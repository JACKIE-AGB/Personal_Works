import os
import torch
import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from threading import Thread
from transformers import AutoTokenizer, AutoModelForCausalLM, TextIteratorStreamer, pipeline
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Chatbot PDF Backend")

# --- CONFIGURACIÓN DEL MODELO ---
MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"
device = "cuda" if torch.cuda.is_available() else "cpu"
model, tokenizer, model_pipeline = None, None, None
contexto_documentos = ""

def cargar_modelo():
    global model, tokenizer, model_pipeline
    logger.info(f"Cargando {MODEL_ID} en {device}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, 
        torch_dtype="auto", 
        device_map="auto", 
        trust_remote_code=True
    )
    model_pipeline = pipeline("text-generation", model=model, tokenizer=tokenizer)

cargar_modelo()

# --- MODELOS DE DATOS ---
class Mensaje(BaseModel):
    role: str # 'user' o 'assistant'
    content: str

class ChatRequest(BaseModel):
    messages: List[Mensaje]
    max_tokens: int = 512

# --- LÓGICA DE DOCUMENTOS ---
def extraer_texto(path_o_bytes, es_ruta=False):
    texto = ""
    try:
        doc = fitz.open(path_o_bytes) if es_ruta else fitz.open(stream=path_o_bytes, filetype="pdf")
        for pagina in doc:
            texto += pagina.get_text()
        return texto.strip()
    except Exception as e:
        return f"Error leyendo PDF: {e}"

# --- ENDPOINTS ---
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    global contexto_documentos
    content = await file.read()
    contexto_documentos = extraer_texto(content)
    return {"status": "ready", "chars": len(contexto_documentos)}

@app.post("/chat")
async def chat(req: ChatRequest):
    def generar():
        # Construimos el prompt con el contexto del PDF al inicio si existe
        full_history = []
        if contexto_documentos:
            system_msg = {
                "role": "system", 
                "content": f"Eres un asistente útil. Tienes acceso a este documento:\n{contexto_documentos[:8000]}\nResponde de forma natural y breve."
            }
            full_history.append(system_msg)
        
        for m in req.messages:
            full_history.append({"role": m.role, "content": m.content})

        streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
        
        # Generación en hilo para streaming
        inputs = tokenizer.apply_chat_template(full_history, tokenize=True, add_generation_prompt=True, return_tensors="pt").to(device)
        generation_kwargs = dict(input_ids=inputs, streamer=streamer, max_new_tokens=req.max_tokens, do_sample=True, temperature=0.7)
        
        thread = Thread(target=model.generate, kwargs=generation_kwargs)
        thread.start()

        for chunk in streamer:
            yield chunk

    return StreamingResponse(generar(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)