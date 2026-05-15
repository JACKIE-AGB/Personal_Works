from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_classic.chains import RetrievalQA
from langchain_community.document_loaders import PyPDFLoader
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import time
import io
from typing import List
from PIL import Image

# ── CONFIGURACIÓN DE EXTRACCIÓN Y CAPA OCR ──────────────────────────────────
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
    print("✅ PyMuPDF disponible")
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("⚠️ PyMuPDF no instalado (pip install pymupdf)")

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    
    # Auto-detección de la ruta estándar de Tesseract en Windows
    WINDOWS_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(WINDOWS_TESSERACT_PATH):
        pytesseract.pytesseract.tesseract_cmd = WINDOWS_TESSERACT_PATH
        print(f"🎯 Tesseract OCR vinculado con éxito: {WINDOWS_TESSERACT_PATH}")
    else:
        print("⚠️ Tesseract binario no detectado en la ruta por defecto de Windows.")
except ImportError:
    TESSERACT_AVAILABLE = False
    print("⚠️ pytesseract no instalado (pip install pytesseract pillow)")

load_dotenv()

app = FastAPI(title="Enterprise Document API - Nomic Embed & Planos OCR", version="3.0")

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

print("🚀 Cargando modelo nomic-embed-text-v1.5...")
embeddings = HuggingFaceEmbeddings(
    model_name="nomic-ai/nomic-embed-text-v1.5",
    model_kwargs={'trust_remote_code': True, 'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True, 'truncate_dim': 768}
)
print("✅ Modelo cargado correctamente")

CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200
MAX_DOCUMENTS = 100        
MAX_FILE_SIZE_MB = 120  # Límite expandido para planos pesados de ingeniería

FAISS_INDEX_PATH = "faiss_saved_index_nomic"
INDEX_METADATA_PATH = "index_metadata_nomic.json"
PDF_INDEX_PATH = "faiss_pdf_index_nomic"
PDF_METADATA_PATH = "pdf_metadata_nomic.json"

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

@app.on_event("startup")
async def load_saved_indexes():
    global pdf_vectorstore, folder_vectorstore
    if os.path.exists(PDF_INDEX_PATH):
        try:
            pdf_vectorstore = FAISS.load_local(PDF_INDEX_PATH, embeddings, allow_dangerous_deserialization=True)
            print("✅ Índice PDF restaurado")
        except Exception as e:
            print(f"⚠️ No se pudo restaurar índice PDF: {e}")

    if os.path.exists(FAISS_INDEX_PATH):
        try:
            folder_vectorstore = FAISS.load_local(FAISS_INDEX_PATH, embeddings, allow_dangerous_deserialization=True)
            print("✅ Índice de carpeta restaurado")
        except Exception as e:
            print(f"⚠️ No se pudo restaurar índice de carpeta: {e}")


class NomicDocumentProcessor:
    @staticmethod
    def get_file_hash(file_path: str) -> str:
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def load_pdf_with_ocr_fallback(file_path: str) -> List[Document]:
        """
        Procesador híbrido inteligente:
        Extrae texto digital directo. Si no encuentra o el archivo es un plano,
        ejecuta una rasterización en alta resolución y procesa con OCR Tesseract.
        """
        filename = Path(file_path).name
        file_hash = NomicDocumentProcessor.get_file_hash(file_path)
        documents = []

        if not PYMUPDF_AVAILABLE:
            try:
                loader = PyPDFLoader(file_path)
                return loader.load()
            except Exception as e:
                print(f"❌ Error en cargador fallback para {filename}: {e}")
                return []

        try:
            doc = fitz.open(file_path)
            for page_num, page in enumerate(doc):
                # Intentar texto digital embebido estándar
                text = page.get_text("text").strip()
                extraction_method = "digital_layer"

                # Si es un plano de ingeniería o texto nativo casi nulo (menos de 15 caracteres válidos)
                clean_chars = [c for c in text if c.isalnum()]
                if not text or len(clean_chars) < 15:
                    if TESSERACT_AVAILABLE:
                        try:
                            # Renderizado de alta fidelidad (Matrix 2.5x2.5) para capturar micro-textos en planos
                            pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
                            img_data = pix.tobytes("png")
                            img = Image.open(io.BytesIO(img_data))
                            
                            # OCR bilingüe para soportar nomenclaturas técnicas y códigos
                            ocr_text = pytesseract.image_to_string(img, lang="spa+eng")
                            if ocr_text.strip():
                                text = ocr_text.strip()
                                extraction_method = "ocr_tesseract_high_res"
                        except Exception as ocr_err:
                            print(f"   ⚠️ Falló OCR en {filename} Pág {page_num+1}: {ocr_err}")
                    else:
                        extraction_method = "skipped_no_ocr_installed"

                # Si logramos extraer datos por cualquiera de los dos métodos, guardamos la página
                if text and any(char.isalnum() for char in text):
                    documents.append(Document(
                        page_content=text,
                        metadata={
                            "source": file_path,
                            "filename": filename,
                            "page": page_num + 1,
                            "file_hash": file_hash,
                            "extraction": extraction_method
                        }
                    ))
            doc.close()
            return documents
        except Exception as e:
            print(f"❌ Error crítico leyendo plano {filename}: {str(e)}")
            return []


processor = NomicDocumentProcessor()

@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    global pdf_vectorstore
    try:
        if not file.filename.endswith('.pdf'):
            return JSONResponse(status_code=400, content={"error": "Solo archivos PDF"})

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            temp_path = tmp.name

        docs = processor.load_pdf_with_ocr_fallback(temp_path)
        if not docs:
            return JSONResponse(status_code=400, content={"error": "El PDF no contiene texto ni OCR procesable."})

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ".", " ", ""], length_function=len
        )
        chunks = text_splitter.split_documents(docs)
        chunks = [c for c in chunks if c.page_content and any(char.isalnum() for char in c.page_content)]

        if not chunks:
            return JSONResponse(status_code=400, content={"error": "No se generaron fragmentos útiles."})

        pdf_vectorstore = FAISS.from_documents(chunks, embeddings)
        pdf_vectorstore.save_local(PDF_INDEX_PATH)

        metadata = {"filename": file.filename, "pages": len(docs), "chunks": len(chunks), "model": "nomic-embed-text-v1.5", "timestamp": time.time()}
        with open(PDF_METADATA_PATH, 'w') as f:
            json.dump(metadata, f, indent=2)

        os.unlink(temp_path)
        return {"message": "Archivo indexado correctamente", "pages": len(docs), "chunks": len(chunks)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/pdf_info")
async def pdf_info():
    if os.path.exists(PDF_METADATA_PATH):
        try:
            with open(PDF_METADATA_PATH, 'r') as f: return json.load(f)
        except: pass
    return {}


@app.post("/ask_pdf/")
async def ask_pdf(question: str = Form(...), style: str = Form("normal")):
    global pdf_vectorstore
    if pdf_vectorstore is None:
        if os.path.exists(PDF_INDEX_PATH):
            pdf_vectorstore = FAISS.load_local(PDF_INDEX_PATH, embeddings, allow_dangerous_deserialization=True)
        else:
            return {"answer": "❌ Sube un PDF primero."}

    style_prompts = {
        "normal": "Responde de forma profesional usando la información del documento.",
        "amable": "Responde de manera amable y detallada.",
        "agresivo": "Responde de forma directa y al grano."
    }
    retriever = pdf_vectorstore.as_retriever(search_type="mmr", search_kwargs={'k': 6, 'fetch_k': 15, 'lambda_mult': 0.7})
    qa_chain = RetrievalQA.from_chain_type(
        llm=ChatGroq(model="llama-3.1-8b-instant", api_key=GROQ_API_KEY, temperature=0.2),
        retriever=retriever, chain_type="stuff"
    )
    response = qa_chain.invoke(f"{style_prompts[style]}\n\nPregunta: {question}")
    return {"answer": response['result']}


@app.get("/folder_doc_count")
async def folder_doc_count(folder_path: str):
    if not os.path.exists(folder_path):
        return JSONResponse(status_code=400, content={"error": "Ruta no encontrada"})
    pdf_files = list(Path(folder_path).rglob("*.pdf"))
    count = len(pdf_files)
    return {"count": count, "limit": MAX_DOCUMENTS, "exceeds_limit": count > MAX_DOCUMENTS, "will_process": min(count, MAX_DOCUMENTS)}


@app.post("/index_folder/")
async def index_folder(folder_path: str = Form(...), background_tasks: BackgroundTasks = None):
    global indexing_status
    if not os.path.exists(folder_path):
        return JSONResponse(status_code=400, content={"error": "Ruta no encontrada"})
    if indexing_status["in_progress"]:
        return JSONResponse(status_code=409, content={"error": "Indexación en progreso"})

    pdf_files = list(Path(folder_path).rglob("*.pdf"))
    if len(pdf_files) == 0:
        return JSONResponse(status_code=400, content={"error": "No se encontraron PDFs"})

    background_tasks.add_task(process_folder_background_nomic, folder_path)
    return {"message": "Indexación con soporte OCR de planos iniciada", "total_found": len(pdf_files), "will_process": min(len(pdf_files), MAX_DOCUMENTS), "status_endpoint": "/indexing_status"}


@app.get("/indexing_status")
async def get_indexing_status():
    global indexing_status
    if indexing_status["in_progress"]:
        elapsed = time.time() - indexing_status["start_time"] if indexing_status["start_time"] else 0
        progress = (indexing_status["processed_files"] / indexing_status["total_files"] * 100) if indexing_status["total_files"] > 0 else 0
        return {
            "in_progress": True,
            "total_files": indexing_status["total_files"],
            "processed_files": indexing_status["processed_files"],
            "progress_percentage": round(progress, 2),
            "current_file": indexing_status["current_file"],
            "failed_files": indexing_status["failed_files"],
            "elapsed_seconds": round(elapsed, 1)
        }
    return {"in_progress": False, "total_files": indexing_status["total_files"], "processed_files": indexing_status["processed_files"], "failed_files": indexing_status["failed_files"]}


async def process_folder_background_nomic(folder_path: str):
    global folder_vectorstore, indexing_status
    
    all_pdfs = list(Path(folder_path).rglob("*.pdf"))
    capped_pdfs = all_pdfs[:MAX_DOCUMENTS]
    
    indexing_status = {
        "in_progress": True,
        "total_files": len(capped_pdfs),
        "processed_files": 0,
        "failed_files": [],
        "current_file": "Iniciando OCR en lote para planos...",
        "start_time": time.time()
    }

    try:
        all_documents = []
        # Multi-threading controlado para balancear el procesamiento de imágenes por OCR
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_file = {executor.submit(processor.load_pdf_with_ocr_fallback, str(f)): f for f in capped_pdfs}
            
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                indexing_status["current_file"] = file_path.name
                try:
                    docs = future.result(timeout=120)  # Tolerancia alta para OCR de planos grandes (A0/A1)
                    if docs:
                        all_documents.extend(docs)
                    else:
                        indexing_status["failed_files"].append(f"{file_path.name} (Sin contenido legible por OCR)")
                except Exception as e:
                    indexing_status["failed_files"].append(f"{file_path.name} (Error: {str(e)})")
                
                indexing_status["processed_files"] += 1

        if not all_documents:
            indexing_status["failed_files"].append("ERROR: Ningún plano o documento arrojó texto legible.")
            indexing_status["in_progress"] = False
            return

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, separators=["\n\n", "\n", ".", " ", ""], length_function=len)
        chunks = text_splitter.split_documents(all_documents)
        chunks = [c for c in chunks if c.page_content and any(char.isalnum() for char in c.page_content)]

        if not chunks:
            indexing_status["failed_files"].append("ERROR: Cero fragmentos generados tras segmentación.")
            indexing_status["in_progress"] = False
            return

        print(f"📊 Generando vectores Nomic para {len(chunks)} secciones extraídas...")
        folder_vectorstore = FAISS.from_documents(chunks, embeddings)
        folder_vectorstore.save_local(FAISS_INDEX_PATH)

        metadata = {"folder_path": folder_path, "total_found": len(all_pdfs), "total_files": indexing_status["total_files"], "processed_files": indexing_status["processed_files"], "failed_files": indexing_status["failed_files"], "total_chunks": len(chunks), "model": "nomic-embed-text-v1.5", "timestamp": time.time()}
        with open(INDEX_METADATA_PATH, 'w') as f:
            json.dump(metadata, f, indent=2)

    except Exception as e:
        print(f"❌ Error general en segundo plano: {str(e)}")
        indexing_status["failed_files"].append(f"ERROR_SISTEMA: {str(e)}")
    finally:
        indexing_status["in_progress"] = False
        indexing_status["current_file"] = ""


@app.post("/ask_folder/")
async def ask_folder(question: str = Form(...)):
    global folder_vectorstore
    if folder_vectorstore is None:
        if os.path.exists(FAISS_INDEX_PATH):
            folder_vectorstore = FAISS.load_local(FAISS_INDEX_PATH, embeddings, allow_dangerous_deserialization=True)
        else:
            return {"answer": "❌ Indexa una carpeta primero."}

    template = """Eres un Analista Técnico de Ingeniería experto. Tu trabajo es cruzar la información de las especificaciones y los planos indexados.
    Responde con precisión milimétrica usando el contexto. Siempre debes indicar de qué plano o documento obtuviste el dato y en qué página está.
    
    Contexto: {context}
    Pregunta: {question}
    Respuesta técnica estructurada:"""
    
    prompt = PromptTemplate(template=template, input_variables=["context", "question"])
    retriever = folder_vectorstore.as_retriever(search_type="mmr", search_kwargs={'k': 8, 'fetch_k': 25, 'lambda_mult': 0.6})
    chain = RetrievalQA.from_chain_type(llm=ChatGroq(model="llama-3.1-8b-instant", api_key=GROQ_API_KEY, temperature=0.1), retriever=retriever, return_source_documents=True, chain_type_kwargs={"prompt": prompt})
    
    result = chain.invoke({"query": question})
    sources = {}
    for doc in result["source_documents"]:
        filename = doc.metadata.get('filename', os.path.basename(doc.metadata.get('source', 'Desconocido')))
        page = doc.metadata.get('page', '?')
        ext_method = "Lectura OCR de Plano" if "ocr" in doc.metadata.get('extraction', '') else "Documento Digital"
        key = f"📄 `{filename}` (Pág. {page}) — *[{ext_method}]*"
        sources[key] = sources.get(key, 0) + 1

    sources_text = "\n\n**📚 Planos y Documentos de Origen Cruzados:**\n" + "\n".join([f"- {name}" for name in sources.keys()])
    return {"answer": result["result"] + sources_text}


@app.post("/clear_pdf/")
async def clear_pdf():
    global pdf_vectorstore
    pdf_vectorstore = None
    if os.path.exists(PDF_INDEX_PATH): shutil.rmtree(PDF_INDEX_PATH)
    if os.path.exists(PDF_METADATA_PATH): os.remove(PDF_METADATA_PATH)
    return {"message": "Índice PDF eliminado"}


@app.post("/clear_index/")
async def clear_index():
    global folder_vectorstore, indexing_status
    folder_vectorstore = None
    indexing_status = {"in_progress": False, "total_files": 0, "processed_files": 0, "failed_files": [], "current_file": "", "start_time": None}
    if os.path.exists(FAISS_INDEX_PATH): shutil.rmtree(FAISS_INDEX_PATH)
    if os.path.exists(INDEX_METADATA_PATH): os.remove(INDEX_METADATA_PATH)
    return {"message": "Índice eliminado"}


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