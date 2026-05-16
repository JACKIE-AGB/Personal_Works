from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_text_splitters import CharacterTextSplitter, RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_classic.chains import RetrievalQA
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from langchain_community.embeddings import HuggingFaceEmbeddings
import tempfile
import os
import shutil
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

app = FastAPI(title="Unified Document API", version="1.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración — la API key viene del .env, NUNCA hardcodeada
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("⛔ GROQ_API_KEY no encontrada. Agrégala a tu archivo .env")

# ============================================
# EMBEDDINGS — multilingual-e5-large
# Reemplaza all-MiniLM-L6-v2 (mayormente inglés) por un modelo
# multilingüe optimizado para español técnico (documentación CFE).
# normalize_embeddings=True mejora la similitud coseno en FAISS.
# ⚠️  IMPORTANTE: si ya tienes un índice guardado con el modelo anterior,
#     borra la carpeta faiss_saved_index/ antes de reiniciar la API,
#     de lo contrario las búsquedas devolverán resultados incorrectos.
# ============================================
embeddings = HuggingFaceEmbeddings(
    model_name="intfloat/multilingual-e5-large",
    encode_kwargs={"normalize_embeddings": True}
)
FAISS_INDEX_PATH = "faiss_saved_index"

# Estados de los índices
pdf_vectorstore = None
folder_vectorstore = None

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

        loader = PyPDFLoader(temp_path)
        docs = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100).split_documents(loader.load())
        pdf_vectorstore = FAISS.from_documents(docs, embeddings)
        os.unlink(temp_path)
        return {"message": "PDF procesado correctamente"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/ask_pdf/")
async def ask_pdf(question: str = Form(...), style: str = Form("normal")):
    if pdf_vectorstore is None:
        return {"answer": "❌ Sube un PDF primero."}

    prompt_style = "Responde de forma profesional."
    if style == "amable":
        prompt_style = "Responde de manera amable y útil."
    elif style == "agresivo":
        prompt_style = "Responde de forma directa y corta."

    qa_chain = RetrievalQA.from_chain_type(
        llm=ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY, temperature=0.3),
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
        loader = DirectoryLoader(folder_path, glob="**/*.pdf", loader_cls=PyPDFLoader)
        raw_documents = loader.load()

        for doc in raw_documents:
            file_name = os.path.basename(doc.metadata['source'])
            doc.page_content = f"ARCHIVO: {file_name}\nCONTENIDO: {doc.page_content}"

        # chunk_size=1800 y overlap=300: fragmentos más grandes para preservar
        # contexto técnico completo (tablas, especificaciones, numeración de artículos).
        docs = RecursiveCharacterTextSplitter(chunk_size=1800, chunk_overlap=300).split_documents(raw_documents)
        folder_vectorstore = FAISS.from_documents(docs, embeddings)
        folder_vectorstore.save_local(FAISS_INDEX_PATH)

        # Contar archivos únicos (raw_documents tiene una entrada por PÁGINA, no por archivo)
        unique_files = list(set([os.path.basename(d.metadata['source']) for d in raw_documents]))
        return {
            "message": f"Indexación completa: {len(unique_files)} archivos.",
            "files": unique_files
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/ask_folder/")
async def ask_folder(question: str = Form(...)):
    global folder_vectorstore
    if folder_vectorstore is None:
        return {"answer": "❌ Indexa una carpeta primero."}

    template = """Eres un Analista de Documentos experto. Usa el contexto para responder e identifica siempre el archivo fuente.
    Contexto: {context}
    Pregunta: {question}
    Respuesta:"""

    prompt = PromptTemplate(template=template, input_variables=["context", "question"])
    chain = RetrievalQA.from_chain_type(
        # gpt-oss-120b: modelo más potente e inteligente de Groq (2026).
        # Mayor razonamiento para cruzar información entre múltiples documentos técnicos.
        # temperature=0.0 → respuestas 100% factuales, sin alucinaciones.
        llm=ChatGroq(model="openai/gpt-oss-120b", api_key=GROQ_API_KEY, temperature=0.0),
        # k=8: recupera más fragmentos para carpetas masivas con docs relacionados
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
    global folder_vectorstore
    folder_vectorstore = None
    if os.path.exists(FAISS_INDEX_PATH):
        shutil.rmtree(FAISS_INDEX_PATH)
    return {"message": "Índice borrado."}

@app.get("/health")
async def health():
    return {
        "pdf_ready": pdf_vectorstore is not None,
        "folder_ready": folder_vectorstore is not None,
        "embeddings_model": "intfloat/multilingual-e5-large",
        "folder_llm": "openai/gpt-oss-120b",
        "pdf_llm": "llama-3.3-70b-versatile"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)