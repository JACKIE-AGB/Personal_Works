from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_text_splitters import RecursiveCharacterTextSplitter
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

load_dotenv()

app = FastAPI(title="CFE Intelligent Document API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY no encontrada")

# ==========================================================
# CONFIG
# ==========================================================

MAX_DOCUMENTS = 100

PDF_INDEX_PATH = "pdf_index"
FOLDER_INDEX_PATH = "folder_index"

embeddings = HuggingFaceEmbeddings(
    model_name="intfloat/multilingual-e5-large",
    encode_kwargs={"normalize_embeddings": True}
)

pdf_vectorstore = None
folder_vectorstore = None

# ==========================================================
# LOAD SAVED INDEXES
# ==========================================================

if os.path.exists(PDF_INDEX_PATH):
    try:
        pdf_vectorstore = FAISS.load_local(
            PDF_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        print("✅ PDF index cargado")
    except:
        pass

if os.path.exists(FOLDER_INDEX_PATH):
    try:
        folder_vectorstore = FAISS.load_local(
            FOLDER_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        print("✅ Folder index cargado")
    except:
        pass

# ==========================================================
# PDF INDIVIDUAL
# ==========================================================

@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    global pdf_vectorstore

    try:

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            temp_path = tmp.name

        loader = PyPDFLoader(temp_path)

        raw_documents = loader.load()

        docs = RecursiveCharacterTextSplitter(
            chunk_size=1800,
            chunk_overlap=300
        ).split_documents(raw_documents)

        pdf_vectorstore = FAISS.from_documents(docs, embeddings)

        pdf_vectorstore.save_local(PDF_INDEX_PATH)

        os.unlink(temp_path)

        return {
            "message": "PDF procesado correctamente",
            "chunks": len(docs)
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.post("/ask_pdf/")
async def ask_pdf(question: str = Form(...)):

    global pdf_vectorstore

    if pdf_vectorstore is None:
        return {"answer": "❌ Primero sube un PDF"}

    template = """
Eres un analista documental experto de CFE.

Responde únicamente usando el contexto proporcionado.

Si no encuentras información suficiente,
indica claramente que no existe en el documento.

Contexto:
{context}

Pregunta:
{question}

Respuesta:
"""

    prompt = PromptTemplate(
        template=template,
        input_variables=["context", "question"]
    )

    chain = RetrievalQA.from_chain_type(
        llm=ChatGroq(
            model="openai/gpt-oss-120b",
            api_key=GROQ_API_KEY,
            temperature=0
        ),
        retriever=pdf_vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={"k": 6}
        ),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt}
    )

    result = chain.invoke({"query": question})

    return {
        "answer": result["result"]
    }

# ==========================================================
# INDEX FOLDER
# ==========================================================

@app.post("/index_folder/")
async def index_folder(folder_path: str = Form(...)):

    global folder_vectorstore

    if not os.path.exists(folder_path):
        return JSONResponse(
            status_code=400,
            content={"error": "Ruta inválida"}
        )

    try:

        pdf_files = []

        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(".pdf"):
                    pdf_files.append(os.path.join(root, file))

        if len(pdf_files) > MAX_DOCUMENTS:
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Máximo permitido: {MAX_DOCUMENTS} PDFs"
                }
            )

        loader = DirectoryLoader(
            folder_path,
            glob="**/*.pdf",
            loader_cls=PyPDFLoader
        )

        raw_documents = loader.load()

        for doc in raw_documents:
            file_name = os.path.basename(doc.metadata['source'])

            doc.page_content = f"""
ARCHIVO: {file_name}

CONTENIDO:
{doc.page_content}
"""

        docs = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=350
        ).split_documents(raw_documents)

        folder_vectorstore = FAISS.from_documents(
            docs,
            embeddings
        )

        folder_vectorstore.save_local(FOLDER_INDEX_PATH)

        unique_files = list(set([
            os.path.basename(d.metadata['source'])
            for d in raw_documents
        ]))

        return {
            "message": f"Indexación completada",
            "documents": len(unique_files),
            "files": unique_files
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

# ==========================================================
# ASK FOLDER
# ==========================================================

@app.post("/ask_folder/")
async def ask_folder(question: str = Form(...)):

    global folder_vectorstore

    if folder_vectorstore is None:
        return {
            "answer": "❌ Primero indexa una carpeta"
        }

    template = """
Eres un analista documental senior de CFE.

Debes:
- analizar documentos técnicos
- identificar archivos origen
- responder con precisión
- evitar alucinaciones

Contexto:
{context}

Pregunta:
{question}

Respuesta:
"""

    prompt = PromptTemplate(
        template=template,
        input_variables=["context", "question"]
    )

    chain = RetrievalQA.from_chain_type(
        llm=ChatGroq(
            model="openai/gpt-oss-120b",
            api_key=GROQ_API_KEY,
            temperature=0
        ),
        retriever=folder_vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={"k": 8}
        ),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt}
    )

    result = chain.invoke({"query": question})

    sources = list(set([
        os.path.basename(doc.metadata['source'])
        for doc in result["source_documents"]
    ]))

    return {
        "answer": result["result"],
        "sources": sources
    }

# ==========================================================
# CLEAR
# ==========================================================

@app.post("/clear_index/")
async def clear_index():

    global pdf_vectorstore
    global folder_vectorstore

    pdf_vectorstore = None
    folder_vectorstore = None

    if os.path.exists(PDF_INDEX_PATH):
        shutil.rmtree(PDF_INDEX_PATH)

    if os.path.exists(FOLDER_INDEX_PATH):
        shutil.rmtree(FOLDER_INDEX_PATH)

    return {"message": "Índices eliminados"}

# ==========================================================
# HEALTH
# ==========================================================

@app.get("/health")
async def health():

    return {
        "pdf_ready": pdf_vectorstore is not None,
        "folder_ready": folder_vectorstore is not None,
        "max_documents": MAX_DOCUMENTS,
        "llm": "openai/gpt-oss-120b",
        "embeddings": "multilingual-e5-large"
    }

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8001
    )