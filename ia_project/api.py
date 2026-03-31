import os
import torch
import fitz
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging
import warnings

# Suprimir warnings de transformers
warnings.filterwarnings("ignore")

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración del modelo
MODEL_ID = "microsoft/Phi-3.5-mini-instruct"

# Detectar dispositivo
device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"Dispositivo detectado: {device}")

# Variables globales para el modelo
tokenizer = None
model = None
phi_pipe = None

def load_model():
    """Carga el modelo con manejo de errores"""
    global tokenizer, model, phi_pipe
    
    try:
        logger.info(f"Cargando modelo: {MODEL_ID}...")
        
        # Importar transformers dentro de la función para mejor manejo
        from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
        
        # Cargar tokenizer con configuración específica
        tokenizer = AutoTokenizer.from_pretrained(
            MODEL_ID,
            trust_remote_code=True,
            use_fast=True
        )
        
        # Configurar token de padding
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        # Cargar modelo con configuración optimizada
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto",
            trust_remote_code=True,
            low_cpu_mem_usage=True,
            use_cache=True
        )
        
        # Crear pipeline
        phi_pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            device_map="auto",
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
        )
        
        logger.info("✅ Modelo cargado correctamente")
        return True
        
    except ImportError as e:
        logger.error(f"Error de importación: {e}")
        logger.error("Asegúrate de tener instaladas las versiones correctas:")
        logger.error("pip install transformers==4.46.3 torch==2.5.1 accelerate==1.1.0 einops==0.8.0")
        return False
    except Exception as e:
        logger.error(f"Error al cargar el modelo: {e}")
        logger.error(f"Tipo de error: {type(e).__name__}")
        return False

# Intentar cargar el modelo al inicio
MODEL_LOADED = load_model()

if not MODEL_LOADED:
    logger.warning("⚠️ No se pudo cargar el modelo. La API funcionará con funcionalidad limitada.")

# Inicializar FastAPI
app = FastAPI(
    title="PDF QA API", 
    version="3.0",
    description="API para hacer preguntas sobre documentos PDF"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estado global
contexto_pdf = ""
archivo_actual = ""

# Modelos Pydantic
class PreguntaRequest(BaseModel):
    pregunta: str
    max_tokens: Optional[int] = 512

class CargarArchivoRequest(BaseModel):
    ruta_completa: str

# Funciones utilitarias
def extraer_texto_pdf(file_bytes: bytes) -> str:
    """Extrae texto de un archivo PDF"""
    try:
        texto = ""
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            for pagina in doc:
                texto += pagina.get_text()
        return texto.strip()
    except Exception as e:
        logger.error(f"Error al extraer texto del PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Error al procesar PDF: {str(e)}")

def generar_respuesta(pregunta: str, contexto: str, max_tokens: int = 512) -> str:
    """Genera respuesta usando el modelo"""
    if not MODEL_LOADED:
        return "⚠️ El modelo no está disponible. Por favor, verifica las dependencias."
    
    try:
        # Limitar contexto para evitar exceder límites
        contexto_limitado = contexto[:3500]
        
        # Usar el formato correcto para Phi-3.5
        messages = [
            {"role": "user", "content": f"Contexto: {contexto_limitado}\n\nPregunta: {pregunta}\n\nResponde basándote únicamente en el contexto proporcionado."}
        ]
        
        # Generar respuesta
        outputs = phi_pipe(
            messages,
            max_new_tokens=min(max_tokens, 512),
            temperature=0.3,
            do_sample=True,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id
        )
        
        respuesta = outputs[0]["generated_text"].strip()
        
        # Limpiar la respuesta si contiene el contexto
        if respuesta.startswith("Contexto:"):
            respuesta = respuesta.split("Pregunta:")[-1] if "Pregunta:" in respuesta else respuesta
        
        return respuesta if respuesta else "No se pudo generar una respuesta."
        
    except Exception as e:
        logger.error(f"Error al generar respuesta: {e}")
        return f"Error al procesar la pregunta: {str(e)}"

# Endpoints
@app.get("/")
def root():
    return {
        "status": "API activa",
        "modelo": MODEL_ID if MODEL_LOADED else "No cargado",
        "modelo_cargado": MODEL_LOADED,
        "archivo_cargado": archivo_actual or "Ninguno",
        "dispositivo": device
    }

@app.post("/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """Sube un archivo PDF"""
    global contexto_pdf, archivo_actual
    
    # Validar extensión
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")
    
    try:
        contenido = await file.read()
        contexto_pdf = extraer_texto_pdf(contenido)
        archivo_actual = file.filename
        
        if not contexto_pdf:
            raise HTTPException(status_code=400, detail="No se pudo extraer texto del PDF")
        
        logger.info(f"Archivo cargado: {file.filename}, caracteres: {len(contexto_pdf)}")
        
        return {
            "status": f"Archivo '{file.filename}' cargado correctamente",
            "caracteres": len(contexto_pdf),
            "preview": contexto_pdf[:300] + "..." if len(contexto_pdf) > 300 else contexto_pdf,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al subir archivo: {e}")
        raise HTTPException(status_code=500, detail=f"Error al procesar archivo: {str(e)}")

@app.post("/cargar_desde_ruta")
def cargar_desde_ruta(req: CargarArchivoRequest):
    """Carga un archivo desde una ruta local"""
    global contexto_pdf, archivo_actual
    
    if not os.path.isfile(req.ruta_completa):
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {req.ruta_completa}")
    
    if not req.ruta_completa.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")
    
    try:
        with open(req.ruta_completa, "rb") as f:
            contenido = f.read()
        
        contexto_pdf = extraer_texto_pdf(contenido)
        archivo_actual = req.ruta_completa
        
        if not contexto_pdf:
            raise HTTPException(status_code=400, detail="No se pudo extraer texto del PDF")
        
        logger.info(f"Archivo cargado desde ruta: {req.ruta_completa}, caracteres: {len(contexto_pdf)}")
        
        return {
            "status": "Archivo cargado correctamente",
            "archivo": req.ruta_completa,
            "caracteres": len(contexto_pdf),
            "preview": contexto_pdf[:300] + "..." if len(contexto_pdf) > 300 else contexto_pdf,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al cargar archivo desde ruta: {e}")
        raise HTTPException(status_code=500, detail=f"Error al leer archivo: {str(e)}")

@app.post("/preguntar")
def preguntar(req: PreguntaRequest):
    """Hace una pregunta sobre el documento cargado"""
    if not contexto_pdf:
        raise HTTPException(
            status_code=400,
            detail="No hay documento cargado. Use /upload_pdf o /cargar_desde_ruta primero."
        )
    
    respuesta = generar_respuesta(
        pregunta=req.pregunta,
        contexto=contexto_pdf,
        max_tokens=req.max_tokens
    )
    
    return {
        "archivo": archivo_actual,
        "pregunta": req.pregunta,
        "respuesta": respuesta,
    }

@app.get("/estado")
def estado():
    """Devuelve info del documento actualmente cargado"""
    return {
        "archivo_cargado": archivo_actual or "Ninguno",
        "caracteres_en_contexto": len(contexto_pdf),
        "modelo": MODEL_ID if MODEL_LOADED else "No disponible",
        "modelo_cargado": MODEL_LOADED,
        "dispositivo": device
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)