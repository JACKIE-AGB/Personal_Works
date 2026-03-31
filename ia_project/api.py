import os
import glob
import torch
import fitz
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from pydantic import BaseModel
from typing import Optional

# ─────────────────────────────────────────────
# MODELO
# Opción 1 (recomendada, más potente ~7.8B):  "microsoft/Phi-3.5-mini-instruct"
# Opción 2 (aún más potente ~14B, necesita más VRAM): "microsoft/Phi-3-medium-4k-instruct"
# Opción 3 (alternativa open-source potente):  "mistralai/Mistral-7B-Instruct-v0.3"
# ─────────────────────────────────────────────
MODEL_ID = "microsoft/Phi-3.5-mini-instruct"

print(f"[INFO] Cargando modelo: {MODEL_ID} ...")

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    device_map="auto",
    torch_dtype="auto",
    trust_remote_code=True,
)

phi_pipe = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
)

print("[INFO] Modelo cargado correctamente.")

# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────
app = FastAPI(title="PDF QA API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estado global (en producción usa Redis o BD)
contexto_pdf: str = ""
archivo_actual: str = ""

EXTENSIONES_SOPORTADAS = {".pdf", ".txt", ".md"}


# ─────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────
def extraer_texto_pdf(file_bytes: bytes) -> str:
    texto = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for pagina in doc:
            texto += pagina.get_text()
    return texto.strip()


def extraer_texto_txt(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="replace").strip()


def extraer_texto_archivo(ruta: str) -> str:
    """Extrae texto de un archivo dado su path en disco."""
    ext = os.path.splitext(ruta)[1].lower()
    with open(ruta, "rb") as f:
        contenido = f.read()
    if ext == ".pdf":
        return extraer_texto_pdf(contenido)
    elif ext in {".txt", ".md"}:
        return extraer_texto_txt(contenido)
    else:
        raise ValueError(f"Extensión no soportada: {ext}")


def buscar_archivos_en_carpeta(
    carpeta: str,
    nombre_busqueda: Optional[str] = None,
    ruta_relativa: Optional[str] = None,
) -> list[dict]:
    """
    Busca archivos dentro de una carpeta.
    - nombre_busqueda: busca archivos cuyo nombre contenga este texto (case-insensitive).
    - ruta_relativa: ruta relativa dentro de la carpeta, ej: "SubCarpeta/Documento.pdf"
    Devuelve lista de dicts con 'nombre' y 'ruta_completa'.
    """
    if not os.path.isdir(carpeta):
        raise FileNotFoundError(f"La carpeta no existe: {carpeta}")

    # Si se da ruta relativa exacta
    if ruta_relativa:
        ruta_completa = os.path.join(carpeta, ruta_relativa)
        if os.path.isfile(ruta_completa):
            return [{"nombre": os.path.basename(ruta_completa), "ruta_completa": ruta_completa}]
        else:
            raise FileNotFoundError(f"Archivo no encontrado: {ruta_completa}")

    # Búsqueda recursiva por nombre
    resultados = []
    for ext in EXTENSIONES_SOPORTADAS:
        patron = os.path.join(carpeta, "**", f"*{ext}")
        for archivo in glob.glob(patron, recursive=True):
            nombre = os.path.basename(archivo)
            if nombre_busqueda is None or nombre_busqueda.lower() in nombre.lower():
                resultados.append({
                    "nombre": nombre,
                    "ruta_completa": archivo,
                    "ruta_relativa": os.path.relpath(archivo, carpeta),
                })

    return resultados


def generar_respuesta(pregunta: str, contexto: str, max_tokens: int = 512) -> str:
    """Genera respuesta usando el pipeline del modelo."""
    messages = [
        {
            "role": "system",
            "content": (
                "Eres un asistente experto en análisis de documentos. "
                "Responde únicamente basándote en el texto proporcionado. "
                "Si la respuesta no está en el texto, indícalo claramente. "
                "Sé preciso, completo y estructurado en tus respuestas."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Texto del documento:\n\n{contexto[:3500]}\n\n"
                f"Pregunta: {pregunta}"
            ),
        },
    ]

    outputs = phi_pipe(
        messages,
        max_new_tokens=max_tokens,
        temperature=0.2,
        do_sample=True,
        return_full_text=False,
    )

    return outputs[0]["generated_text"].strip()


# ─────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────
class PreguntaRequest(BaseModel):
    pregunta: str
    max_tokens: Optional[int] = 512


class CarpetaRequest(BaseModel):
    carpeta: str                          # Ruta absoluta de la carpeta
    nombre_busqueda: Optional[str] = None # Texto a buscar en el nombre del archivo
    ruta_relativa: Optional[str] = None   # Ruta relativa directa, ej: "Docs/informe.pdf"


class CargarArchivoRequest(BaseModel):
    ruta_completa: str  # Ruta absoluta del archivo a cargar


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "status": "API activa",
        "modelo": MODEL_ID,
        "archivo_cargado": archivo_actual or "Ninguno",
    }


@app.post("/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """Sube un archivo PDF, TXT o MD directamente."""
    global contexto_pdf, archivo_actual

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in EXTENSIONES_SOPORTADAS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado. Use: {EXTENSIONES_SOPORTADAS}",
        )

    contenido = await file.read()
    if ext == ".pdf":
        contexto_pdf = extraer_texto_pdf(contenido)
    else:
        contexto_pdf = extraer_texto_txt(contenido)

    archivo_actual = file.filename

    return {
        "status": f"Archivo '{file.filename}' cargado correctamente",
        "caracteres": len(contexto_pdf),
        "preview": contexto_pdf[:300] + "..." if len(contexto_pdf) > 300 else contexto_pdf,
    }


@app.post("/buscar_en_carpeta")
def buscar_en_carpeta(req: CarpetaRequest):
    """
    Busca archivos dentro de una carpeta.
    Ejemplos de uso:
      - Listar todos los PDFs:       { "carpeta": "/mis/documentos" }
      - Buscar por nombre:           { "carpeta": "/mis/docs", "nombre_busqueda": "informe" }
      - Ruta relativa directa:       { "carpeta": "/mis/docs", "ruta_relativa": "2024/enero.pdf" }
    """
    try:
        archivos = buscar_archivos_en_carpeta(
            carpeta=req.carpeta,
            nombre_busqueda=req.nombre_busqueda,
            ruta_relativa=req.ruta_relativa,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "carpeta": req.carpeta,
        "total_encontrados": len(archivos),
        "archivos": archivos,
    }


@app.post("/cargar_desde_ruta")
def cargar_desde_ruta(req: CargarArchivoRequest):
    """
    Carga un archivo desde una ruta local en disco para hacer preguntas sobre él.
    La ruta puede ser absoluta o relativa al servidor.
    """
    global contexto_pdf, archivo_actual

    if not os.path.isfile(req.ruta_completa):
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {req.ruta_completa}")

    ext = os.path.splitext(req.ruta_completa)[1].lower()
    if ext not in EXTENSIONES_SOPORTADAS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado. Use: {EXTENSIONES_SOPORTADAS}",
        )

    try:
        contexto_pdf = extraer_texto_archivo(req.ruta_completa)
        archivo_actual = req.ruta_completa
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al leer el archivo: {e}")

    return {
        "status": f"Archivo cargado correctamente",
        "archivo": req.ruta_completa,
        "caracteres": len(contexto_pdf),
        "preview": contexto_pdf[:300] + "..." if len(contexto_pdf) > 300 else contexto_pdf,
    }


@app.post("/preguntar")
def preguntar(req: PreguntaRequest):
    """Hace una pregunta sobre el documento cargado actualmente."""
    if not contexto_pdf:
        raise HTTPException(
            status_code=400,
            detail="No hay documento cargado. Use /upload_pdf, /buscar_en_carpeta o /cargar_desde_ruta primero.",
        )

    respuesta = generar_respuesta(
        pregunta=req.pregunta,
        contexto=contexto_pdf,
        max_tokens=req.max_tokens,
    )

    return {
        "archivo": archivo_actual,
        "pregunta": req.pregunta,
        "respuesta": respuesta,
    }


@app.get("/estado")
def estado():
    """Devuelve info del documento actualmente cargado."""
    return {
        "archivo_cargado": archivo_actual or "Ninguno",
        "caracteres_en_contexto": len(contexto_pdf),
        "modelo": MODEL_ID,
    }