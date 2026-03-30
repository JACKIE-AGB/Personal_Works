import torch
import fitz
from fastapi import FastAPI, UploadFile, File
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

model_id = "microsoft/Phi-3-mini-4k-instruct"

tokenizer = AutoTokenizer.from_pretrained(model_id)

model = AutoModelForCausalLM.from_pretrained(
    model_id,
    device_map="auto",
    torch_dtype="auto"
)

phi3_pipe = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer
)

#app
app = FastAPI()
contexto_pdf=""

#util
def extraer_texto_pdf(file_bytes):
    texto=""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for pagina in doc:
            texto += pagina.get_text()
    return texto

#Endpoint
@app.post("upload.pdf")
async def upload_pdf(file: UploadFile = File(...)):
    global contexto_pdf
    pdf_bytes = await file.read()
    contexto_pdf = extraer_texto_pdf(pdf_bytes)
    return {"status": "PDF cargado correctamente"}


@app.post("/preguntar")
async def preguntar(pregunta: str):
    prompt = f"""
<|user|>
Basado en este texto:
{contexto_pdf}

Pregunta: {pregunta}
<|end|>
<|assistant|>
"""

    outputs = phi3_pipe(
        prompt,
        max_new_tokens=200,
        temperature=0.1,
        do_sample=True
    )

    respuesta = outputs[0]["generated_text"].split("<|assistant|>")[-1].strip()
    return {"respuesta": respuesta}