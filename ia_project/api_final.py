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
import fitz  # PyMuPDF para procesamiento veloz de texto y gráficos planos
import base64
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

app = FastAPI(title="CFE Intelligent Document & Vision API", version="2.5")

# Configuración de CORS
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
# CONFIGURACIÓN DE MODELOS Y RUTAS
# ==========================================================
VISION_MODEL = "llama-3.2-90b-vision-instruct" 
TEXT_MODEL_FOLDER = "openai/gpt-oss-120b"
TEXT_MODEL_PDF = "llama-3.3-70b-versatile"

MAX_DOCUMENTS = 100
PDF_INDEX_PATH = "pdf_index"
FOLDER_INDEX_PATH = "folder_index"

# Embeddings multilingües óptimos para documentación técnica en español
embeddings = HuggingFaceEmbeddings(
    model_name="intfloat/multilingual-e5-large",
    encode_kwargs={"normalize_embeddings": True}
)

pdf_vectorstore = None
folder_vectorstore = None

# Inicializar modelo de visión de producción
vision_llm = ChatGroq(model=VISION_MODEL, api_key=GROQ_API_KEY, temperature=0.0)

# ==========================================================
# CARGA INICIAL DE ÍNDICES PERSISTENTES
# ==========================================================
if os.path.exists(PDF_INDEX_PATH):
    try:
        pdf_vectorstore = FAISS.load_local(
            PDF_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        print("✅ Índice PDF individual cargado desde disco.")
    except Exception as e:
        print(f"⚠️ No se pudo inicializar el índice PDF local: {e}")

if os.path.exists(FOLDER_INDEX_PATH):
    try:
        folder_vectorstore = FAISS.load_local(
            FOLDER_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        print("✅ Índice de carpetas masivas cargado desde disco.")
    except Exception as e:
        print(f"⚠️ No se pudo inicializar el índice de carpetas local: {e}")


# ==========================================================
# PIPELINE DE EXTRACCIÓN MULTIMODAL (TEXTO + PLANOS / IMÁGENES)
# ==========================================================
def extract_pdf_content_with_vision(file_path: str) -> list[Document]:
    """
    Procesa un PDF página por página. Si detecta planos, diagramas o imágenes,
    los convierte temporalmente en formato visual y usa la IA de visión de Groq
    para generar una descripción técnica detallada e indexable en FAISS.
    """
    documents = []
    file_name = os.path.basename(file_path)
    
    with fitz.open(file_path) as pdf:
        for page_num in range(len(pdf)):
            page = pdf[page_num]
            text = page.get_text()
            has_images = len(page.get_images()) > 0
            
            # Formatear el contenido base textual
            page_content = f"ARCHIVO: {file_name}\nPÁGINA: {page_num + 1}\n"
            if text.strip():
                page_content += f"CONTENIDO TEXTUAL:\n{text}\n"
            
            # Criterio: Si contiene imágenes o es un plano con poco texto extraíble nativamente
            if has_images or len(text.strip()) < 150:
                try:
                    # Renderizar la página como imagen PNG a alta definición (150 DPI para legibilidad de planos)
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("png")
                    encoded_image = base64.b64encode(img_bytes).decode("utf-8")
                    
                    prompt_vision = (
                        "Eres un ingeniero especialista de la CFE. Analiza minuciosamente este plano técnico, "
                        "diagrama de flujo, mapa o documento escaneado de la central hidroeléctrica. "
                        "Describe detalladamente la distribución de equipos, tuberías, conexiones eléctricas, "
                        "valores numéricos, nomenclaturas, leyendas y cualquier dato crítico para que sea indexable textualmente."
                    )
                    
                    message = HumanMessage(
                        content=[
                            {"type": "text", "text": prompt_vision},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{encoded_image}"}
                            }
                        ]
                    )
                    
                    response = vision_llm.invoke([message])
                    page_content += f"\n[DESCRIPCIÓN DE PLANO E IMAGEN TÉCNICA]:\n{response.content}\n"
                    
                except Exception as ve:
                    print(f"⚠️ Error de procesamiento visual en {file_name} (Pág. {page_num + 1}): {ve}")
            
            # Guardar estructura final como Document compatible con LangChain
            documents.append(Document(
                page_content=page_content,
                metadata={"source": file_path, "page": page_num + 1}
            ))
            
    return documents


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

        # Análisis avanzado visual y textual
        raw_documents = extract_pdf_content_with_vision(temp_path)
        
        docs = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=250
        ).split_documents(raw_documents)

        pdf_vectorstore = FAISS.from_documents(docs, embeddings)
        pdf_vectorstore.save_local(PDF_INDEX_PATH)
        
        os.unlink(temp_path)
        return {
            "message": "PDF analizado por visión computacional e indexado correctamente.",
            "chunks": len(docs)
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/ask_pdf/")
async def ask_pdf(question: str = Form(...), style: str = Form("normal")):
    global pdf_vectorstore
    if pdf_vectorstore is None:
        return {"answer": "❌ Primero sube y procesa un PDF"}

    prompt_style = "Eres un analista documental experto de CFE. Responde de forma profesional basándote en el texto y planos analizados."
    if style == "amable":
        prompt_style = "Eres un analista documental experto de CFE. Responde de manera amable, cordial y altamente detallada."
    elif style == "agresivo":
        prompt_style = "Eres un analista documental experto de CFE. Responde de forma directa, técnica, concisa y sin rodeos."

    template = f"""{prompt_style}
Responde únicamente usando el contexto proporcionado.
Si no encuentras información suficiente en los fragmentos, indica claramente que no existe en el documento.

Contexto:
{{context}}

Pregunta:
{{question}}

Respuesta:
"""
    prompt = PromptTemplate(template=template, input_variables=["context", "question"])
    
    chain = RetrievalQA.from_chain_type(
        llm=ChatGroq(model=TEXT_MODEL_PDF, api_key=GROQ_API_KEY, temperature=0.2),
        retriever=pdf_vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": 5}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt}
    )
    
    result = chain.invoke({"query": question})
    return {"answer": result["result"]}


# ==========================================================
# ENDPOINTS: CARPETAS MASIVAS
# ==========================================================
@app.post("/index_folder/")
async def index_folder(folder_path: str = Form(...)):
    global folder_vectorstore
    if not os.path.exists(folder_path):
        return JSONResponse(status_code=400, content={"error": "La ruta especificada no existe en el servidor."})

    try:
        pdf_files = []
        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(".pdf"):
                    pdf_files.append(os.path.join(root, file))

        if len(pdf_files) > MAX_DOCUMENTS:
            return JSONResponse(status_code=400, content={"error": f"Límite excedido: El máximo permitido son {MAX_DOCUMENTS} PDFs"})
        
        if not pdf_files:
            return JSONResponse(status_code=400, content={"error": "No se encontraron archivos PDF en el directorio."})

        all_documents = []
        for full_path in pdf_files:
            try:
                file_docs = extract_pdf_content_with_vision(full_path)
                all_documents.extend(file_docs)
            except Exception as fe:
                print(f"⚠️ Omitiendo archivo inaccesible o dañado: {full_path} -> {fe}")

        docs = RecursiveCharacterTextSplitter(
            chunk_size=1800,
            chunk_overlap=300
        ).split_documents(all_documents)

        folder_vectorstore = FAISS.from_documents(docs, embeddings)
        folder_vectorstore.save_local(FOLDER_INDEX_PATH)

        unique_files = list(set([os.path.basename(d.metadata['source']) for d in all_documents]))
        return {
            "message": "Indexación recursiva de planos y carpetas completada con éxito.",
            "documents": len(unique_files),
            "files": unique_files
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/ask_folder/")
async def ask_folder(question: str = Form(...)):
    global folder_vectorstore
    if folder_vectorstore is None:
        return {"answer": "❌ Primero indexa una carpeta desde el panel técnico"}

    template = """Eres un Ingeniero Analista del Sistema de Información de CFE El Cajón. Utiliza los fragmentos de contexto provistos (que incluyen transcripciones de texto e interpretaciones técnicas de planos y esquemas analizados por visión computacional) para responder la pregunta de forma técnica, fáctica y sumamente precisa.
    
    Contexto:
    {context}
    
    Pregunta:
    {question}
    
    Respuesta:"""

    prompt = PromptTemplate(template=template, input_variables=["context", "question"])
    
    chain = RetrievalQA.from_chain_type(
        llm=ChatGroq(model=TEXT_MODEL_FOLDER, api_key=GROQ_API_KEY, temperature=0.0),
        retriever=folder_vectorstore.as_retriever(search_type="mmr", search_kwargs={'k': 8}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt}
    )

    result = chain.invoke({"query": question})
    sources = list(set([os.path.basename(doc.metadata['source']) for doc in result["source_documents"]]))
    
    return {
        "answer": result["result"],
        "sources": sources
    }


# ==========================================================
# ENDPOINT: CONTROL Y LIMPIEZA DE MEMORIA
# ==========================================================
@app.post("/clear_index/")
async def clear_index():
    global pdf_vectorstore, folder_vectorstore
    pdf_vectorstore = None
    folder_vectorstore = None

    if os.path.exists(PDF_INDEX_PATH):
        shutil.rmtree(PDF_INDEX_PATH)
    if os.path.exists(FOLDER_INDEX_PATH):
        shutil.rmtree(FOLDER_INDEX_PATH)

    return {"message": "Índices locales de memoria y disco eliminados correctamente."}


@app.get("/health")
async def health():
    return {
        "pdf_ready": pdf_vectorstore is not None,
        "folder_ready": folder_vectorstore is not None,
        "max_documents": MAX_DOCUMENTS,
        "vision_llm_active": VISION_MODEL,
        "embeddings": "intfloat/multilingual-e5-large"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)