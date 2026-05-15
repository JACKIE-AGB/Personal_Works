from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_classic.chains import RetrievalQA
from langchain_community.document_loaders import PyPDFLoader, UnstructuredPDFLoader
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
import tempfile
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time
from typing import List

# ── Imports opcionales para extracción avanzada ───────────────────────────────
try:
    import fitz  # PyMuPDF — pip install pymupdf
    PYMUPDF_AVAILABLE = True
    print("✅ PyMuPDF disponible")
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("⚠️ PyMuPDF no instalado (pip install pymupdf)")

load_dotenv()

app = FastAPI(title="Enterprise Document API - Nomic Embed", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("⛔ GROQ_API_KEY no encontrada. Agrégala a tu archivo .env")

# ============================================
# CONFIGURACIÓN NOMIC EMBED (OPTIMIZADA)
# ============================================
print("🚀 Cargando modelo nomic-embed-text-v1.5 (potente y eficiente)...")

embeddings = HuggingFaceEmbeddings(
    model_name="nomic-ai/nomic-embed-text-v1.5",
    model_kwargs={
        'trust_remote_code': True,
        'device': 'cpu',
    },
    encode_kwargs={
        'normalize_embeddings': True,
        'truncate_dim': 768
    }
)

print("✅ Modelo cargado correctamente")

# Optimizaciones para Nomic (aprovecha el contexto de 8192 tokens)
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200
MAX_DOCUMENTS = 100        # ✅ Límite reducido a 100 documentos por carpeta
MAX_FILE_SIZE_MB = 50

FAISS_INDEX_PATH = "faiss_saved_index_nomic"
INDEX_METADATA_PATH = "index_metadata_nomic.json"

# ✅ Persistencia para el índice de PDF individual
PDF_INDEX_PATH = "faiss_pdf_index_nomic"
PDF_METADATA_PATH = "pdf_metadata_nomic.json"

# Estados en memoria
pdf_vectorstore = None
folder_vectorstore = None

indexing_status = {
    "in_progress": False,
    "total_files": 0,
    "processed_files": 0,
    "failed_files": [],
    "current_file": "",
    "start_time": None
}


# ============================================
# CARGA DE ÍNDICES AL ARRANCAR
# ============================================
@app.on_event("startup")
async def load_saved_indexes():
    """Carga en memoria los índices guardados en disco al iniciar el servidor."""
    global pdf_vectorstore, folder_vectorstore

    if os.path.exists(PDF_INDEX_PATH):
        try:
            pdf_vectorstore = FAISS.load_local(
                PDF_INDEX_PATH, embeddings, allow_dangerous_deserialization=True
            )
            print("✅ Índice PDF restaurado desde disco")
        except Exception as e:
            print(f"⚠️ No se pudo restaurar índice PDF: {e}")

    if os.path.exists(FAISS_INDEX_PATH):
        try:
            folder_vectorstore = FAISS.load_local(
                FAISS_INDEX_PATH, embeddings, allow_dangerous_deserialization=True
            )
            print("✅ Índice de carpeta restaurado desde disco")
        except Exception as e:
            print(f"⚠️ No se pudo restaurar índice de carpeta: {e}")


# ============================================
# CLASE PROCESADORA OPTIMIZADA
# ============================================
class NomicDocumentProcessor:
    """Procesador optimizado para nomic-embed-text"""

    @staticmethod
    def get_file_hash(file_path: str) -> str:
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def extract_text_pymupdf(file_path: str) -> List:
        """Extracción con PyMuPDF — mejor para PDFs con texto embebido no estándar."""
        documents = []
        doc = fitz.open(file_path)
        filename = os.path.basename(file_path)
        file_hash = NomicDocumentProcessor.get_file_hash(file_path)
        for page_num, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                documents.append(Document(
                    page_content=text,
                    metadata={
                        "source": file_path,
                        "filename": filename,
                        "page": page_num,
                        "file_hash": file_hash,
                        "extraction": "pymupdf"
                    }
                ))
        doc.close()
        return documents

    @staticmethod
    def load_pdf_safe(file_path: str) -> List:
        """
        Extracción de texto en cascada (solo texto, sin OCR ni imágenes):
          1. PyPDFLoader      — texto embebido estándar
          2. PyMuPDF (fitz)   — layouts complejos / fuentes no estándar
          3. UnstructuredPDF  — tablas, headers mixtos
        PDFs escaneados o de solo imagen son omitidos intencionalmente.
        """
        try:
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > MAX_FILE_SIZE_MB:
                print(f"⚠️ Archivo muy grande: {Path(file_path).name} ({file_size_mb:.2f}MB)")
                return []

            filename = Path(file_path).name
            documents = []

            # ── Intento 1: PyPDFLoader ────────────────────────────────────────
            try:
                loader = PyPDFLoader(file_path)
                raw = loader.load()
                documents = [d for d in raw if d.page_content and d.page_content.strip()]
                if documents:
                    print(f"   📄 {filename} → PyPDF ({len(documents)} páginas)")
            except Exception as e:
                print(f"   ⚠️ PyPDF falló en {filename}: {e}")

            # ── Intento 2: PyMuPDF ────────────────────────────────────────────
            if not documents and PYMUPDF_AVAILABLE:
                try:
                    docs = NomicDocumentProcessor.extract_text_pymupdf(file_path)
                    documents = [d for d in docs if d.page_content and d.page_content.strip()]
                    if documents:
                        print(f"   📄 {filename} → PyMuPDF ({len(documents)} páginas)")
                except Exception as e:
                    print(f"   ⚠️ PyMuPDF falló en {filename}: {e}")

            # ── Intento 3: UnstructuredPDFLoader ─────────────────────────────
            if not documents:
                try:
                    loader2 = UnstructuredPDFLoader(file_path)
                    raw2 = loader2.load()
                    documents = [d for d in raw2 if d.page_content and d.page_content.strip()]
                    if documents:
                        print(f"   📄 {filename} → Unstructured ({len(documents)} páginas)")
                except Exception as e:
                    print(f"   ⚠️ Unstructured falló en {filename}: {e}")

            # ── Sin texto → omitir (PDF escaneado / solo imagen) ─────────────
            if not documents:
                print(f"   ⏭️ {filename} → omitido (sin texto extraíble, posiblemente escaneado)")
                return []

            # Normalizar metadata
            for doc in documents:
                doc.metadata.setdefault('source', file_path)
                doc.metadata.setdefault('filename', os.path.basename(file_path))
                doc.metadata.setdefault('file_hash', NomicDocumentProcessor.get_file_hash(file_path))

            return documents

        except Exception as e:
            print(f"❌ Error cargando {Path(file_path).name}: {str(e)}")
            return []

    @staticmethod
    def process_directory_parallel(directory_path: str, max_workers: int = 4) -> tuple:
        """Procesa directorio en paralelo respetando el límite de MAX_DOCUMENTS."""
        directory_path = Path(directory_path)
        pdf_files = list(directory_path.rglob("*.pdf"))

        if len(pdf_files) > MAX_DOCUMENTS:
            print(f"⚠️ Limitando de {len(pdf_files)} a {MAX_DOCUMENTS} documentos")
            pdf_files = pdf_files[:MAX_DOCUMENTS]

        all_documents = []
        failed_files = []

        from concurrent.futures import as_completed

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(NomicDocumentProcessor.load_pdf_safe, str(f)): f
                for f in pdf_files
            }

            # ✅ Usar as_completed para procesar resultados conforme terminan
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    docs = future.result(timeout=60)
                    # ✅ Filtrar docs vacíos explícitamente
                    docs = [d for d in docs if d.page_content and d.page_content.strip()] if docs else []
                    if docs:
                        all_documents.extend(docs)
                        print(f"✅ {file_path.name} → {len(docs)} páginas válidas")
                    else:
                        print(f"⚠️ {file_path.name} → sin contenido extraíble")
                        failed_files.append(str(file_path))
                except Exception as e:
                    print(f"❌ Error/Timeout en {file_path.name}: {str(e)}")
                    failed_files.append(str(file_path))

        return all_documents, failed_files


processor = NomicDocumentProcessor()


# ============================================
# ENDPOINTS
# ============================================

@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    global pdf_vectorstore
    try:
        if not file.filename.endswith('.pdf'):
            return JSONResponse(status_code=400, content={"error": "Solo archivos PDF"})

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
                return JSONResponse(status_code=400, content={"error": f"Máximo {MAX_FILE_SIZE_MB}MB"})
            tmp.write(content)
            temp_path = tmp.name

        docs = processor.load_pdf_safe(temp_path)

        if not docs:
            return JSONResponse(status_code=500, content={"error": "No se pudo procesar el PDF"})

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ".", " ", ""],
            length_function=len
        )

        chunks = text_splitter.split_documents(docs)

        # ✅ Filtrar chunks vacíos
        chunks = [c for c in chunks if c.page_content and c.page_content.strip()]

        if not chunks:
            return JSONResponse(status_code=500, content={"error": "El PDF no contiene texto extraíble"})

        pdf_vectorstore = FAISS.from_documents(chunks, embeddings)

        # ✅ Guardar índice PDF en disco para persistencia entre sesiones
        pdf_vectorstore.save_local(PDF_INDEX_PATH)

        metadata = {
            "filename": file.filename,
            "pages": len(docs),
            "chunks": len(chunks),
            "model": "nomic-embed-text-v1.5",
            "timestamp": time.time()
        }
        with open(PDF_METADATA_PATH, 'w') as f:
            json.dump(metadata, f, indent=2)

        os.unlink(temp_path)

        return {
            "message": "PDF procesado con Nomic Embed",
            "pages": len(docs),
            "chunks": len(chunks),
            "model": "nomic-embed-text-v1.5"
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/pdf_info")
async def pdf_info():
    """Devuelve metadata del PDF indexado actualmente."""
    if os.path.exists(PDF_METADATA_PATH):
        try:
            with open(PDF_METADATA_PATH, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}


@app.post("/ask_pdf/")
async def ask_pdf(question: str = Form(...), style: str = Form("normal")):
    global pdf_vectorstore

    # ✅ Intentar cargar desde disco si no está en memoria
    if pdf_vectorstore is None:
        if os.path.exists(PDF_INDEX_PATH):
            try:
                pdf_vectorstore = FAISS.load_local(
                    PDF_INDEX_PATH, embeddings, allow_dangerous_deserialization=True
                )
            except Exception as e:
                return {"answer": f"❌ Error cargando índice PDF: {str(e)}"}
        else:
            return {"answer": "❌ Sube un PDF primero."}

    style_prompts = {
        "normal": "Responde de forma profesional, detallada y precisa usando SOLO la información del documento.",
        "amable": "Responde de manera amable, clara y servicial, explicando con paciencia.",
        "agresivo": "Responde de forma directa, concisa, sin rodeos y solo con hechos verificables."
    }

    retriever = pdf_vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={
            'k': 6,
            'fetch_k': 15,
            'lambda_mult': 0.7
        }
    )

    qa_chain = RetrievalQA.from_chain_type(
        llm=ChatGroq(model="llama-3.1-8b-instant", api_key=GROQ_API_KEY, temperature=0.2),
        retriever=retriever,
        chain_type="stuff"
    )

    response = qa_chain.invoke(f"{style_prompts[style]}\n\nPregunta: {question}")
    return {"answer": response['result']}


@app.get("/folder_doc_count")
async def folder_doc_count(folder_path: str):
    """Cuenta PDFs en una carpeta antes de indexar. Avisa si supera el límite."""
    if not os.path.exists(folder_path):
        return JSONResponse(status_code=400, content={"error": "Ruta no encontrada"})
    pdf_files = list(Path(folder_path).rglob("*.pdf"))
    count = len(pdf_files)
    return {
        "count": count,
        "limit": MAX_DOCUMENTS,
        "exceeds_limit": count > MAX_DOCUMENTS,
        "will_process": min(count, MAX_DOCUMENTS)
    }


@app.post("/index_folder/")
async def index_folder(folder_path: str = Form(...), background_tasks: BackgroundTasks = None):
    global folder_vectorstore, indexing_status

    if not os.path.exists(folder_path):
        return JSONResponse(status_code=400, content={"error": "Ruta no encontrada"})

    if indexing_status["in_progress"]:
        return JSONResponse(status_code=409, content={"error": "Indexación en progreso"})

    # ✅ Verificar límite de documentos antes de iniciar
    pdf_files = list(Path(folder_path).rglob("*.pdf"))
    total_found = len(pdf_files)

    if total_found == 0:
        return JSONResponse(status_code=400, content={"error": "No se encontraron PDFs en la carpeta"})

    background_tasks.add_task(process_folder_background_nomic, folder_path)

    return {
        "message": "Indexación con Nomic Embed iniciada",
        "total_found": total_found,
        "will_process": min(total_found, MAX_DOCUMENTS),
        "limit_applied": total_found > MAX_DOCUMENTS,
        "status_endpoint": "/indexing_status"
    }


@app.get("/indexing_status")
async def get_indexing_status():
    global indexing_status
    if indexing_status["in_progress"]:
        elapsed = time.time() - indexing_status["start_time"] if indexing_status["start_time"] else 0
        progress = (
            indexing_status["processed_files"] / indexing_status["total_files"] * 100
            if indexing_status["total_files"] > 0 else 0
        )
        return {
            "in_progress": True,
            "total_files": indexing_status["total_files"],
            "processed_files": indexing_status["processed_files"],
            "progress_percentage": round(progress, 2),
            "current_file": indexing_status["current_file"],
            "failed_files": indexing_status["failed_files"],
            "elapsed_seconds": round(elapsed, 1)
        }
    else:
        return {
            "in_progress": False,
            "total_files": indexing_status["total_files"],
            "processed_files": indexing_status["processed_files"],
            "failed_files": indexing_status["failed_files"]
        }


async def process_folder_background_nomic(folder_path: str):
    global folder_vectorstore, indexing_status

    indexing_status = {
        "in_progress": True,
        "total_files": 0,
        "processed_files": 0,
        "failed_files": [],
        "current_file": "",
        "start_time": time.time()
    }

    try:
        all_pdfs = list(Path(folder_path).rglob("*.pdf"))
        # ✅ Aplicar límite de 100 documentos
        capped_pdfs = all_pdfs[:MAX_DOCUMENTS]
        indexing_status["total_files"] = len(capped_pdfs)

        if indexing_status["total_files"] == 0:
            indexing_status["in_progress"] = False
            return

        all_documents, failed_files = processor.process_directory_parallel(folder_path, max_workers=4)

        indexing_status["failed_files"] = failed_files
        indexing_status["processed_files"] = indexing_status["total_files"] - len(failed_files)

        if not all_documents:
            indexing_status["in_progress"] = False
            return

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ".", " ", ""],
            length_function=len
        )

        chunks = text_splitter.split_documents(all_documents)

        # ✅ Filtrar chunks vacíos para evitar "list index out of range" en FAISS
        chunks = [c for c in chunks if c.page_content and c.page_content.strip()]

        if not chunks:
            print("❌ No se generaron chunks válidos tras el split")
            indexing_status["failed_files"].append("ERROR: ningún chunk válido generado")
            indexing_status["in_progress"] = False
            return

        print(f"📊 Creando vectorstore con {len(chunks)} chunks válidos...")
        folder_vectorstore = FAISS.from_documents(chunks, embeddings)
        folder_vectorstore.save_local(FAISS_INDEX_PATH)

        metadata = {
            "folder_path": folder_path,
            "total_found": len(all_pdfs),
            "total_files": indexing_status["total_files"],
            "processed_files": indexing_status["processed_files"],
            "failed_files": failed_files,
            "total_chunks": len(chunks),
            "model": "nomic-embed-text-v1.5",
            "chunk_size": CHUNK_SIZE,
            "limit_applied": len(all_pdfs) > MAX_DOCUMENTS,
            "timestamp": time.time()
        }

        with open(INDEX_METADATA_PATH, 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"✅ Indexación completa: {len(chunks)} chunks, {indexing_status['processed_files']} archivos")

    except Exception as e:
        print(f"❌ Error en indexación: {str(e)}")
        indexing_status["failed_files"].append(f"ERROR_GENERAL: {str(e)}")
    finally:
        indexing_status["in_progress"] = False
        indexing_status["current_file"] = ""


@app.get("/folder_info")
async def folder_info():
    """Devuelve metadata del índice de carpeta guardado."""
    if os.path.exists(INDEX_METADATA_PATH):
        try:
            with open(INDEX_METADATA_PATH, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}


@app.post("/ask_folder/")
async def ask_folder(question: str = Form(...)):
    global folder_vectorstore

    # ✅ Intentar cargar desde disco si no está en memoria
    if folder_vectorstore is None:
        if os.path.exists(FAISS_INDEX_PATH):
            try:
                print("🔄 Cargando índice persistente de Nomic...")
                folder_vectorstore = FAISS.load_local(
                    FAISS_INDEX_PATH,
                    embeddings,
                    allow_dangerous_deserialization=True
                )
                print("✅ Índice cargado correctamente")
            except Exception as e:
                return {"answer": f"❌ Error cargando índice: {str(e)}"}
        else:
            return {"answer": "❌ Indexa una carpeta primero."}

    template = """Eres un Analista de Documentos experto para una empresa de alto nivel.
    Usa el contexto para responder con precisión y SIEMPRE cita el archivo fuente específico.
    
    Contexto: {context}
    
    Pregunta: {question}
    
    Instrucciones:
    1. Responde basándote ÚNICAMENTE en el contexto proporcionado
    2. Si no encuentras la información, dilo claramente
    3. Siempre menciona qué archivo(s) contienen la información
    4. Sé específico y profesional
    5. Aprovecha el contexto completo que se te proporciona (Nomic permite hasta 8192 tokens)
    
    Respuesta:"""

    prompt = PromptTemplate(template=template, input_variables=["context", "question"])

    retriever = folder_vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={
            'k': 8,
            'fetch_k': 25,
            'lambda_mult': 0.6
        }
    )

    chain = RetrievalQA.from_chain_type(
        llm=ChatGroq(model="llama-3.1-8b-instant", api_key=GROQ_API_KEY, temperature=0.1),
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt}
    )

    result = chain.invoke({"query": question})

    sources = {}
    for doc in result["source_documents"]:
        filename = doc.metadata.get('filename', os.path.basename(doc.metadata.get('source', 'Unknown')))
        sources[filename] = sources.get(filename, 0) + 1

    sources_text = "\n\n**📚 Fuentes consultadas (Nomic Embed):**\n" + \
                   "\n".join([f"📄 `{name}` (referenciado {count} veces)" for name, count in sources.items()])

    return {"answer": result["result"] + sources_text}


@app.post("/clear_pdf/")
async def clear_pdf():
    """Elimina el índice PDF persistente."""
    global pdf_vectorstore
    pdf_vectorstore = None
    if os.path.exists(PDF_INDEX_PATH):
        shutil.rmtree(PDF_INDEX_PATH)
    if os.path.exists(PDF_METADATA_PATH):
        os.remove(PDF_METADATA_PATH)
    return {"message": "Índice PDF eliminado correctamente"}


@app.post("/clear_index/")
async def clear_index():
    global folder_vectorstore, indexing_status
    folder_vectorstore = None
    indexing_status = {
        "in_progress": False,
        "total_files": 0,
        "processed_files": 0,
        "failed_files": [],
        "current_file": "",
        "start_time": None
    }

    if os.path.exists(FAISS_INDEX_PATH):
        shutil.rmtree(FAISS_INDEX_PATH)
    if os.path.exists(INDEX_METADATA_PATH):
        os.remove(INDEX_METADATA_PATH)

    return {"message": "Índice Nomic eliminado correctamente"}


@app.get("/health")
async def health():
    return {
        "pdf_ready": pdf_vectorstore is not None or os.path.exists(PDF_INDEX_PATH),
        "folder_ready": folder_vectorstore is not None or os.path.exists(FAISS_INDEX_PATH),
        "indexing_in_progress": indexing_status["in_progress"],
        "embedding_model": "nomic-embed-text-v1.5",
        "chunk_size": CHUNK_SIZE,
        "max_documents": MAX_DOCUMENTS
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_unified:app", host="127.0.0.1", port=8001, reload=True)