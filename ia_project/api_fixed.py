import os
import torch
import fitz
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging
import warnings
import sys

# Suprimir warnings
warnings.filterwarnings("ignore")

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración del modelo
MODEL_ID = "microsoft/Phi-3-mini-4k-instruct"

# Detectar dispositivo
device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"Dispositivo detectado: {device}")

# Variables globales
tokenizer = None
model = None
phi_pipe = None
MODEL_LOADED = False

def load_model():
    """Carga el modelo con manejo de errores detallado"""
    global tokenizer, model, phi_pipe, MODEL_LOADED
    
    try:
        logger.info("=" * 50)
        logger.info("INICIANDO CARGA DEL MODELO")
        logger.info("=" * 50)
        
        # Importar transformers
        from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
        
        logger.info(f"1. Cargando tokenizer para {MODEL_ID}...")
        tokenizer = AutoTokenizer.from_pretrained(
            MODEL_ID,
            trust_remote_code=True,
            use_fast=True,
            cache_dir=None  # Usar caché por defecto
        )
        logger.info("✅ Tokenizer cargado correctamente")
        
        # Configurar token de padding
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            logger.info("Token de padding configurado")
        
        logger.info("2. Cargando modelo...")
        logger.info("Esto puede tomar varios minutos la primera vez...")
        
        # Configuración para CPU (optimizada)
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.float32,  # Usar float32 para CPU
            device_map="cpu",  # Forzar CPU
            trust_remote_code=True,
            low_cpu_mem_usage=True,
            use_cache=True
        )
        logger.info("✅ Modelo cargado correctamente")
        
        logger.info("3. Creando pipeline de generación...")
        phi_pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            device=0 if torch.cuda.is_available() else -1,  # -1 para CPU
            torch_dtype=torch.float32
        )
        logger.info("✅ Pipeline creado correctamente")
        
        MODEL_LOADED = True
        logger.info("=" * 50)
        logger.info("🎉 MODELO CARGADO EXITOSAMENTE")
        logger.info("=" * 50)
        return True
        
    except Exception as e:
        logger.error("=" * 50)
        logger.error(f"❌ ERROR AL CARGAR EL MODELO: {e}")
        logger.error(f"Tipo de error: {type(e).__name__}")
        logger.error("=" * 50)
        
        # Mostrar información de diagnóstico
        logger.info("\nDIAGNÓSTICO:")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"PyTorch version: {torch.__version__}")
        
        try:
            import transformers
            logger.info(f"Transformers version: {transformers.__version__}")
        except:
            logger.info("Transformers no instalado")
        
        try:
            import accelerate
            logger.info(f"Accelerate version: {accelerate.__version__}")
        except:
            logger.info("Accelerate no instalado")
        
        return False

# Intentar cargar el modelo
MODEL_LOADED = load_model()

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

def generar_respuesta_simple(pregunta: str, contexto: str, max_tokens: int = 512) -> str:
    """Genera respuesta usando el modelo con formato simple"""
    if not MODEL_LOADED:
        return "⚠️ El modelo no está disponible. Por favor, revisa los logs del servidor."
    
    try:
        # Limitar contexto
        contexto_limitado = contexto[:3000]
        
        # Formato más simple y directo
        prompt = f"""Context: {contexto_limitado}

Question: {pregunta}

Answer based only on the context above:"""
        
        # Generar respuesta
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096)
        
        # Mover inputs al mismo dispositivo que el modelo
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=min(max_tokens, 512),
                temperature=0.3,
                do_sample=True,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id
            )
        
        # Decodificar respuesta
        respuesta = tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Extraer solo la respuesta (después de "Answer:")
        if "Answer:" in respuesta:
            respuesta = respuesta.split("Answer:")[-1].strip()
        else:
            # Si no encuentra el marcador, tomar lo último
            respuesta = respuesta.replace(prompt, "").strip()
        
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
    
    respuesta = generar_respuesta_simple(
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
    logger.info("Iniciando servidor en http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)