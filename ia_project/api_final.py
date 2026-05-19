from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="CFE Intelligent Document & Vision API", version="3.0")

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

# ==========================================================
# CONFIGURACIÓN DE MODELOS
# Modelo de visión: llama-3.2-90b para máxima calidad en planos
# Modelo de texto: llama-3.3-70b-versatile — mejor balance velocidad/inteligencia en Groq
# ==========================================================
VISION_MODEL = "llama-3.2-90b-vision-instruct"
TEXT_MODEL   = "llama-3.3-70b-versatile"

MAX_DOCUMENTS    = 100
PDF_INDEX_PATH   = "pdf_index"
FOLDER_INDEX_PATH = "folder_index"

# ── Embeddings: multilingual-e5-small → ~3x más rápido que large, calidad similar ──
embeddings = HuggingFaceEmbeddings(
    model_name="intfloat/multilingual-e5-small",
    encode_kwargs={"normalize_embeddings": True},
    model_kwargs={"device": "cpu"},
)

# ── Pool de hilos para paralelismo en I/O-bound tasks ──
MAX_WORKERS = min(8, (os.cpu_count() or 4) * 2)
_executor   = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# ── Semáforo para limitar llamadas concurrentes a la API de Groq (evita rate-limits) ──
# Ajusta según el tier de tu cuenta; 6 es seguro para cuentas de producción
GROQ_CONCURRENCY = 6

pdf_vectorstore    = None
folder_vectorstore = None

# ── Carga de índices persistentes al inicio ──
for index_path, label in [(PDF_INDEX_PATH, "PDF"), (FOLDER_INDEX_PATH, "carpetas")]:
    if os.path.exists(index_path):
        try:
            store = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
            if index_path == PDF_INDEX_PATH:
                pdf_vectorstore = store
            else:
                folder_vectorstore = store
            print(f"✅ Índice de {label} cargado desde disco.")
        except Exception as e:
            print(f"⚠️ No se pudo cargar índice de {label}: {e}")


# ==========================================================
# EXTRACCIÓN RÁPIDA DE PÁGINAS PDF (fase 1 — un solo hilo, fitz no es thread-safe)
# ==========================================================
def _extract_pages_data(file_path: str) -> list[dict]:
    """
    Abre el PDF UNA SOLA VEZ y extrae texto + bytes de imagen de cada página.
    Las imágenes se renderizan en 100 DPI (suficiente para OCR/descripción técnica)
    SOLO si la página tiene imágenes Y poco texto extraíble.
    Devuelve una lista de dicts listos para la fase paralela.
    """
    pages_data = []
    file_name  = os.path.basename(file_path)

    with fitz.open(file_path) as pdf:
        for page_num, page in enumerate(pdf):
            text       = page.get_text().strip()
            has_images = len(page.get_images()) > 0

            # Criterio de visión: imagen presente + texto insuficiente
            needs_vision = has_images and len(text) < 300

            img_b64 = None
            if needs_vision:
                pix    = page.get_pixmap(dpi=100)  # 100 DPI — rápido y legible
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


# ==========================================================
# ANÁLISIS CON VISIÓN (fase 2 — llamadas API en paralelo)
# ==========================================================
def _analyze_page(page_data: dict) -> Document:
    """
    Construye el Document de una página.
    Si necesita visión, llama a la API de Groq con una instancia local (thread-safe).
    """
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


# ==========================================================
# PIPELINE PRINCIPAL DE EXTRACCIÓN (combina fases 1 y 2)
# ==========================================================
def extract_pdf_parallel(file_path: str) -> list[Document]:
    """
    1. Extrae datos de todas las páginas de forma secuencial y segura (fitz).
    2. Procesa las llamadas de visión en paralelo con ThreadPoolExecutor.
    El resultado neto: el tiempo total ≈ tiempo de la página de visión más lenta,
    no la suma de todas.
    """
    pages_data = _extract_pages_data(file_path)

    documents = [None] * len(pages_data)

    # Páginas que no necesitan visión: procesadas sin API call, casi instantáneo
    text_only  = [p for p in pages_data if not p["needs_vision"]]
    need_vision = [p for p in pages_data if p["needs_vision"]]

    for pd_item in text_only:
        documents[pd_item["page_num"]] = _analyze_page(pd_item)

    # Páginas con visión: llamadas a API en paralelo
    if need_vision:
        with ThreadPoolExecutor(max_workers=GROQ_CONCURRENCY) as vis_pool:
            futures = {
                vis_pool.submit(_analyze_page, pd_item): pd_item["page_num"]
                for pd_item in need_vision
            }
            for future in as_completed(futures):
                page_num = futures[future]
                try:
                    documents[page_num] = future.result()
                except Exception as e:
                    print(f"⚠️ Error en pág.{page_num}: {e}")

    return [doc for doc in documents if doc is not None]


def _process_single_pdf(file_path: str) -> list[Document]:
    """Wrapper seguro para usar en pool de carpetas."""
    try:
        return extract_pdf_parallel(file_path)
    except Exception as e:
        print(f"⚠️ Omitiendo {os.path.basename(file_path)}: {e}")
        return []


# ==========================================================
# ENDPOINTS: PDF INDIVIDUAL
# ==========================================================
@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    global pdf_vectorstore
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            temp_path = tmp.name

        loop = asyncio.get_event_loop()
        raw_docs = await loop.run_in_executor(
            _executor, partial(extract_pdf_parallel, temp_path)
        )

        splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)
        docs = splitter.split_documents(raw_docs)

        pdf_vectorstore = FAISS.from_documents(docs, embeddings)
        pdf_vectorstore.save_local(PDF_INDEX_PATH)

        os.unlink(temp_path)
        return {
            "message": "✅ PDF procesado e indexado correctamente.",
            "pages":   len(raw_docs),
            "chunks":  len(docs),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/ask_pdf/")
async def ask_pdf(question: str = Form(...), style: str = Form("normal")):
    global pdf_vectorstore
    if pdf_vectorstore is None:
        return {"answer": "❌ Primero sube y procesa un PDF"}

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
        retriever=pdf_vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": 5}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )

    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, partial(chain.invoke, {"query": question}))
    return {"answer": result["result"]}


# ==========================================================
# ENDPOINTS: CARPETAS MASIVAS (PDFs procesados en paralelo)
# ==========================================================
@app.post("/index_folder/")
async def index_folder(folder_path: str = Form(...)):
    global folder_vectorstore
    if not os.path.exists(folder_path):
        return JSONResponse(status_code=400, content={"error": "La ruta especificada no existe en el servidor."})

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

        loop = asyncio.get_event_loop()

        # ── Procesar todos los PDFs en paralelo (un hilo por archivo) ──
        futures = [
            loop.run_in_executor(_executor, _process_single_pdf, fp)
            for fp in pdf_files
        ]
        results = await asyncio.gather(*futures, return_exceptions=True)

        all_docs = []
        for r in results:
            if isinstance(r, list):
                all_docs.extend(r)

        if not all_docs:
            return JSONResponse(status_code=500, content={"error": "No se pudo extraer contenido de los PDFs."})

        splitter = RecursiveCharacterTextSplitter(chunk_size=1800, chunk_overlap=200)
        docs     = splitter.split_documents(all_docs)

        folder_vectorstore = FAISS.from_documents(docs, embeddings)
        folder_vectorstore.save_local(FOLDER_INDEX_PATH)

        unique_files = sorted(set(os.path.basename(d.metadata["source"]) for d in all_docs))
        return {
            "message":   "✅ Indexación recursiva completada.",
            "documents": len(unique_files),
            "chunks":    len(docs),
            "files":     unique_files,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/ask_folder/")
async def ask_folder(question: str = Form(...)):
    global folder_vectorstore
    if folder_vectorstore is None:
        return {"answer": "❌ Primero indexa una carpeta desde el panel técnico"}

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
        retriever=folder_vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": 8}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )

    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, partial(chain.invoke, {"query": question}))
    sources = sorted(set(os.path.basename(d.metadata["source"]) for d in result["source_documents"]))

    return {
        "answer":  result["result"],
        "sources": sources,
    }


# ==========================================================
# CONTROL Y LIMPIEZA
# ==========================================================
@app.post("/clear_index/")
async def clear_index():
    global pdf_vectorstore, folder_vectorstore
    pdf_vectorstore = folder_vectorstore = None

    for path in (PDF_INDEX_PATH, FOLDER_INDEX_PATH):
        if os.path.exists(path):
            shutil.rmtree(path)

    return {"message": "✅ Índices de memoria y disco eliminados correctamente."}


@app.get("/health")
async def health():
    return {
        "pdf_ready":      pdf_vectorstore is not None,
        "folder_ready":   folder_vectorstore is not None,
        "max_documents":  MAX_DOCUMENTS,
        "vision_model":   VISION_MODEL,
        "text_model":     TEXT_MODEL,
        "embeddings":     "intfloat/multilingual-e5-small",
        "workers":        MAX_WORKERS,
        "groq_concurrency": GROQ_CONCURRENCY,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
