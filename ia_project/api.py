import os
import torch
import fitz
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging
import warnings

# Suprimir warnings
warnings.filterwarnings("ignore")

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración del modelo principal
MODEL_ID = "microsoft/Phi-3.5-mini-instruct"

# Detectar dispositivo
device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"Dispositivo detectado: {device}")

# Variables globales
tokenizer = None
model = None
phi_pipe = None
MODEL_LOADED = False

def load_model():
    """Carga el modelo principal optimizado para evitar colapsos de memoria"""
    global tokenizer, model, phi_pipe, MODEL_LOADED
    
    try:
        logger.info("=" * 50)
        logger.info("INICIANDO CARGA DEL MODELO PRINCIPAL")
        logger.info("=" * 50)
        
        from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
        
        logger.info(f"1. Cargando tokenizer para {MODEL_ID}...")
        tokenizer = AutoTokenizer.from_pretrained(
            MODEL_ID,
            trust_remote_code=True,
            use_fast=True
        )
        
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        logger.info("2. Cargando modelo (usando bfloat16 para ahorrar un 50% de RAM)...")
        # Usamos bfloat16 o float16 en lugar de float32 para evitar OOM (Out of Memory)
        dtype = torch.bfloat16 if device == "cpu" else torch.float16
        
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=dtype,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
            attn_implementation="eager"
        ).to(device)
        logger.info("✅ Modelo cargado correctamente en memoria")
        
        logger.info("3. Creando pipeline de generación...")
        # Eliminamos device=-1 porque el modelo ya fue movido con .to(device)
        phi_pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer
        )
        logger.info("✅ Pipeline creado correctamente")
        
        MODEL_LOADED = True
        logger.info("=" * 50)
        logger.info("🎉 MODELO PRINCIPAL CARGADO EXITOSAMENTE")
        logger.info("=" * 50)
        return True
        
    except Exception as e:
        logger.error(f"❌ ERROR AL CARGAR EL MODELO PRINCIPAL: {e}")
        return False

# Intentar cargar el modelo principal
MODEL_LOADED = load_model()

# Si falló, intentar con un modelo alternativo VERDADERAMENTE pequeño (0.5B params)
if not MODEL_LOADED:
    logger.warning("Intentando con modelo alternativo ultraligero (Qwen2.5-0.5B)...")
    try:
        MODEL_ID_ALT = "Qwen/Qwen2.5-0.5B-Instruct"
        from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
        
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID_ALT)
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID_ALT,
            torch_dtype=torch.float32 if device == "cpu" else torch.float16,
            low_cpu_mem_usage=True
        ).to(device)
        
        phi_pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)
        
        MODEL_LOADED = True
        logger.info("✅ Modelo alternativo (Qwen) cargado correctamente")
    except Exception as e:
        logger.error(f"❌ También falló el modelo alternativo: {e}")

# Inicializar FastAPI
app = FastAPI(
    title="PDF QA API", 
    version="3.0",
    description="API para hacer preguntas sobre documentos PDF"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

contexto_pdf = ""
archivo_actual = ""

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

def generar_respuesta(pregunta: str, contexto: str, max_tokens: int = 512) -> str:
    if not MODEL_LOADED:
        return "⚠️ El modelo no está disponible. Revisa los logs de la terminal para ver el error exacto de memoria o dependencias."
    
    try:
        contexto_limitado = contexto[:3000]
        
        messages = [
            {"role": "user", "content": f"Basado en el siguiente documento, responde la pregunta de forma concisa.\n\nDocumento:\n{contexto_limitado}\n\nPregunta:\n{pregunta}"}
        ]
        
        outputs = phi_pipe(
            messages,
            max_new_tokens=min(max_tokens, 512),
            temperature=0.3,
            do_sample=True
        )
        
        respuesta_bruta = outputs[0]["generated_text"]
        
        # Manejo correcto de la salida: en transformers nuevos devuelve una lista de mensajes
        if isinstance(respuesta_bruta, list):
            # Extraer solo el contenido del último mensaje (la respuesta del asistente)
            respuesta = respuesta_bruta[-1].get("content", "").strip()
        else:
            respuesta = str(respuesta_bruta)
            # Limpieza en caso de que devuelva el texto plano
            if "Pregunta:" in respuesta:
                respuesta = respuesta.split("Pregunta:")[-1].split("\n", 1)[-1].strip()
                
        return respuesta if respuesta else "No se pudo generar una respuesta coherente."
        
    except Exception as e:
        logger.error(f"Error en inferencia: {e}")
        return f"Error al procesar la pregunta: {str(e)}"

@app.get("/")
def root():
    return {"status": "API activa", "modelo_cargado": MODEL_LOADED, "dispositivo": device}

@app.post("/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):
    global contexto_pdf, archivo_actual
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")
    
    contenido = await file.read()
    contexto_pdf = extraer_texto_pdf(contenido)
    archivo_actual = file.filename
    
    return {
        "status": f"Archivo '{file.filename}' cargado",
        "caracteres": len(contexto_pdf),
        "preview": contexto_pdf[:300] + "..."
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
        "preview": contexto_pdf[:300] + "..."
    }

@app.post("/preguntar")
def preguntar(req: PreguntaRequest):
    if not contexto_pdf:
        raise HTTPException(status_code=400, detail="No hay documento cargado.")
    
    respuesta = generar_respuesta(req.pregunta, contexto_pdf, req.max_tokens)
    return {"archivo": archivo_actual, "pregunta": req.pregunta, "respuesta": respuesta}

@app.get("/estado")
def estado():
    return {"archivo_cargado": archivo_actual, "caracteres": len(contexto_pdf), "modelo_cargado": MODEL_LOADED, "dispositivo": device}

if __name__ == "__main__":
    import uvicorn
    logger.info("Iniciando servidor en http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)