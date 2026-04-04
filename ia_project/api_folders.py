from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_classic.chains import RetrievalQA    
from langchain_core.prompts import PromptTemplate
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from fastapi.responses import JSONResponse
from langchain_groq import ChatGroq
from langchain_community.embeddings import HuggingFaceEmbeddings
import os
import shutil

# Instancia del API
app_folders = FastAPI()

app_folders.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- RUTA LOCAL DONDE SE GUARDA EL ÍNDICE EN DISCO ---
FAISS_INDEX_PATH = "faiss_saved_index"
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vectorstore = None

# --- Cargar índice persistido si existe al arrancar el servidor ---
if os.path.exists(FAISS_INDEX_PATH):
    try:
        vectorstore = FAISS.load_local(FAISS_INDEX_PATH, embeddings, allow_dangerous_deserialization=True)
        print("✅ Índice FAISS cargado desde disco correctamente.")
    except Exception as e:
        print(f"⚠️  No se pudo cargar el índice previo: {e}")

# --- PROMPT DE INDAGACIÓN ---
custom_prompt_template = """
Eres un Analista de Documentos experto. Tu tarea es identificar qué archivos de la biblioteca responden a la duda del usuario.

INSTRUCCIONES:
1. Revisa el contenido y los nombres de los archivos en el 'Contexto'.
2. Si el usuario pregunta por un tema general, busca conceptos relacionados.
3. Identifica SIEMPRE el nombre del archivo (source) que contiene la información.

Contexto: {context}
Pregunta: {question}

Respuesta Sugerida:
"""

@app_folders.post("/index_folder/")
async def index_folder(folder_path: str = Form(...)):
    global vectorstore
    if not os.path.exists(folder_path):
        return JSONResponse(status_code=400, content={"error": "Ruta no encontrada"})

    try:
        loader = DirectoryLoader(folder_path, glob="**/*.pdf", loader_cls=PyPDFLoader)
        raw_documents = loader.load()

        if not raw_documents:
            return JSONResponse(status_code=400, content={"error": "No hay PDFs en la ruta"})

        for doc in raw_documents:
            file_name = os.path.basename(doc.metadata['source'])
            doc.page_content = f"ARCHIVO: {file_name}\nCONTENIDO: {doc.page_content}"

        splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200)
        docs = splitter.split_documents(raw_documents)

        vectorstore = FAISS.from_documents(docs, embeddings)

        # --- Guardar el índice en disco para que persista entre reinicios ---
        vectorstore.save_local(FAISS_INDEX_PATH)

        file_list = list(set([os.path.basename(d.metadata['source']) for d in raw_documents]))
        return {"message": f"Indexación completa: {len(file_list)} archivos analizados.", "files": file_list}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app_folders.post("/clear_index/")
async def clear_index():
    """Elimina el índice en memoria y en disco."""
    global vectorstore
    vectorstore = None
    if os.path.exists(FAISS_INDEX_PATH):
        shutil.rmtree(FAISS_INDEX_PATH)
    return {"message": "Índice eliminado correctamente."}


@app_folders.post("/ask/")
async def ask_question(question: str = Form(...), style: str = Form("normal")):
    global vectorstore
    if vectorstore is None:
        return {"answer": "Error: Primero indexa una carpeta usando el endpoint de api_folders."}

    try:
        prompt = PromptTemplate(template=custom_prompt_template, input_variables=["context", "question"])
        
        chain = RetrievalQA.from_chain_type(
            llm=ChatGroq(model="llama-3.1-8b-instant", api_key="GROQ_API_KEY", temperature=0.1),
            chain_type="stuff",
            retriever=vectorstore.as_retriever(search_type="mmr", search_kwargs={'k': 6}),
            return_source_documents=True,
            chain_type_kwargs={"prompt": prompt}
        )
        
        result = chain.invoke({"query": question})
        answer = result["result"]
        
        sources = list(set([os.path.basename(doc.metadata['source']) for doc in result["source_documents"]]))
        paths_str = "\n\n**📍 Ubicación del documento:**\n" + "\n".join([f"📄 `{s}`" for s in sources])

        return {"answer": answer + paths_str}
    except Exception as e:
        return JSONResponse(status_code=500, content={"answer": f"Error en la consulta: {str(e)}"})