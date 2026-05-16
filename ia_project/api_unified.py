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
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

app = FastAPI(title="CFE Unified Document & Vision API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de API Key
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("⛔ GROQ_API_KEY no encontrada. Agrégala a tu archivo .env")

# Modelos configurados
VISION_MODEL = "llama-3.2-90b-vision-preview"
TEXT_MODEL_FOLDER = "openai/gpt-oss-120b"
TEXT_MODEL_PDF = "llama-3.3-70b-versatile"

# Embeddings multilingües
embeddings = HuggingFaceEmbeddings(
    model_name="intfloat/multilingual-e5-large",
    encode_kwargs={"normalize_embeddings": True}
)
FAISS_INDEX_PATH = "faiss_saved_index"

# Estados de los índices
pdf_vectorstore = None
folder_vectorstore = None

# Inicializar modelo de visión
vision_llm = ChatGroq(model=VISION_MODEL, api_key=GROQ_API_KEY, temperature=0.0)


# ============================================
# PIPELINE DE PROCESAMIENTO VISUAL Y TEXTUAL
# ============================================
def extract_pdf_content_with_vision(file_path: str) -> list[Document]:
    """
    Lee un PDF página por página. Si detecta imágenes o planos, utiliza el modelo
    de visión de Groq para describir el contenido visual y añadirlo al índice.
    """
    documents = []
    file_name = os.path.basename(file_path)
    
    with fitz.open(file_path) as pdf:
        for page_num in range(len(pdf)):
            page = pdf[page_num]
            text = page.get_text()
            has_images = len(page.get_images()) > 0
            
            # Construcción del bloque de contenido básico
            page_content = f"ARCHIVO: {file_name}\nPÁGINA: {page_num + 1}\n"
            if text.strip():
                page_content += f"TEXTO EXTRAÍDO:\n{text}\n"
            
            # Criterio: Si tiene imágenes o el texto es muy corto (posible plano o escaneo)
            if has_images or len(text.strip()) < 150:
                try:
                    # Renderizar página a imagen de alta definición (DPI 150 para planos)
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("png")
                    encoded_image = base64.b64encode(img_bytes).decode("utf-8")
                    
                    # Crear el mensaje multimodal para Groq
                    prompt_vision = (
                        "Eres un ingeniero experto de la CFE. Analiza detalladamente esta imagen, plano o diagrama "
                        "técnico perteneciente a la planta. Describe meticulosamente la distribución, componentes eléctricos, "
                        "conexiones, tuberías, diagramas de flujo, etiquetas, tablas de datos y cualquier nomenclatura visible. "
                        "Tu descripción debe ser exhaustiva para que pueda ser buscada con precisión mediante texto."
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
                    
                    # Invocar el modelo de visión
                    response = vision_llm.invoke([message])
                    page_content += f"\n[ANÁLISIS VISUAL DEL PLANO/DIAGRAMA]:\n{response.content}\n"
                    
                except Exception as ve:
                    print(f"⚠️ No se pudo procesar la visión en {file_name} (Pág. {page_num + 1}): {ve}")
            
            # Crear documento estructurado para LangChain
            documents.append(Document(
                page_content=page_content,
                metadata={"source": file_path, "page": page_num + 1}
            ))
            
    return documents


# ============================================
# LÓGICA DE CARGA INICIAL
# ============================================
if os.path.exists(FAISS_INDEX_PATH):
    try:
        folder_vectorstore = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        print("✅ Índice de carpetas persistente cargado.")
    except Exception as e:
        print(f"⚠️ Error al cargar índice: {e}")


# ============================================
# ENDPOINTS PDF INDIVIDUAL
# ============================================
@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    global pdf_vectorstore
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            temp_path = tmp.name

        # Procesamiento avanzado con visión incorporada
        raw_documents = extract_pdf_content_with_vision(temp_path)
        
        splitter = RecursiveCharacterTextSplitter(chunk_size=1800, chunk_overlap=300)
        docs = splitter.split_documents(raw_documents)
        
        pdf_vectorstore = FAISS.from_documents(docs, embeddings)
        os.unlink(temp_path)
        return {"message": "PDF con análisis visual procesado correctamente"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/ask_pdf/")
async def ask_pdf(question: str = Form(...), style: str = Form("normal")):
    if pdf_vectorstore is None:
        return {"answer": "❌ Sube un PDF primero."}

    prompt_style = "Responde de forma profesional basándote en la información y análisis visual provistos."
    if style == "amable":
        prompt_style = "Responde de manera amable, servicial y técnica."
    elif style == "agresivo":
        prompt_style = "Responde de forma directa, corta y técnica."

    qa_chain = RetrievalQA.from_chain_type(
        llm=ChatGroq(model=TEXT_MODEL_PDF, api_key=GROQ_API_KEY, temperature=0.3),
        retriever=pdf_vectorstore.as_retriever(search_kwargs={'k': 4})
    )
    response = qa_chain.run(f"{prompt_style}\n\nPregunta: {question}")
    return {"answer": response}


# ============================================
# ENDPOINTS CARPETAS
# ============================================
@app.post("/index_folder/")
async def index_folder(folder_path: str = Form(...)):
    global folder_vectorstore
    if not os.path.exists(folder_path):
        return JSONResponse(status_code=400, content={"error": "Ruta no encontrada"})

    try:
        all_documents = []
        # Caminar por el directorio de forma recursiva para buscar archivos PDF
        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith('.pdf'):
                    full_path = os.path.join(root, file)
                    try:
                        # Extraer contenido de texto y planos usando visión
                        file_docs = extract_pdf_content_with_vision(full_path)
                        all_documents.extend(file_docs)
                    except Exception as fe:
                        print(f"⚠️ Error omitiendo archivo {full_path}: {fe}")

        if not all_documents:
            return JSONResponse(status_code=400, content={"error": "No se encontraron PDFs válidos en la carpeta."})

        splitter = RecursiveCharacterTextSplitter(chunk_size=1800, chunk_overlap=300)
        docs = splitter.split_documents(all_documents)
        
        folder_vectorstore = FAISS.from_documents(docs, embeddings)
        folder_vectorstore.save_local(FAISS_INDEX_PATH)

        unique_files = list(set([os.path.basename(d.metadata['source']) for d in all_documents]))
        return {
            "message": f"Indexación completa con análisis de imágenes: {len(unique_files)} archivos analizados.",
            "files": unique_files
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/ask_folder/")
async def ask_folder(question: str = Form(...)):
    global folder_vectorstore
    if folder_vectorstore is None:
        return {"answer": "❌ Indexa una carpeta primero."}

    template = """Eres un Analista de Documentos e Ingeniero Experto de CFE. Usa el contexto provisto (que incluye transcripciones de texto e interpretaciones detalladas de planos y elementos visuales) para responder la pregunta de forma fáctica. Identifica siempre el archivo fuente.
    Contexto: {context}
    Pregunta: {question}
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
    paths_str = "\n\n**📍 Ubicación del documento:**\n" + "\n".join([f"📄 `{s}`" for s in sources])
    return {"answer": result["result"] + paths_str}


@app.post("/clear_index/")
async def clear_index():
    global folder_vectorstore, pdf_vectorstore
    folder_vectorstore = None
    pdf_vectorstore = None
    if os.path.exists(FAISS_INDEX_PATH):
        shutil.rmtree(FAISS_INDEX_PATH)
    return {"message": "Índices borrados por completo."}


@app.get("/health")
async def health():
    return {
        "pdf_ready": pdf_vectorstore is not None,
        "folder_ready": folder_vectorstore is not None,
        "embeddings_model": "intfloat/multilingual-e5-large",
        "vision_model": VISION_MODEL,
        "folder_llm": TEXT_MODEL_FOLDER,
        "pdf_llm": TEXT_MODEL_PDF
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)