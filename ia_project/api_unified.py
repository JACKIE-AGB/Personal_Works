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

# ============================================
# CONFIGURACIÓN
# ============================================
app = FastAPI(title="Unified Document API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de API Key (usa variable de entorno)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "tu_api_key_aqui")
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# Estado para PDF individual
pdf_vectorstore = None

# Estado para carpetas
folder_vectorstore = None
FAISS_INDEX_PATH = "faiss_saved_index"

# ============================================
# FUNCIONES AUXILIARES
# ============================================
def get_prompt_style(style: str) -> str:
    if style == "amable":
        return "Responde de manera amable, clara y útil, como un asistente servicial."
    elif style == "agresivo":
        return "Responde de forma directa, corta y sin rodeos. Ve al grano inmediatamente."
    else:
        return "Responde de manera profesional, clara y precisa."

# ============================================
# ENDPOINTS PARA PDF INDIVIDUAL
# ============================================
@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    global pdf_vectorstore
    
    try:
        # Guardar temporalmente
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            temp_path = tmp.name
        
        # Cargar y procesar
        loader = PyPDFLoader(temp_path)
        documents = loader.load()
        
        splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = splitter.split_documents(documents)
        
        # Crear vectorstore
        pdf_vectorstore = FAISS.from_documents(docs, embeddings)
        
        # Limpiar
        os.unlink(temp_path)
        
        return {"message": "PDF procesado correctamente"}
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/ask_pdf/")
async def ask_pdf(
    question: str = Form(...),
    style: str = Form("normal")
):
    global pdf_vectorstore
    
    if pdf_vectorstore is None:
        return {"answer": "❌ Primero debes subir un PDF usando /upload_pdf/"}
    
    try:
        prompt_style = get_prompt_style(style)
        final_question = f"{prompt_style}\n\nPregunta del usuario: {question}"
        
        qa_chain = RetrievalQA.from_chain_type(
            llm=ChatGroq(model="llama-3.1-8b-instant", api_key=GROQ_API_KEY, temperature=0.3),
            retriever=pdf_vectorstore.as_retriever(search_kwargs={'k': 4})
        )
        
        response = qa_chain.run(final_question)
        return {"answer": response}
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"answer": f"Error: {str(e)}"})

# ============================================
# ENDPOINTS PARA CARPETAS
# ============================================
# Cargar índice persistente al iniciar
if os.path.exists(FAISS_INDEX_PATH):
    try:
        folder_vectorstore = FAISS.load_local(
            FAISS_INDEX_PATH, 
            embeddings, 
            allow_dangerous_deserialization=True
        )
        print("✅ Índice de carpetas cargado desde disco")
    except Exception as e:
        print(f"⚠️ No se pudo cargar índice previo: {e}")

@app.post("/index_folder/")
async def index_folder(folder_path: str = Form(...)):
    global folder_vectorstore
    
    if not os.path.exists(folder_path):
        return JSONResponse(status_code=400, content={"error": "Ruta no encontrada"})
    
    try:
        # Cargar todos los PDFs de la carpeta
        loader = DirectoryLoader(folder_path, glob="**/*.pdf", loader_cls=PyPDFLoader)
        raw_documents = loader.load()
        
        if not raw_documents:
            return JSONResponse(status_code=400, content={"error": "No se encontraron PDFs en la carpeta"})
        
        # Enriquecer con nombre del archivo
        for doc in raw_documents:
            file_name = os.path.basename(doc.metadata['source'])
            doc.page_content = f"📄 ARCHIVO: {file_name}\n📝 CONTENIDO: {doc.page_content}"
        
        # Dividir documentos
        splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200)
        docs = splitter.split_documents(raw_documents)
        
        # Crear vectorstore y guardar
        folder_vectorstore = FAISS.from_documents(docs, embeddings)
        folder_vectorstore.save_local(FAISS_INDEX_PATH)
        
        # Lista de archivos procesados
        file_list = sorted(list(set([os.path.basename(d.metadata['source']) for d in raw_documents])))
        
        return {
            "message": f"✅ Indexación completada: {len(file_list)} archivos procesados",
            "files": file_list
        }
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/clear_index/")
async def clear_index():
    global folder_vectorstore
    
    folder_vectorstore = None
    
    if os.path.exists(FAISS_INDEX_PATH):
        shutil.rmtree(FAISS_INDEX_PATH)
    
    return {"message": "Índice eliminado correctamente"}

# Prompt personalizado para carpetas
FOLDER_PROMPT_TEMPLATE = PromptTemplate(
    input_variables=["context", "question"],
    template="""
Eres un Analista de Documentos experto. Debes responder basándote ÚNICAMENTE en el contexto proporcionado.

INSTRUCCIONES:
1. Identifica qué archivo(s) contienen la información relevante.
2. SIEMPRE menciona el nombre del archivo en tu respuesta.
3. Si no encuentras la información, indica claramente que no está disponible.
4. Sé preciso y conciso.

CONTEXTO:
{context}

PREGUNTA DEL USUARIO:
{question}

RESPUESTA:
"""
)

@app.post("/ask_folder/")
async def ask_folder(question: str = Form(...)):
    global folder_vectorstore
    
    if folder_vectorstore is None:
        return {"answer": "❌ Primero debes indexar una carpeta usando /index_folder/"}
    
    try:
        qa_chain = RetrievalQA.from_chain_type(
            llm=ChatGroq(
                model="llama-3.1-8b-instant", 
                api_key=GROQ_API_KEY, 
                temperature=0.2
            ),
            chain_type="stuff",
            retriever=folder_vectorstore.as_retriever(
                search_type="mmr", 
                search_kwargs={'k': 6}
            ),
            return_source_documents=True,
            chain_type_kwargs={"prompt": FOLDER_PROMPT_TEMPLATE}
        )
        
        result = qa_chain.invoke({"query": question})
        answer = result["result"]
        
        # Extraer fuentes
        sources = list(set([
            os.path.basename(doc.metadata['source']) 
            for doc in result["source_documents"]
        ]))
        
        if sources:
            sources_text = "\n\n📚 **Documentos consultados:**\n" + "\n".join([f"• `{s}`" for s in sources])
            answer = answer + sources_text
        
        return {"answer": answer}
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"answer": f"Error: {str(e)}"})

# ============================================
# ENDPOINT DE VERIFICACIÓN
# ============================================
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "pdf_ready": pdf_vectorstore is not None,
        "folder_ready": folder_vectorstore is not None
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Iniciando servidor unificado...")
    print("📄 Endpoints disponibles:")
    print("   POST /upload_pdf/  - Subir PDF individual")
    print("   POST /ask_pdf/     - Preguntar sobre PDF")
    print("   POST /index_folder/ - Indexar carpeta")
    print("   POST /ask_folder/   - Preguntar sobre carpeta")
    print("   POST /clear_index/  - Limpiar índice")
    print("   GET  /health        - Verificar estado")
    uvicorn.run(app, host="127.0.0.1", port=8001)