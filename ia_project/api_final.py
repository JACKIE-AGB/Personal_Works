from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from contextlib import asynccontextmanager
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_classic.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document
from langchain_groq import ChatGroq
from langchain_community.embeddings import HuggingFaceEmbeddings
from typing import List
from pathlib import Path

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

# =======================================
# ESTADO DE PRE-INDEXACIÓN
# =======================================
PREINDEX_STATUS = {
    "running": False,
    "done": False,
    "total": 0,
    "indexed": 0,
    "errors": 0,
    "current_file": "",
    "log": []          # lista de mensajes para el frontend
}

# Mapa: relative_path → conversation_id  (para lookup rápido al hacer clic)
PREINDEX_MAP: dict[str, str] = {}

def _preindex_single_document(doc: dict) -> tuple[str, str | None]:
    """
    Indexa un documento de XAMPP en hilo de fondo.
    Devuelve (relative_path, conversation_id | None).
    """
    full_path  = doc["full_path"]
    rel_path   = doc["relative_path"]
    file_name  = doc["name"]
    ext        = os.path.splitext(full_path)[1].lower()

    try:
        raw_docs = []

        if ext == ".pdf":
            raw_docs = extract_pdf_parallel(full_path)

        elif ext == ".txt":
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            raw_docs = [Document(page_content=content,
                                 metadata={"source": full_path, "page": 1})]
        else:
            return rel_path, None

        if not raw_docs:
            return rel_path, None

        splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)
        docs     = splitter.split_documents(raw_docs)

        conv_id  = f"xampp_{uuid.uuid4().hex[:8]}"
        conv_dir = os.path.join(INDICES_BASE_DIR, conv_id)

        vectorstore = FAISS.from_documents(docs, embeddings)
        vectorstore.save_local(conv_dir)

        meta = load_metadata()
        meta[conv_id] = {
            "id":          conv_id,
            "title":       file_name,
            "type":        "xampp",
            "target_name": file_name,
            "file_path":   full_path,
            "relative_path": rel_path,
            "history":     [],
            "created_at":  datetime.now().isoformat()
        }
        save_metadata(meta)
        # NO registrar como sesión temporal — es un índice permanente de la BD

        # Persistir en disco para sobrevivir reinicios
        pmap = load_preindex_map()
        pmap[rel_path] = conv_id
        save_preindex_map(pmap)

        print(f"  ✅ Pre-indexado: {file_name}  →  {conv_id}")
        return rel_path, conv_id

    except Exception as e:
        print(f"  ⚠️ Error pre-indexando {file_name}: {e}")
        return rel_path, None


def run_preindex():
    """Ejecuta la pre-indexación completa en un hilo de fondo.
    Solo indexa documentos nuevos; los ya indexados se recuperan del mapa persistente.
    """
    global PREINDEX_STATUS, PREINDEX_MAP

    PREINDEX_STATUS["running"] = True
    PREINDEX_STATUS["done"]    = False
    PREINDEX_STATUS["log"]     = []

    # ── Recuperar índices pre-existentes del disco ──
    persisted = load_preindex_map()
    meta       = load_metadata()

    # Validar que el índice en disco sigue existiendo para cada entrada persistida
    valid_persisted = {}
    for rel_path, conv_id in persisted.items():
        conv_dir = os.path.join(INDICES_BASE_DIR, conv_id)
        if conv_id in meta and os.path.exists(conv_dir):
            valid_persisted[rel_path] = conv_id
        else:
            print(f"  ⚠️ Índice huérfano descartado: {rel_path} → {conv_id}")

    # Sincronizar mapa en memoria con los válidos
    PREINDEX_MAP.update(valid_persisted)
    if len(valid_persisted) != len(persisted):
        save_preindex_map(valid_persisted)   # limpiar entradas huérfanas

    if valid_persisted:
        print(f"⚡ {len(valid_persisted)} documento(s) ya pre-indexados — omitiendo re-indexación.")

    docs = scan_xampp_documents()
    PREINDEX_STATUS["total"] = len(docs)

    # Filtrar solo los que aún no están indexados
    pending = [d for d in docs if d["relative_path"] not in PREINDEX_MAP]

    if not pending:
        print("✅ Todos los documentos de la BD ya están indexados — nada que hacer.")
        PREINDEX_STATUS["indexed"] = len(valid_persisted)
        PREINDEX_STATUS["running"] = False
        PREINDEX_STATUS["done"]    = True
        return

    print(f"⚙️  Pre-indexando {len(pending)} documento(s) nuevo(s) de la BD...")

    futures = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for doc in pending:
            PREINDEX_STATUS["current_file"] = doc["name"]
            f = pool.submit(_preindex_single_document, doc)
            futures[f] = doc["name"]

        for future in as_completed(futures):
            name = futures[future]
            try:
                rel_path, conv_id = future.result()
                if conv_id:
                    PREINDEX_MAP[rel_path] = conv_id
                    PREINDEX_STATUS["indexed"] += 1
                    msg = f"✅ {name}"
                else:
                    PREINDEX_STATUS["errors"] += 1
                    msg = f"⚠️ {name} (sin contenido o error)"
            except Exception as e:
                PREINDEX_STATUS["errors"] += 1
                msg = f"❌ {name}: {e}"

            PREINDEX_STATUS["log"].append(msg)
            PREINDEX_STATUS["current_file"] = name

    PREINDEX_STATUS["indexed"] += len(valid_persisted)   # contar los recuperados también
    PREINDEX_STATUS["running"] = False
    PREINDEX_STATUS["done"]    = True
    print(f"✅ Pre-indexación completa: {PREINDEX_STATUS['indexed']} OK, "
          f"{PREINDEX_STATUS['errors']} errores.")


# =======================================
# LIFESPAN: LIMPIEZA + PRE-INDEXACIÓN
# =======================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Servidor iniciado — limpiando sesiones de usuario anteriores...")
    delete_user_conversations()   # ← solo borra sesiones de usuario, NO índices de la BD
    start_cleanup_scheduler()

    # Lanzar pre-indexación en hilo de fondo (reutiliza índices existentes si los hay)
    preindex_thread = threading.Thread(target=run_preindex, daemon=True)
    preindex_thread.start()

    yield

    print("🛑 Servidor apagado — eliminando sesiones de usuario...")
    delete_user_conversations()   # ← conserva índices de la BD para el próximo arranque

app = FastAPI(title="CFE Intelligent Document & Vision API", version="4.2", lifespan=lifespan)

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
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"   # Soporta visión + texto técnico complejo
TEXT_MODEL   = "meta-llama/llama-4-scout-17b-16e-instruct"   # Mismo modelo: rápido, preciso y multimodal

MAX_DOCUMENTS       = 150
UPLOAD_DIR          = "uploaded_pdfs"
XAMPP_DOCS_PATH     = r"C:\xampp\htdocs\ia_docs"
APACHE_BASE_URL     ="http://localhost/ia_docs"
SUPPORTED_EXTENSIONS = [".pdf"]
INDICES_BASE_DIR    = "stored_conversations"
METADATA_FILE       = os.path.join(INDICES_BASE_DIR, "conversations.json")
TEMP_SESSIONS_FILE  = os.path.join(INDICES_BASE_DIR, "temp_sessions.json")
PREINDEX_MAP_FILE   = os.path.join(INDICES_BASE_DIR, "preindex_map.json")  # ← persistente en disco

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(INDICES_BASE_DIR, exist_ok=True)

# ── Embeddings ──
embeddings = HuggingFaceEmbeddings(
    model_name="intfloat/multilingual-e5-small",
    encode_kwargs={"normalize_embeddings": True},
    model_kwargs={"device": "cpu"},
)

# ── Pool de hilos ──
MAX_WORKERS = min(8, (os.cpu_count() or 4) * 2)
_executor   = ThreadPoolExecutor(max_workers=MAX_WORKERS)
GROQ_CONCURRENCY = 6

CANCELLATION_TOKENS = {}

def load_preindex_map() -> dict:
    """Carga el mapa de pre-indexación persistente desde disco."""
    if os.path.exists(PREINDEX_MAP_FILE):
        try:
            with open(PREINDEX_MAP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_preindex_map(pmap: dict):
    """Guarda el mapa de pre-indexación en disco (sobrevive reinicios)."""
    with open(PREINDEX_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(pmap, f, ensure_ascii=False, indent=4)

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
            print(f"🧹 Limpiados archivos de conversación: {conversation_id}")
        except Exception as e:
            print(f"⚠️ Error limpiando {conversation_id}: {e}")

def delete_user_conversations():
    """
    Borra únicamente las conversaciones subidas por el usuario (tipo 'pdf' y 'folder').
    Los índices pre-indexados de la BD (tipo 'xampp') se conservan en disco
    para no tener que re-indexar al reiniciar el servidor.
    """
    meta = load_metadata()
    xampp_ids = {cid for cid, data in meta.items() if data.get("type") == "xampp"}

    # Eliminar del metadata solo las no-xampp
    new_meta = {cid: data for cid, data in meta.items() if cid in xampp_ids}

    # Borrar directorios de conversaciones de usuario
    if os.path.exists(INDICES_BASE_DIR):
        for item in os.listdir(INDICES_BASE_DIR):
            item_path = os.path.join(INDICES_BASE_DIR, item)
            if os.path.isdir(item_path) and item not in xampp_ids:
                try:
                    shutil.rmtree(item_path)
                except Exception as e:
                    print(f"⚠️ Error eliminando índice de usuario {item_path}: {e}")

    save_metadata(new_meta)

    # Limpiar temp_sessions (solo sesiones de usuario)
    if os.path.exists(TEMP_SESSIONS_FILE):
        try:
            os.remove(TEMP_SESSIONS_FILE)
        except:
            pass

    # Limpiar archivos PDF subidos por el usuario
    if os.path.exists(UPLOAD_DIR):
        for item in os.listdir(UPLOAD_DIR):
            item_path = os.path.join(UPLOAD_DIR, item)
            try:
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except Exception as e:
                print(f"⚠️ Error eliminando archivo {item_path}: {e}")

    os.makedirs(INDICES_BASE_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    print(f"🧹 Sesiones de usuario limpiadas. Índices BD conservados: {len(xampp_ids)}.")

def delete_all_conversations():
    if os.path.exists(METADATA_FILE):
        try:
            os.remove(METADATA_FILE)
        except:
            pass
    
    if os.path.exists(TEMP_SESSIONS_FILE):
        try:
            os.remove(TEMP_SESSIONS_FILE)
        except:
            pass

    if os.path.exists(INDICES_BASE_DIR):
        for item in os.listdir(INDICES_BASE_DIR):
            item_path = os.path.join(INDICES_BASE_DIR, item)
            if os.path.isdir(item_path):
                try:
                    shutil.rmtree(item_path)
                except Exception as e:
                    print(f"⚠️ Error eliminando índice {item_path}: {e}")

    if os.path.exists(UPLOAD_DIR):
        for item in os.listdir(UPLOAD_DIR):
            item_path = os.path.join(UPLOAD_DIR, item)
            try:
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except Exception as e:
                print(f"⚠️ Error eliminando archivo {item_path}: {e}")

    os.makedirs(INDICES_BASE_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    print("🧹 Limpieza total de sesión completada.")

def start_cleanup_scheduler():
    def cleanup_loop():
        while True:
            time.sleep(3600)
            cleaned = cleanup_expired_sessions(max_age_hours=24)
            if cleaned > 0:
                print(f"🧹 Limpieza automática: {cleaned} sesiones expiradas eliminadas")
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()

# =======================================
# EXTRACCIÓN DE PDF
# =======================================
def _extract_pages_data(file_path: str, cancel_token: str = None) -> list[dict]:
    pages_data = []
    file_name  = os.path.basename(file_path)

    with fitz.open(file_path) as pdf:
        for page_num, page in enumerate(pdf):
            if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
                break

            text = page.get_text().strip()
            has_images = len(page.get_images()) > 0
            needs_vision = has_images and len(text) < 300

            img_b64 = None
            if needs_vision:
                pix = page.get_pixmap(dpi=100)
                img_b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")

            pages_data.append({
                "page_num": page_num,
                "file_name": file_name,
                "file_path": file_path,
                "text": text,
                "needs_vision": needs_vision,
                "img_b64": img_b64,
            })
    return pages_data

def _analyze_page(page_data: dict, cancel_token: str = None) -> Document:
    if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
        return None

    content = (f"ARCHIVO: {page_data['file_name']}\n"
               f"PÁGINA: {page_data['page_num'] + 1}\n")

    if page_data["text"]:
        content += f"CONTENIDO TEXTUAL:\n{page_data['text']}\n"

    if page_data["needs_vision"] and page_data["img_b64"]:
        try:
            llm = ChatGroq(model=VISION_MODEL, api_key=GROQ_API_KEY, temperature=0.0)
            msg = HumanMessage(content=[
                {"type": "text", "text": "Eres un ingeniero especialista de la CFE. Analiza minuciosamente este plano técnico, diagrama, mapa o documento escaneado. Describe equipos, tuberías, conexiones eléctricas, valores numéricos, nomenclaturas, leyendas y datos críticos de forma técnica y concisa para que sea indexable textualmente."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{page_data['img_b64']}"}}
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

    text_only = [p for p in pages_data if not p["needs_vision"]]
    need_vision = [p for p in pages_data if p["needs_vision"]]

    for pd_item in text_only:
        if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
            return []
        documents[pd_item["page_num"]] = _analyze_page(pd_item, cancel_token)

    if need_vision:
        with ThreadPoolExecutor(max_workers=GROQ_CONCURRENCY) as vis_pool:
            futures = {vis_pool.submit(_analyze_page, pd_item, cancel_token): pd_item["page_num"] for pd_item in need_vision}
            for future in as_completed(futures):
                if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
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
# ESCANEAR DOCUMENTOS EN XAMPP/APACHE
# =======================================

def scan_xampp_documents():
    documents = []

    if not os.path.exists(XAMPP_DOCS_PATH):
        return documents

    for root, dirs, files in os.walk(XAMPP_DOCS_PATH):

        for file in files:
            ext = os.path.splitext(file)[1].lower()

            if ext not in SUPPORTED_EXTENSIONS:
                continue

            full_path = os.path.join(root, file)

            relative_path = os.path.relpath(full_path, XAMPP_DOCS_PATH)

            documents.append({
                "name": file,
                "relative_path": relative_path.replace("\\", "/"),
                "full_path": full_path,
                "type": "file",
                "url": f"{APACHE_BASE_URL}/{relative_path.replace(os.sep, '/')}"
            })

    return documents

@app.get("/xampp_documents/")
async def xampp_documents():
    docs = scan_xampp_documents()
    # Añadir flag indicando si cada documento ya está pre-indexado
    for doc in docs:
        doc["preindexed"] = doc["relative_path"] in PREINDEX_MAP
    return {
        "total": len(docs),
        "documents": docs
    }

@app.get("/preindex_status/")
async def preindex_status():
    """Devuelve el estado actual de la pre-indexación al arranque."""
    return {
        "running":      PREINDEX_STATUS["running"],
        "done":         PREINDEX_STATUS["done"],
        "total":        PREINDEX_STATUS["total"],
        "indexed":      PREINDEX_STATUS["indexed"],
        "errors":       PREINDEX_STATUS["errors"],
        "current_file": PREINDEX_STATUS["current_file"],
        "log":          PREINDEX_STATUS["log"][-20:],   # últimos 20 mensajes
    }

# =======================================
# INDEXAR DOCUMENTO DE XAMPP
# (usa el índice pre-generado si ya está listo)
# =======================================

@app.post("/index_xampp_document/")
async def index_xampp_document(path: str = Form(...)):

    # ── Atajo: si ya fue pre-indexado, devolver el ID directamente ──
    if path in PREINDEX_MAP:
        conv_id = PREINDEX_MAP[path]
        meta    = load_metadata()
        if conv_id in meta:
            print(f"⚡ Usando índice pre-generado para: {path} → {conv_id}")
            return {
                "conversation_id": conv_id,
                "message": "✅ Documento ya pre-indexado — listo para preguntar"
            }
        # Si el índice fue eliminado (raro), caer al flujo normal
        del PREINDEX_MAP[path]

    full_path = os.path.join(XAMPP_DOCS_PATH, path)

    if not os.path.exists(full_path):
        return JSONResponse(
            status_code=404,
            content={"error": "Documento no encontrado"}
        )

    try:

        ext = os.path.splitext(full_path)[1].lower()

        raw_docs = []

        if ext == ".pdf":
            loop = asyncio.get_event_loop()
            raw_docs = await loop.run_in_executor(_executor, partial(extract_pdf_parallel, full_path))

        elif ext == ".txt":

            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            raw_docs = [
                Document(
                    page_content=content,
                    metadata={"source": full_path, "page": 1}
                )
            ]

        else:
            return JSONResponse(
                status_code=400,
                content={"error": "Formato no soportado"}
            )

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=200
        )

        docs = splitter.split_documents(raw_docs)

        meta = load_metadata()

        conv_id  = f"xampp_{uuid.uuid4().hex[:8]}"
        conv_dir = os.path.join(INDICES_BASE_DIR, conv_id)

        vectorstore = FAISS.from_documents(docs, embeddings)
        vectorstore.save_local(conv_dir)

        file_name = os.path.basename(full_path)

        meta[conv_id] = {
            "id":            conv_id,
            "title":         file_name,
            "type":          "xampp",
            "target_name":   file_name,
            "file_path":     full_path,
            "relative_path": path,
            "history":       [],
            "created_at":    datetime.now().isoformat()
        }

        save_metadata(meta)
        # NO registrar como sesión temporal — índice permanente de la BD

        # Persistir en disco para sobrevivir reinicios
        PREINDEX_MAP[path] = conv_id
        pmap = load_preindex_map()
        pmap[path] = conv_id
        save_preindex_map(pmap)

        return {
            "conversation_id": conv_id,
            "message": "✅ Documento XAMPP indexado correctamente"
        }

    except Exception as e:

        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

def get_docs_in_xampp_folder(folder_path: str):
    folder_path = folder_path.replace("\\", "/").strip("/")
    docs = []

    for doc in scan_xampp_documents():
        rel = doc["relative_path"].replace("\\", "/")
        if rel == folder_path or rel.startswith(folder_path + "/"):
            docs.append(doc)

    return docs


@app.post("/index_xampp_folder/")
async def index_xampp_folder(folder_path: str = Form(...), folder_name: str = Form(...)):
    try:
        meta = load_metadata()

        folder_path = folder_path.replace("\\", "/").strip("/")
        existing = next(
            (
                cid for cid, data in meta.items()
                if data.get("type") == "xampp_folder" and data.get("folder_path") == folder_path
            ),
            None
        )

        if existing and os.path.exists(os.path.join(INDICES_BASE_DIR, existing)):
            return {
                "conversation_id": existing,
                "message": "✅ Carpeta ya pre-leída — lista para preguntar"
            }

        docs_in_folder = get_docs_in_xampp_folder(folder_path)
        if not docs_in_folder:
            return JSONResponse(status_code=404, content={"error": "No se encontraron documentos en esa carpeta."})

        all_documents = []
        loop = asyncio.get_event_loop()

        for doc in docs_in_folder:
            full_path = doc["full_path"]
            ext = os.path.splitext(full_path)[1].lower()

            if ext == ".pdf":
                raw_docs = await loop.run_in_executor(_executor, partial(extract_pdf_parallel, full_path))
            elif ext == ".txt":
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                raw_docs = [Document(page_content=content, metadata={"source": full_path, "page": 1})]
            else:
                continue

            all_documents.extend(raw_docs)

        if not all_documents:
            return JSONResponse(status_code=400, content={"error": "No se pudo extraer texto de la carpeta."})

        splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)
        docs = splitter.split_documents(all_documents)

        conv_id = f"xamppfolder_{uuid.uuid4().hex[:8]}"
        conv_dir = os.path.join(INDICES_BASE_DIR, conv_id)
        os.makedirs(conv_dir, exist_ok=True)

        db = FAISS.from_documents(docs, embeddings)
        db.save_local(conv_dir)

        meta[conv_id] = {
            "id": conv_id,
            "title": f"Carpeta: {folder_name}",
            "type": "xampp_folder",
            "target_name": f"{folder_name} ({len(docs_in_folder)} archivos)",
            "file_path": conv_dir,
            "folder_path": folder_path,
            "history": [],
            "created_at": datetime.now().isoformat()
        }
        save_metadata(meta)

        print(f"✅ Carpeta XAMPP indexada. ID: {conv_id} — {len(docs_in_folder)} archivos, {len(docs)} chunks")
        return {
            "conversation_id": conv_id,
            "message": "✅ Carpeta pre-leída e indexada correctamente"
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Error al indexar carpeta XAMPP '{folder_path}': {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

# =======================================
# ENDPOINTS DE CONVERSACIÓN
# =======================================
@app.get("/conversations/")
async def list_conversations():
    return load_metadata()

@app.post("/clear_conversation_history/")
async def clear_conversation_history(id: str = Form(...)):
    """
    Limpia el historial de chat de una conversación sin borrar el índice FAISS.
    Usado para conversaciones de tipo 'xampp' cuyos índices son permanentes.
    """
    meta = load_metadata()
    if id not in meta:
        return JSONResponse(status_code=404, content={"error": "Conversación no encontrada"})

    meta[id]["history"] = []
    save_metadata(meta)
    return {"message": f"✅ Historial de conversación {id} limpiado correctamente"}

@app.post("/delete_conversation/")
async def delete_conversation(id: str = Form(...)):
    meta = load_metadata()
    if id not in meta:
        return JSONResponse(status_code=404, content={"error": "Conversación no encontrada"})
    
    conv_data = meta[id]
    conv_dir = os.path.join(INDICES_BASE_DIR, id)
    if os.path.exists(conv_dir):
        try:
            shutil.rmtree(conv_dir)
        except Exception as e:
            print(f"⚠️ Error eliminando directorio {conv_dir}: {e}")
    
    del meta[id]
    save_metadata(meta)
    unregister_temp_session(id)

    # Si era un índice de BD, eliminarlo también del mapa persistente
    if conv_data.get("type") == "xampp":
        rel_path = conv_data.get("relative_path", "")
        pmap = load_preindex_map()
        if rel_path in pmap:
            del pmap[rel_path]
            save_preindex_map(pmap)
        if rel_path in PREINDEX_MAP:
            del PREINDEX_MAP[rel_path]

    return {"message": f"✅ Conversación {id} eliminada correctamente"}

# =======================================
# ENDPOINT: SUBIR PDF INDIVIDUAL
# =======================================
@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...), cancel_token: str = Form(None)):
    if not cancel_token:
        cancel_token = str(uuid.uuid4())
    CANCELLATION_TOKENS[cancel_token] = False

    try:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        loop = asyncio.get_event_loop()
        raw_docs = await loop.run_in_executor(_executor, partial(extract_pdf_parallel, file_path, cancel_token))

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
        register_temp_session(conv_id)

        return {
            "conversation_id": conv_id,
            "message": "✅ PDF procesado e indexado correctamente.",
            "pages": len(raw_docs),
            "chunks": len(docs)
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if cancel_token in CANCELLATION_TOKENS:
            del CANCELLATION_TOKENS[cancel_token]

# =======================================
# ENDPOINT: SUBIR CARPETA REMOTA (CORREGIDO)
# =======================================
@app.post("/upload_folder_remote/")
async def upload_folder_remote(files: List[UploadFile] = File(...), cancel_token: str = Form(None)):
    """
    Recibe múltiples archivos PDF simulando la subida de una carpeta completa 
    desde el entorno web remoto.
    """
    if not cancel_token:
        cancel_token = str(uuid.uuid4())
    CANCELLATION_TOKENS[cancel_token] = False
    
    saved_paths = []
    all_documents = []
    conversation_id = None
    
    try:
        print(f"📁 Recibidos {len(files)} archivos para procesar")
        
        # Filtrar solo PDFs y guardarlos
        pdf_files = [f for f in files if f.filename.lower().endswith('.pdf')]
        
        if not pdf_files:
            return JSONResponse(status_code=400, content={"error": "No se encontraron archivos PDF válidos en la carpeta subida."})
        
        print(f"📄 Procesando {len(pdf_files)} archivos PDF...")
        
        # Guardar archivos
        for file in pdf_files:
            if CANCELLATION_TOKENS.get(cancel_token) == True:
                print(f"🛑 Proceso cancelado por el usuario.")
                for path in saved_paths:
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except:
                            pass
                return JSONResponse(status_code=200, content={"message": "Proceso cancelado por el usuario", "cancelled": True})

            # Extraer el nombre base del archivo (sin rutas)
            base_filename = os.path.basename(file.filename)
            file_path = os.path.join(UPLOAD_DIR, base_filename)
            
            # Manejar duplicados
            counter = 1
            original_path = file_path
            while os.path.exists(file_path):
                name, ext = os.path.splitext(original_path)
                file_path = f"{name}_{counter}{ext}"
                counter += 1
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_paths.append(file_path)
            print(f"✅ Guardado: {os.path.basename(file_path)}")

        # Procesar cada PDF
        loop = asyncio.get_event_loop()
        for idx, path in enumerate(saved_paths):
            if CANCELLATION_TOKENS.get(cancel_token) == True:
                break
            
            print(f"🔍 Procesando ({idx+1}/{len(saved_paths)}): {os.path.basename(path)}")
            docs = await loop.run_in_executor(_executor, _process_single_pdf, path, cancel_token)
            if docs:
                all_documents.extend(docs)
                print(f"   ✓ Extraídas {len(docs)} páginas")

        if CANCELLATION_TOKENS.get(cancel_token) == True:
            for path in saved_paths:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except:
                        pass
            return JSONResponse(status_code=200, content={"message": "Proceso cancelado por el usuario", "cancelled": True})

        if not all_documents:
            return JSONResponse(status_code=400, content={"error": "No se pudo extraer texto de ningún documento técnico de la carpeta."})

        # Dividir en chunks e indexar
        print(f"📊 Total de documentos extraídos: {len(all_documents)}")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        final_splits = text_splitter.split_documents(all_documents)
        print(f"📦 Total de chunks generados: {len(final_splits)}")
        
        # Crear conversación
        meta = load_metadata()
        conv_idx = len(meta) + 1
        conversation_id = f"conversacion_{conv_idx}"
        conv_dir = os.path.join(INDICES_BASE_DIR, conversation_id)
        os.makedirs(conv_dir, exist_ok=True)
        
        # Crear índice FAISS
        db = FAISS.from_documents(final_splits, embeddings)
        db.save_local(conv_dir)
        
        # Obtener nombre de la carpeta (intentar extraer de la ruta original)
        folder_name = "Carpeta_Remota"
        if files and len(files) > 0:
            first_file = files[0].filename
            if '/' in first_file:
                folder_name = first_file.split('/')[0]
        
        # Guardar metadatos
        meta[conversation_id] = {
            "id": conversation_id,
            "title": f"Carpeta: {folder_name}",
            "type": "folder",
            "target_name": f"{folder_name} ({len(saved_paths)} PDFs)",
            "file_path": conv_dir,
            "history": [],
            "created_at": datetime.now().isoformat()
        }
        save_metadata(meta)
        register_temp_session(conversation_id)
        
        print(f"✅ Carpeta indexada correctamente. ID: {conversation_id}")
        
        return {
            "message": f"✅ Carpeta indexada con éxito. {len(saved_paths)} archivos cargados, {len(final_splits)} chunks creados.",
            "conversation_id": conversation_id,
            "files_processed": len(saved_paths),
            "chunks_created": len(final_splits)
        }

    except Exception as e:
        print(f"❌ Error al procesar carpeta remota: {e}")
        import traceback
        traceback.print_exc()
        for path in saved_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if cancel_token in CANCELLATION_TOKENS:
            del CANCELLATION_TOKENS[cancel_token]

# =======================================
# ENDPOINTS: CONSULTAS RAG
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
        "normal": "Eres un analista documental experto de CFE. Responde de forma profesional basándote en el texto y planos analizados.",
        "amable": "Eres un analista documental experto de CFE. Responde de manera amable, cordial y altamente detallada.",
        "agresivo": "Eres un analista documental experto de CFE. Responde de forma directa, técnica, concisa y sin rodeos.",
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
    chain = RetrievalQA.from_chain_type(
        llm=ChatGroq(model=TEXT_MODEL, api_key=GROQ_API_KEY, temperature=0.2),
        retriever=local_store.as_retriever(search_type="mmr", search_kwargs={"k": 5}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )

    loop = asyncio.get_event_loop()
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
    chain = RetrievalQA.from_chain_type(
        llm=ChatGroq(model=TEXT_MODEL, api_key=GROQ_API_KEY, temperature=0.0),
        retriever=local_store.as_retriever(search_type="mmr", search_kwargs={"k": 8}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )

    loop = asyncio.get_event_loop()
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
# ENDPOINT DE VISTA PREVIA
# =======================================
@app.get("/preview/")
async def preview_file(path: str):
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": f"Archivo no encontrado en la ruta: {path}"})
    return FileResponse(path, media_type="application/pdf")

# =======================================
# ENDPOINTS DE LIMPIEZA
# =======================================
@app.post("/clear_index/")
async def clear_index():
    global PREINDEX_MAP
    for path in (UPLOAD_DIR, INDICES_BASE_DIR):
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
            except Exception as e:
                print(f"⚠️ Error al limpiar ruta {path}: {e}")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(INDICES_BASE_DIR, exist_ok=True)
    save_temp_sessions({})
    PREINDEX_MAP.clear()   # limpiar también el mapa en memoria
    return {"message": "✅ Índices de memoria, disco y archivos cargados eliminados."}

@app.post("/clear_all_sessions/")
async def clear_all_sessions():
    delete_user_conversations()
    return {"message": "✅ Sesiones de usuario eliminadas. Los índices de la BD se conservaron."}

@app.get("/health")
async def health():
    meta = load_metadata()
    sessions = load_temp_sessions()
    return {
        "active_conversations": len(meta),
        "temp_sessions": len(sessions),
        "max_documents": MAX_DOCUMENTS,
        "vision_model": VISION_MODEL,
        "text_model": TEXT_MODEL,
        "workers": MAX_WORKERS,
        "status": "healthy"
    }

# =======================================
# SERVIR FRONTEND
# =======================================
from fastapi.staticfiles import StaticFiles

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)