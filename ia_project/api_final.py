from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_classic.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document
from langchain_groq import ChatGroq
from langchain_community.embeddings import HuggingFaceEmbeddings

import tempfile
import os
import shutil
import fitz  # PyMuPDF
import base64
import asyncio
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = FastAPI(title="CFE Intelligent Document & Vision API", version="4.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("⛔ GROQ_API_KEY no encontrada en el archivo .env")

# =======================================
# CONFIGURACIÓN DE MODELOS Y RUTAS PERSISTENTES
# =======================================
VISION_MODEL = "llama-3.2-90b-vision-instruct"
TEXT_MODEL   = "llama-3.3-70b-versatile"

MAX_DOCUMENTS       = 100
UPLOAD_DIR          = "uploaded_pdfs"
INDICES_BASE_DIR    = "stored_conversations"
METADATA_FILE       = os.path.join(INDICES_BASE_DIR, "conversations.json")
TEMP_SESSIONS_FILE  = os.path.join(INDICES_BASE_DIR, "temp_sessions.json")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(INDICES_BASE_DIR, exist_ok=True)

# ── Embeddings ──
embeddings = HuggingFaceEmbeddings(
    model_name="intfloat/multilingual-e5-small",
    encode_kwargs={"normalize_embeddings": True},
    model_kwargs={"device": "cpu"},
)

# ── Pool de hilos y Control de Cancelación Activo ──
MAX_WORKERS = min(8, (os.cpu_count() or 4) * 2)
_executor   = ThreadPoolExecutor(max_workers=MAX_WORKERS)
GROQ_CONCURRENCY = 6

# Diccionario global en memoria para registrar procesos en ejecución que pueden ser cancelados
# Estructura: { "cancel_token_uuid": True/False }
CANCELLATION_TOKENS = {}

def load_metadata() -> dict:
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_metadata(meta: dict):
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=4)

def load_temp_sessions() -> dict:
    if os.path.exists(TEMP_SESSIONS_FILE):
        try:
            with open(TEMP_SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_temp_sessions(sessions: dict):
    with open(TEMP_SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=4)

def register_temp_session(conversation_id: str):
    sessions = load_temp_sessions()
    sessions[conversation_id] = {
        "created_at": datetime.now().isoformat(),
        "last_accessed": datetime.now().isoformat()
    }
    save_temp_sessions(sessions)

def unregister_temp_session(conversation_id: str):
    sessions = load_temp_sessions()
    if conversation_id in sessions:
        del sessions[conversation_id]
        save_temp_sessions(sessions)

def cleanup_expired_sessions(max_age_hours: int = 24):
    sessions = load_temp_sessions()
    now = datetime.now()
    expired = []
    
    for conv_id, data in sessions.items():
        try:
            created_at = datetime.fromisoformat(data["created_at"])
            age_hours = (now - created_at).total_seconds() / 3600
            if age_hours > max_age_hours:
                expired.append(conv_id)
        except Exception:
            expired.append(conv_id)
    
    for conv_id in expired:
        delete_conversation_files(conv_id)
        if conv_id in sessions:
            del sessions[conv_id]
    
    if expired:
        save_temp_sessions(sessions)
    
    return len(expired)

def delete_conversation_files(conversation_id: str):
    conv_dir = os.path.join(INDICES_BASE_DIR, conversation_id)
    if os.path.exists(conv_dir):
        try:
            shutil.rmtree(conv_dir)
            print(f"跑 Limpiados archivos de conversación: {conversation_id}")
        except Exception as e:
            print(f"⚠️ Error limpiando {conversation_id}: {e}")

def start_cleanup_scheduler():
    def cleanup_loop():
        while True:
            time.sleep(3600)
            cleaned = cleanup_expired_sessions(max_age_hours=24)
            if cleaned > 0:
                print(f"跑 Limpieza automática: {cleaned} sesiones expiradas eliminadas")
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()

start_cleanup_scheduler()

# =======================================
# EXTRACCIÓN RÁPIDA DE PÁGINAS PDF CON COOPERACIÓN DE CANCELACIÓN
# =======================================
def _extract_pages_data(file_path: str, cancel_token: str = None) -> list[dict]:
    pages_data = []
    file_name  = os.path.basename(file_path)

    with fitz.open(file_path) as pdf:
        for page_num, page in enumerate(pdf):
            # Verificación temprana de cancelación voluntaria
            if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
                break

            text       = page.get_text().strip()
            has_images = len(page.get_images()) > 0
            needs_vision = has_images and len(text) < 300

            img_b64 = None
            if needs_vision:
                pix    = page.get_pixmap(dpi=100)
                img_b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")

            pages_data.append({
                "page_num":     page_num,
                "file_name":    file_name,
                "file_path":    file_path,
                "text":         text,
                "needs_vision": needs_vision,
                "img_b64":      img_b64,
            })
    return pages_data

def _analyze_page(page_data: dict, cancel_token: str = None) -> Document:
    # Si ya se canceló la operación globalmente, saltamos invocaciones costosas a Groq
    if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
        return None

    content = (
        f"ARCHIVO: {page_data['file_name']}\n"
        f"PÁGINA: {page_data['page_num'] + 1}\n"
    )

    if page_data["text"]:
        content += f"CONTENIDO TEXTUAL:\n{page_data['text']}\n"

    if page_data["needs_vision"] and page_data["img_b64"]:
        try:
            llm = ChatGroq(model=VISION_MODEL, api_key=GROQ_API_KEY, temperature=0.0)
            msg = HumanMessage(content=[
                {
                    "type": "text",
                    "text": (
                        "Eres un ingeniero especialista de la CFE. Analiza minuciosamente este plano técnico, "
                        "diagrama, mapa o documento escaneado. Describe equipos, tuberías, conexiones eléctricas, "
                        "valores numéricos, nomenclaturas, leyendas y datos críticos de forma técnica y concisa "
                        "para que sea indexable textualmente."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{page_data['img_b64']}"},
                },
            ])
            response = llm.invoke([msg])
            content += f"\n[DESCRIPCIÓN TÉCNICA DE PLANO/IMAGEN]:\n{response.content}\n"
        except Exception as ve:
            print(f"⚠️ Error visual — {page_data['file_name']} pág.{page_data['page_num']+1}: {ve}")

    return Document(
        page_content=content,
        metadata={"source": page_data["file_path"], "page": page_data["page_num"] + 1},
    )

def extract_pdf_parallel(file_path: str, cancel_token: str = None) -> list[Document]:
    pages_data = _extract_pages_data(file_path, cancel_token)
    documents = [None] * len(pages_data)

    text_only  = [p for p in pages_data if not p["needs_vision"]]
    need_vision = [p for p in pages_data if p["needs_vision"]]

    for pd_item in text_only:
        if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
            return []
        documents[pd_item["page_num"]] = _analyze_page(pd_item, cancel_token)

    if need_vision:
        with ThreadPoolExecutor(max_workers=GROQ_CONCURRENCY) as vis_pool:
            futures = {
                vis_pool.submit(_analyze_page, pd_item, cancel_token): pd_item["page_num"]
                for pd_item in need_vision
            }
            for future in as_completed(futures):
                if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
                    # Forzar el apagado temprano interrumpiendo lectura
                    break
                page_num = futures[future]
                try:
                    documents[page_num] = future.result()
                except Exception as e:
                    print(f"⚠️ Error en pág.{page_num}: {e}")

    return [doc for doc in documents if doc is not None]

def _process_single_pdf(file_path: str, cancel_token: str = None) -> list[Document]:
    try:
        if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
            return []
        return extract_pdf_parallel(file_path, cancel_token)
    except Exception as e:
        print(f"⚠️ Omitiendo {os.path.basename(file_path)}: {e}")
        return []

# =======================================
# ENDPOINT DE CANCELACIÓN EN TIEMPO REAL
# =======================================
@app.post("/cancel_processing/")
async def cancel_processing(cancel_token: str = Form(...)):
    """
    Establece el token de cancelación en True para abortar cualquier
    bucle activo o pool de hilos asociado.
    """
    CANCELLATION_TOKENS[cancel_token] = True
    print(f"🛑 Solicitud de cancelación recibida para el proceso: {cancel_token}")
    return {"message": "✅ Señal de parada enviada exitosamente al hilo de procesamiento."}

# =======================================
# ENDPOINTS DE CONTROL DE CONVERSACIÓN
# =======================================
@app.get("/conversations/")
async def list_conversations():
    return load_metadata()

@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    meta = load_metadata()
    if conversation_id not in meta:
        return JSONResponse(status_code=404, content={"error": "Conversación no encontrada"})
    
    sessions = load_temp_sessions()
    if conversation_id in sessions:
        sessions[conversation_id]["last_accessed"] = datetime.now().isoformat()
        save_temp_sessions(sessions)
    
    return meta[conversation_id]

@app.post("/delete_conversation/")
async def delete_conversation(id: str = Form(...)):
    meta = load_metadata()
    if id not in meta:
        return JSONResponse(status_code=404, content={"error": "Conversación no encontrada"})
    
    conv_dir = os.path.join(INDICES_BASE_DIR, id)
    if os.path.exists(conv_dir):
        try:
            shutil.rmtree(conv_dir)
        except Exception as e:
            print(f"⚠️ Error eliminando directorio {conv_dir}: {e}")
    
    del meta[id]
    save_metadata(meta)
    unregister_temp_session(id)
    return {"message": f"✅ Conversación {id} eliminada correctamente"}

@app.post("/cleanup_session/")
async def cleanup_session(conversation_id: str = Form(...)):
    meta = load_metadata()
    if conversation_id in meta:
        register_temp_session(conversation_id)
        return {"message": f"✅ Sesión {conversation_id} marcada para limpieza automática"}
    return JSONResponse(status_code=404, content={"error": "Conversación no encontrada"})

@app.post("/cleanup_all_temp/")
async def cleanup_all_temp():
    cleaned = cleanup_expired_sessions(max_age_hours=24)
    return {"message": f"🧹 Limpieza completada: {cleaned} sesiones eliminadas"}

# =======================================
# ENDPOINTS: PROCESAMIENTO E INDEXACIÓN
# =======================================
@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...), cancel_token: str = Form(None)):
    # Generar un token único en memoria si el cliente no mandó uno
    if not cancel_token:
        cancel_token = str(uuid.uuid4())
    CANCELLATION_TOKENS[cancel_token] = False

    try:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        loop = asyncio.get_event_loop()
        raw_docs = await loop.run_in_executor(
            _executor, 
            partial(extract_pdf_parallel, file_path, cancel_token)
        )

        # Si durante la extracción de hilos se activó la cancelación, abortamos el guardado
        if CANCELLATION_TOKENS.get(cancel_token) == True:
            if os.path.exists(file_path):
                os.remove(file_path)
            return JSONResponse(status_code=499, content={"error": "Lectura de PDF cancelada por el usuario."})

        splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)
        docs = splitter.split_documents(raw_docs)

        meta = load_metadata()
        conv_idx = len(meta) + 1
        conv_id = f"conversacion_{conv_idx}"
        conv_dir = os.path.join(INDICES_BASE_DIR, conv_id)

        pdf_vectorstore = FAISS.from_documents(docs, embeddings)
        pdf_vectorstore.save_local(conv_dir)

        meta[conv_id] = {
            "id": conv_id,
            "title": f"Conversación {conv_idx}",
            "type": "pdf",
            "target_name": file.filename,
            "file_path": file_path,
            "history": [],
            "created_at": datetime.now().isoformat()
        }
        save_metadata(meta)

        return {
            "conversation_id": conv_id,
            "message": "✅ PDF procesado e indexado correctamente.",
            "pages":   len(raw_docs),
            "chunks":  len(docs)
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        # Limpieza de banderas de estado de cancelación
        if cancel_token in CANCELLATION_TOKENS:
            del CANCELLATION_TOKENS[cancel_token]

@app.post("/index_folder/")
async def index_folder(folder_path: str = Form(...), cancel_token: str = Form(None)):
    if not os.path.exists(folder_path):
        return JSONResponse(status_code=400, content={"error": "La ruta especificada no existe."})

    if not cancel_token:
        cancel_token = str(uuid.uuid4())
    CANCELLATION_TOKENS[cancel_token] = False

    try:
        pdf_files = [
            os.path.join(root, f)
            for root, _, files in os.walk(folder_path)
            for f in files
            if f.lower().endswith(".pdf")
        ]

        if not pdf_files:
            return JSONResponse(status_code=400, content={"error": "No se encontraron archivos PDF."})
        if len(pdf_files) > MAX_DOCUMENTS:
            return JSONResponse(status_code=400, content={"error": f"Límite excedido: máximo {MAX_DOCUMENTS} PDFs."})

        all_docs = []
        loop = asyncio.get_event_loop()
        
        # Procesamiento secuencial/paralelo controlado para vigilar la interrupción entre archivos
        for fp in pdf_files:
            if CANCELLATION_TOKENS.get(cancel_token) == True:
                break
            
            # Procesamos por lotes/archivos individuales mapeados al pool
            res_docs = await loop.run_in_executor(_executor, _process_single_pdf, fp, cancel_token)
            if isinstance(res_docs, list):
                all_docs.extend(res_docs)

        if CANCELLATION_TOKENS.get(cancel_token) == True:
            return JSONResponse(status_code=499, content={"error": "Indexación del directorio cancelada por el usuario."})

        if not all_docs:
            return JSONResponse(status_code=500, content={"error": "No se pudo extraer contenido o se interrumpió el proceso."})

        splitter = RecursiveCharacterTextSplitter(chunk_size=1800, chunk_overlap=200)
        docs     = splitter.split_documents(all_docs)

        meta = load_metadata()
        conv_idx = len(meta) + 1
        conv_id = f"conversacion_{conv_idx}"
        conv_dir = os.path.join(INDICES_BASE_DIR, conv_id)

        folder_vectorstore = FAISS.from_documents(docs, embeddings)
        folder_vectorstore.save_local(conv_dir)

        folder_display_name = os.path.basename(os.path.normpath(folder_path)) or folder_path
        meta[conv_id] = {
            "id": conv_id,
            "title": f"Conversación {conv_idx}",
            "type": "folder",
            "target_name": folder_display_name,
            "file_path": folder_path,
            "history": [],
            "created_at": datetime.now().isoformat()
        }
        save_metadata(meta)

        return {
            "conversation_id": conv_id,
            "message":   "✅ Indexación recursiva completada.",
            "documents": len(pdf_files)
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if cancel_token in CANCELLATION_TOKENS:
            del CANCELLATION_TOKENS[cancel_token]

# =======================================
# ENDPOINTS: CONSULTAS (RAG)
# =======================================
@app.post("/ask_pdf/")
async def ask_pdf(question: str = Form(...), style: str = Form("normal"), conversation_id: str = Form(...)):
    meta = load_metadata()
    if conversation_id not in meta:
        return JSONResponse(status_code=404, content={"error": "ID de conversación no válido."})

    conv_dir = os.path.join(INDICES_BASE_DIR, conversation_id)
    try:
        local_store = FAISS.load_local(conv_dir, embeddings, allow_dangerous_deserialization=True)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Error al cargar el índice: {e}"})

    style_map = {
        "normal":    "Eres un analista documental experto de CFE. Responde de forma profesional basándote en el texto y planos analizados.",
        "amable":    "Eres un analista documental experto de CFE. Responde de manera amable, cordial y altamente detallada.",
        "agresivo":  "Eres un analista documental experto de CFE. Responde de forma directa, técnica, concisa y sin rodeos.",
    }
    persona = style_map.get(style, style_map["normal"])

    template = f"""{persona}
Responde ÚNICAMENTE usando el contexto proporcionado.
Si no encuentras información suficiente, indica claramente que no existe en el documento.

Contexto:
{{context}}

Pregunta:
{{question}}

Respuesta:"""

    prompt = PromptTemplate(template=template, input_variables=["context", "question"])
    chain  = RetrievalQA.from_chain_type(
        llm=ChatGroq(model=TEXT_MODEL, api_key=GROQ_API_KEY, temperature=0.2),
        retriever=local_store.as_retriever(search_type="mmr", search_kwargs={"k": 5}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )

    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, partial(chain.invoke, {"query": question}))
    sources = sorted(set(d.metadata["source"] for d in result["source_documents"]))

    meta[conversation_id]["history"].append({"role": "user", "content": question})
    meta[conversation_id]["history"].append({"role": "assistant", "content": result["result"], "sources": sources})
    save_metadata(meta)
    
    sessions = load_temp_sessions()
    if conversation_id in sessions:
        sessions[conversation_id]["last_accessed"] = datetime.now().isoformat()
        save_temp_sessions(sessions)

    return {"answer": result["result"], "sources": sources}

@app.post("/ask_folder/")
async def ask_folder(question: str = Form(...), conversation_id: str = Form(...)):
    meta = load_metadata()
    if conversation_id not in meta:
        return JSONResponse(status_code=404, content={"error": "ID de conversación no válido."})

    conv_dir = os.path.join(INDICES_BASE_DIR, conversation_id)
    try:
        local_store = FAISS.load_local(conv_dir, embeddings, allow_dangerous_deserialization=True)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Error al cargar el índice: {e}"})

    template = """Eres un Ingeniero Analista del Sistema de Información CFE El Cajón.
Usa los fragmentos de contexto (texto e interpretaciones de planos por visión) para responder
de forma técnica, factual y sumamente precisa.

Contexto:
{context}

Pregunta:
{question}

Respuesta:"""

    prompt = PromptTemplate(template=template, input_variables=["context", "question"])
    chain  = RetrievalQA.from_chain_type(
        llm=ChatGroq(model=TEXT_MODEL, api_key=GROQ_API_KEY, temperature=0.0),
        retriever=local_store.as_retriever(search_type="mmr", search_kwargs={"k": 8}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )

    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, partial(chain.invoke, {"query": question}))
    sources = sorted(set(d.metadata["source"] for d in result["source_documents"]))

    meta[conversation_id]["history"].append({"role": "user", "content": question})
    meta[conversation_id]["history"].append({"role": "assistant", "content": result["result"], "sources": sources})
    save_metadata(meta)
    
    sessions = load_temp_sessions()
    if conversation_id in sessions:
        sessions[conversation_id]["last_accessed"] = datetime.now().isoformat()
        save_temp_sessions(sessions)

    return {"answer": result["result"], "sources": sources}

# =======================================
# ENDPOINT DE VISTA PREVIA DE DOCUMENTOS
# =======================================
@app.get("/preview/")
async def preview_file(path: str):
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": f"Archivo no encontrado en la ruta: {path}"})
    return FileResponse(path, media_type="application/pdf")

# =======================================
# SELECTOR NATIVO DE CARPETA (tkinter)
# =======================================
@app.post("/browse_folder/")
async def browse_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()                      
        root.wm_attributes('-topmost', 1)    

        folder_path = filedialog.askdirectory(
            title="Seleccionar carpeta de documentos PDF"
        )
        root.destroy()

        if folder_path:
            folder_path = os.path.normpath(folder_path)
            return {"path": folder_path}
        else:
            return JSONResponse(status_code=200, content={"path": ""})

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"No se pudo abrir el selector de carpeta: {str(e)}"}
        )

# =======================================
# CONTROL Y LIMPIEZA TOTAL
# =======================================
@app.post("/clear_index/")
async def clear_index():
    for path in (UPLOAD_DIR, INDICES_BASE_DIR):
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
            except Exception as e:
                print(f"⚠️ Error al limpiar ruta {path}: {e}")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(INDICES_BASE_DIR, exist_ok=True)
    save_temp_sessions({})
    return {"message": "✅ Índices de memoria, disco y archivos cargados eliminados."}

@app.get("/health")
async def health():
    meta = load_metadata()
    sessions = load_temp_sessions()
    return {
        "active_conversations": len(meta),
        "temp_sessions": len(sessions),
        "max_documents":  MAX_DOCUMENTS,
        "vision_model":   VISION_MODEL,
        "text_model":     TEXT_MODEL,
        "workers":        MAX_WORKERS,
        "status": "healthy"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)