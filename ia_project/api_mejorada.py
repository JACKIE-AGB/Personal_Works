import os
import torch
import fitz
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager
import logging
import warnings
from fastapi.responses import StreamingResponse
from transformers import TextIteratorStreamer
from threading import Thread

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"

device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"Dispositivo detectado: {device}")

model_pipeline = None
contexto_pdf = ""
archivo_actual = ""
MODEL_LOADED = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    global model_pipeline, MODEL_LOADED
    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

        logger.info(f"Cargando tokenizer para {MODEL_ID}...")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)

        dtype = torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float16
        if device == "cpu":
            dtype = torch.float32

        logger.info("Cargando modelo...")
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=dtype,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
            device_map="auto" if device == "cuda" else None,
        )

        if device == "cpu":
            model = model.to(device)

        logger.info("Creando pipeline optimizado...")
        model_pipeline = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            device_map="auto" if device == "cuda" else None,
        )

        MODEL_LOADED = True
        logger.info("✅ MODELO CARGADO EXITOSAMENTE")
    except Exception as e:
        logger.error(f"❌ ERROR AL CARGAR EL MODELO: {e}")
        MODEL_LOADED = False

    yield

    model_pipeline = None
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


app = FastAPI(
    title="PDF QA API",
    version="5.0",
    description="API inteligente para hacer preguntas sobre documentos PDF",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PreguntaRequest(BaseModel):
    pregunta: str
    max_tokens: Optional[int] = 512


class CargarArchivoRequest(BaseModel):
    ruta_completa: str


def extraer_texto_pdf(file_bytes: bytes) -> str:
    try:
        texto = ""
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            for pagina in doc:
                texto += pagina.get_text()
        return texto.strip()
    except Exception as e:
        logger.error(f"Error al extraer texto: {e}")
        raise HTTPException(status_code=500, detail=f"Error al procesar PDF: {str(e)}")


# ... imports y config global igual ...

def seleccionar_contexto(pregunta: str, contexto: str) -> str:
    """Selecciona fragmento relevante con límites más ajustados."""
    pregunta_lower = pregunta.lower()
    palabras_inicio = [
        "autor", "autores", "escrito por", "título", "titulo", "fecha",
        "publicado", "institución", "universidad", "versión", "resumen"
    ]
    if any(p in pregunta_lower for p in palabras_inicio):
        return contexto[:1500]   # reducido de 3000
    return contexto[:3000]       # reducido de 6000

def generar_respuesta_stream(pregunta: str, contexto: str, max_tokens: int):
    if not MODEL_LOADED or not model_pipeline:
        yield "⚠️ El modelo no está disponible."
        return

    try:
        contexto_seleccionado = seleccionar_contexto(pregunta, contexto)

        # Prompt de sistema mucho más corto y directo
        system_prompt = (
            "Eres un asistente experto. Responde directamente basándote SOLO en el documento proporcionado.\n"
            "Reglas:\n"
            "1. Respuesta en 1-3 oraciones máximo, salvo que se pida más.\n"
            "2. Si la información no está en el documento, responde: 'El documento no especifica esa información.'\n"
            "3. No repitas la pregunta ni añadas introducciones."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"FRAGMENTO DEL DOCUMENTO:\n"
                    f"---\n{contexto_seleccionado}\n---\n\n"
                    f"PREGUNTA: {pregunta}"
                ),
            },
        ]

        tokenizer = model_pipeline.tokenizer
        model = model_pipeline.model

        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(prompt, return_tensors="pt").to(device)

        streamer = TextIteratorStreamer(
            tokenizer, skip_prompt=True, skip_special_tokens=True
        )

        # Configuración de generación optimizada: greedy decoding, sin muestreo
        generation_kwargs = dict(
            input_ids=inputs.input_ids,
            attention_mask=inputs.attention_mask,
            max_new_tokens=max_tokens,
            do_sample=False,           # greedy, más rápido
            repetition_penalty=1.15,   # evita repeticiones
            streamer=streamer,
        )

        # Usar inference_mode para acelerar
        with torch.inference_mode():
            thread = Thread(target=model.generate, kwargs=generation_kwargs)
            thread.start()

            for new_text in streamer:
                yield new_text

            thread.join()

    except Exception as e:
        logger.error(f"Error en inferencia: {e}")
        yield f"Error: {str(e)}"


@app.get("/")
def root():
    return {"status": "API activa", "modelo_cargado": MODEL_LOADED, "dispositivo": device}


@app.post("/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):
    global contexto_pdf, archivo_actual
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")

    contenido = await file.read()
    contexto_pdf = extraer_texto_pdf(contenido)
    archivo_actual = file.filename

    return {
        "status": f"Archivo '{file.filename}' cargado",
        "caracteres": len(contexto_pdf),
        "preview": contexto_pdf[:300] + "...",
    }


@app.post("/cargar_desde_ruta")
def cargar_desde_ruta(req: CargarArchivoRequest):
    global contexto_pdf, archivo_actual
    if not os.path.isfile(req.ruta_completa):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    with open(req.ruta_completa, "rb") as f:
        contenido = f.read()

    contexto_pdf = extraer_texto_pdf(contenido)
    archivo_actual = req.ruta_completa

    return {
        "status": "Archivo cargado",
        "caracteres": len(contexto_pdf),
        "preview": contexto_pdf[:300] + "...",
    }


@app.post("/preguntar")
def preguntar(req: PreguntaRequest):
    if not contexto_pdf:
        raise HTTPException(status_code=400, detail="No hay documento cargado.")

    return StreamingResponse(
        generar_respuesta_stream(req.pregunta, contexto_pdf, req.max_tokens),
        media_type="text/plain",
    )


@app.get("/estado")
def estado():
    return {
        "modelo": MODEL_ID,
        "archivo_cargado": archivo_actual if archivo_actual else "Ninguno",
        "caracteres_en_contexto": len(contexto_pdf),
        "modelo_cargado": MODEL_LOADED,
        "dispositivo": device,
    }


if __name__ == "__main__":
    import uvicorn
    logger.info("Iniciando servidor en http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)