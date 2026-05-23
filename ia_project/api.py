from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from langchain_text_splitters import CharacterTextSplitter        
from langchain_community.vectorstores import FAISS                
from langchain_classic.chains import RetrievalQA   
from langchain_community.document_loaders import PyPDFLoader      
# from langchain_openai import OpenAIEmbeddings, ChatOpenAI         
from fastapi.responses import JSONResponse
from langchain_groq import ChatGroq
from langchain_community.embeddings import HuggingFaceEmbeddings

import tempfile
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

vectorstore = None
qa_chain = None

def get_prompt_style(style):
    if style == "amable":
        return "Responde de manera amable, clara y útil."
    elif style == "agresivo":
        return "Responde de forma directa, corta y sin rodeos."
    else:
        return "Responde de manera profesional y clara."

@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    global vectorstore, qa_chain

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            temp_path = tmp.name

        loader = PyPDFLoader(temp_path)
        documents = loader.load()

        splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = splitter.split_documents(documents)

        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        vectorstore = FAISS.from_documents(docs, embeddings)

        qa_chain = RetrievalQA.from_chain_type(
            llm=ChatGroq(model="llama-3.1-8b-instant", api_key="GROQ_API_KEY"),
            retriever=vectorstore.as_retriever()
        )

        os.unlink(temp_path)
        return {"message": "PDF procesado correctamente"}

    except Exception as e:
         Ahora verás exactamente qué falló
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/ask/")
async def ask_question(
    question: str = Form(...),
    style: str = Form("normal")
):
    global qa_chain

    if qa_chain is None:
        return {"answer": "Primero debes subir un PDF"}

    try:
        prompt_style = get_prompt_style(style)
        final_question = f"{prompt_style}\nPregunta: {question}"
        response = qa_chain.run(final_question)
        return {"answer": response}

    except Exception as e:
        return JSONResponse(status_code=500, content={"answer": f"Error al procesar: {str(e)}"})