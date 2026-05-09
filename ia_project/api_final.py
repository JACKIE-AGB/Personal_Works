"""
api_unified.py  —  Backend FastAPI para el Asistente IA Unificado
Requiere en .env:  GROQ_API_KEY=gsk_...
Ejecutar con:      uvicorn api_unified:app --host 127.0.0.1 --port 8001 --reload
"""

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# LangChain — imports correctos (sin langchain_classic que no existe)
from langchain_text_splitters import CharacterTextSplitter, RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_classic.chains import RetrievalQA                         # ✅ FIX: langchain.chains, no langchain_classic
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings          # ✅ FIX: langchain_huggingface (nuevo paquete)

import tempfile
import os
import shutil
from dotenv import load_dotenv

# ─── Configuración ────────────────────────────────────────────────────────────
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError(
        "⛔ GROQ_API_KEY no encontrada. "
        "Crea un archivo .env con: GROQ_API_KEY=gsk_..."
    )

FAISS_INDEX_PATH = "faiss_saved_index"
GROQ_MODEL       = "llama-3.1-8b-instant"

# ─── Embeddings (se comparten entre ambos modos) ──────────────────────────────
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="Unified Document API", version="1.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # En producción, limita al dominio real
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Estado en memoria ────────────────────────────────────────────────────────
pdf_vectorstore:    FAISS | None = None
folder_vectorstore: FAISS | None = None

# ─── Carga automática del índice persistente al arrancar ──────────────────────
if os.path.exists(FAISS_INDEX_PATH):
    try:
        folder_vectorstore = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True,
        )
        print("✅ Índice de carpetas persistente cargado desde disco.")
    except Exception as exc:
        print(f"⚠️  No se pudo cargar el índice guardado: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS — PDF INDIVIDUAL
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    """Recibe un PDF, lo divide en chunks y construye un índice FAISS en memoria."""
    global pdf_vectorstore
    tmp_path = None
    try:
        # Guardar temporalmente el archivo subido
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        loader = PyPDFLoader(tmp_path)
        raw_docs = loader.load()

        splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = splitter.split_documents(raw_docs)

        pdf_vectorstore = FAISS.from_documents(docs, embeddings)
        return {"message": f"PDF procesado correctamente ({len(docs)} fragmentos)."}

    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/ask_pdf/")
async def ask_pdf(question: str = Form(...), style: str = Form("normal")):
    """Responde preguntas sobre el PDF cargado."""
    if pdf_vectorstore is None:
        return {"answer": "❌ Sube y procesa un PDF primero."}

    style_prompts = {
        "normal":   "Responde de forma profesional y clara.",
        "amable":   "Responde de manera amable, empática y muy útil.",
        "agresivo": "Responde de forma directa, concisa y sin rodeos.",
    }
    style_instruction = style_prompts.get(style, style_prompts["normal"])

    try:
        llm = ChatGroq(
            model=GROQ_MODEL,
            api_key=GROQ_API_KEY,
            temperature=0.3,
        )

        template = (
            f"{style_instruction}\n\n"
            "Usa el siguiente contexto para responder la pregunta del usuario.\n"
            "Contexto:\n{context}\n\n"
            "Pregunta: {question}\n"
            "Respuesta:"
        )
        prompt = PromptTemplate(
            template=template,
            input_variables=["context", "question"],
        )

        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=pdf_vectorstore.as_retriever(search_kwargs={"k": 4}),
            chain_type_kwargs={"prompt": prompt},
        )

        response = qa_chain.invoke({"query": question})
        return {"answer": response.get("result", "Sin respuesta")}

    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


# ══════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS — CARPETA DE DOCUMENTOS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/index_folder/")
async def index_folder(folder_path: str = Form(...)):
    """
    Indexa todos los PDFs dentro de folder_path (recursivo).
    Persiste el índice en disco para reutilizarlo entre reinicios.
    """
    global folder_vectorstore

    if not os.path.exists(folder_path):
        return JSONResponse(
            status_code=400,
            content={"error": f"La ruta no existe: {folder_path}"},
        )

    try:
        loader = DirectoryLoader(
            folder_path,
            glob="**/*.pdf",
            loader_cls=PyPDFLoader,
        )
        raw_documents = loader.load()

        if not raw_documents:
            return JSONResponse(
                status_code=400,
                content={"error": "No se encontraron archivos PDF en la carpeta."},
            )

        # Añadir nombre de archivo al contenido para que el LLM pueda citarlo
        for doc in raw_documents:
            file_name = os.path.basename(doc.metadata.get("source", "desconocido"))
            doc.page_content = f"ARCHIVO: {file_name}\nCONTENIDO: {doc.page_content}"

        splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200)
        docs = splitter.split_documents(raw_documents)

        folder_vectorstore = FAISS.from_documents(docs, embeddings)
        folder_vectorstore.save_local(FAISS_INDEX_PATH)

        unique_files = sorted(
            set(os.path.basename(d.metadata["source"]) for d in raw_documents)
        )
        return {
            "message": f"Indexación completa: {len(unique_files)} archivos, {len(docs)} fragmentos.",
            "files": unique_files,
        }

    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/ask_folder/")
async def ask_folder(question: str = Form(...)):
    """Responde preguntas usando el índice de la carpeta, citando la fuente."""
    if folder_vectorstore is None:
        return {"answer": "❌ Indexa una carpeta primero."}

    template = (
        "Eres un Analista de Documentos experto. "
        "Usa el contexto para responder con precisión e identifica siempre el archivo fuente.\n\n"
        "Contexto:\n{context}\n\n"
        "Pregunta: {question}\n"
        "Respuesta:"
    )
    prompt = PromptTemplate(template=template, input_variables=["context", "question"])

    try:
        llm = ChatGroq(
            model=GROQ_MODEL,
            api_key=GROQ_API_KEY,
            temperature=0.1,
        )

        chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=folder_vectorstore.as_retriever(
                search_type="mmr",
                search_kwargs={"k": 6},
            ),
            return_source_documents=True,
            chain_type_kwargs={"prompt": prompt},
        )

        result = chain.invoke({"query": question})

        sources = sorted(
            set(
                os.path.basename(doc.metadata.get("source", "desconocido"))
                for doc in result.get("source_documents", [])
            )
        )
        sources_str = (
            "\n\n**📍 Ubicación del documento:**\n"
            + "\n".join(f"📄 `{s}`" for s in sources)
        ) if sources else ""

        return {"answer": result.get("result", "Sin respuesta") + sources_str}

    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


# ══════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS — UTILIDAD
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/clear_index/")
async def clear_index():
    """Elimina el índice de la carpeta de memoria y disco."""
    global folder_vectorstore
    folder_vectorstore = None
    if os.path.exists(FAISS_INDEX_PATH):
        shutil.rmtree(FAISS_INDEX_PATH)
    return {"message": "Índice eliminado correctamente."}


@app.get("/health")
async def health():
    """Verifica el estado de los índices activos."""
    return {
        "status": "ok",
        "pdf_ready":    pdf_vectorstore is not None,
        "folder_ready": folder_vectorstore is not None,
    }


# ─── Punto de entrada ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001, reload=True)