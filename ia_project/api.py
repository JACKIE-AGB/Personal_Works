import os
import re
import torch
import fitz  # PyMuPDF
import pdfplumber
import io
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from threading import Thread
from transformers import AutoTokenizer, AutoModelForCausalLM, TextIteratorStreamer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Chatbot PDF Backend")

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"   # ← cambia a 3B si tienes poca VRAM
device = "cuda" if torch.cuda.is_available() else "cpu"
model, tokenizer = None, None

# Almacén del documento activo
documento_activo: dict = {
    "texto": "",
    "paginas": 0,
    "nombre": "",
    "tiene_tablas": False,
}


def cargar_modelo():
    global model, tokenizer
    logger.info(f"Cargando {MODEL_ID} en {device}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map="auto",
        trust_remote_code=True,
    )
    model.eval()
    logger.info("Modelo cargado correctamente.")


cargar_modelo()

class Mensaje(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Mensaje]
    max_tokens: int = 512


def _limpiar_texto(texto: str) -> str:
    """Limpia artefactos comunes de extracción PDF."""
    # Quitar líneas con un solo carácter repetido (separadores tipo -----)
    texto = re.sub(r"^[\-_=]{3,}\s*$", "", texto, flags=re.MULTILINE)
    # Colapsar más de 2 saltos de línea consecutivos
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    # Quitar espacios al inicio/fin de cada línea
    lineas = [l.rstrip() for l in texto.splitlines()]
    texto = "\n".join(lineas)
    # Quitar caracteres de control raros (excepto \n y \t)
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", texto)
    return texto.strip()


def _extraer_con_pymupdf(doc_bytes: bytes) -> tuple[str, int]:
    """
    Extrae texto con PyMuPDF usando bloques ordenados por posición.
    Respeta el orden visual real (columnas, encabezados, etc.).
    Retorna (texto_completo, num_paginas).
    """
    paginas_texto = []
    with fitz.open(stream=doc_bytes, filetype="pdf") as doc:
        num_paginas = len(doc)
        for num, pagina in enumerate(doc, start=1):
            # get_text("blocks") → lista de (x0, y0, x1, y1, texto, block_no, tipo)
            # tipo 0 = texto, tipo 1 = imagen
            bloques = pagina.get_text("blocks", sort=True)

            fragmentos = []
            for bloque in bloques:
                tipo = bloque[6]
                if tipo != 0:      # Saltar imágenes
                    continue
                frag = bloque[4].strip()
                if len(frag) < 3:  # Ignorar fragmentos vacíos o muy cortos
                    continue
                fragmentos.append(frag)

            if fragmentos:
                paginas_texto.append(
                    f"── Página {num} ──\n" + "\n".join(fragmentos)
                )

    return "\n\n".join(paginas_texto), num_paginas


def _extraer_tablas_con_pdfplumber(doc_bytes: bytes) -> str:
    """
    Extrae tablas de forma legible usando pdfplumber.
    Retorna un bloque de texto con todas las tablas encontradas.
    """
    tablas_texto = []
    with pdfplumber.open(io.BytesIO(doc_bytes)) as pdf:
        for num, pagina in enumerate(pdf.pages, start=1):
            tablas = pagina.extract_tables()
            if not tablas:
                continue
            for i, tabla in enumerate(tablas, start=1):
                if not tabla:
                    continue
                # Convertir la tabla a texto alineado
                filas_texto = []
                for fila in tabla:
                    celda_limpia = [str(c).strip() if c else "" for c in fila]
                    filas_texto.append(" | ".join(celda_limpia))
                bloque = (
                    f"[Tabla {i} — Página {num}]\n"
                    + "\n".join(filas_texto)
                )
                tablas_texto.append(bloque)
    return "\n\n".join(tablas_texto)


def _detectar_pdf_escaneado(doc_bytes: bytes) -> bool:
    """
    Devuelve True si el PDF parece ser un escaneo (poco o ningún texto extraíble).
    """
    with fitz.open(stream=doc_bytes, filetype="pdf") as doc:
        muestra = min(3, len(doc))
        total_chars = sum(
            len(doc[i].get_text().strip()) for i in range(muestra)
        )
        return total_chars < 50 * muestra   # < 50 caracteres por página → escaneo


def extraer_pdf_completo(doc_bytes: bytes) -> dict:
    """
    Pipeline principal de extracción.
    Combina PyMuPDF (texto ordenado) + pdfplumber (tablas).
    Retorna dict con texto, páginas, advertencias.
    """
    es_escaneado = _detectar_pdf_escaneado(doc_bytes)
    advertencias = []

    if es_escaneado:
        advertencias.append(
            "⚠️ El PDF parece ser un escaneo. El texto extraído puede ser limitado. "
            "Para mejores resultados, usa un PDF con texto seleccionable."
        )

    # 1. Texto principal ordenado por posición
    texto_principal, num_paginas = _extraer_con_pymupdf(doc_bytes)

    # 2. Tablas
    try:
        texto_tablas = _extraer_tablas_con_pdfplumber(doc_bytes)
        tiene_tablas = bool(texto_tablas.strip())
    except Exception as e:
        logger.warning(f"Error extrayendo tablas: {e}")
        texto_tablas = ""
        tiene_tablas = False

    # 3. Combinar
    secciones = [texto_principal]
    if tiene_tablas:
        secciones.append("\n\n══ TABLAS DETECTADAS ══\n" + texto_tablas)

    texto_final = _limpiar_texto("\n\n".join(secciones))

    return {
        "texto": texto_final,
        "paginas": num_paginas,
        "tiene_tablas": tiene_tablas,
        "escaneado": es_escaneado,
        "advertencias": advertencias,
        "chars": len(texto_final),
    }


# ─────────────────────────────────────────────
# GESTIÓN DE CONTEXTO — ventana inteligente
# ─────────────────────────────────────────────

MAX_CONTEXT_CHARS = 12_000   # ~3000 tokens de contexto de documento

def preparar_contexto(texto: str, pregunta: str) -> str:
    """
    En lugar de truncar ciegamente, intenta mantener las secciones
    más relevantes para la pregunta del usuario.
    Si el texto cabe completo, lo pasa tal cual.
    """
    if len(texto) <= MAX_CONTEXT_CHARS:
        return texto

    # Búsqueda simple por relevancia: páginas que contengan palabras clave
    palabras_clave = [
        p.lower() for p in re.split(r"\W+", pregunta) if len(p) > 3
    ]
    paginas = re.split(r"── Página \d+ ──", texto)

    puntuadas = []
    for pag in paginas:
        pag_lower = pag.lower()
        score = sum(pag_lower.count(kw) for kw in palabras_clave)
        puntuadas.append((score, pag))

    # Ordenar por relevancia, luego reconstruir hasta el límite
    puntuadas.sort(key=lambda x: x[0], reverse=True)
    resultado = []
    total = 0
    for _, pag in puntuadas:
        if total + len(pag) > MAX_CONTEXT_CHARS:
            break
        resultado.append(pag)
        total += len(pag)

    return "...(fragmentos más relevantes)...\n\n" + "\n\n".join(resultado)


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    global documento_activo
    try:
        contenido = await file.read()
        if not contenido:
            raise HTTPException(400, "Archivo vacío.")
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Solo se aceptan archivos PDF.")

        resultado = extraer_pdf_completo(contenido)

        if resultado["chars"] < 20:
            raise HTTPException(400, "No se pudo extraer texto del PDF.")

        documento_activo = {
            "texto": resultado["texto"],
            "paginas": resultado["paginas"],
            "nombre": file.filename,
            "tiene_tablas": resultado["tiene_tablas"],
        }

        respuesta = {
            "status": "ready",
            "archivo": file.filename,
            "paginas": resultado["paginas"],
            "chars": resultado["chars"],
            "tablas": resultado["tiene_tablas"],
        }
        if resultado["advertencias"]:
            respuesta["advertencias"] = resultado["advertencias"]

        logger.info(
            f"PDF cargado: {file.filename} | {resultado['paginas']} pág. | "
            f"{resultado['chars']} chars | tablas={resultado['tiene_tablas']}"
        )
        return respuesta

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al procesar PDF: {e}", exc_info=True)
        raise HTTPException(500, f"Error procesando el archivo: {str(e)}")


@app.post("/chat")
async def chat(req: ChatRequest):
    def generar():
        try:
            # Construir el prompt del sistema
            if documento_activo["texto"]:
                ultima_pregunta = req.messages[-1].content if req.messages else ""
                contexto = preparar_contexto(
                    documento_activo["texto"], ultima_pregunta
                )
                info_doc = (
                    f"Documento: '{documento_activo['nombre']}' "
                    f"({documento_activo['paginas']} páginas"
                    + (", contiene tablas" if documento_activo["tiene_tablas"] else "")
                    + ")"
                )
                system_content = (
                    f"Eres un asistente experto en análisis de documentos. "
                    f"{info_doc}.\n\n"
                    f"CONTENIDO DEL DOCUMENTO:\n{contexto}\n\n"
                    f"Instrucciones:\n"
                    f"- Responde SIEMPRE basándote en el documento anterior.\n"
                    f"- Sé concreto, claro y directo.\n"
                    f"- Si la respuesta requiere citar datos, hazlo con precisión.\n"
                    f"- Si la pregunta no se puede responder con el documento, dilo claramente.\n"
                    f"- Responde en el mismo idioma que el usuario."
                )
            else:
                system_content = (
                    "Eres un asistente útil. Responde de forma clara y concisa. "
                    "Si el usuario quiere analizar un documento, pídele que lo suba."
                )

            historial = [{"role": "system", "content": system_content}]
            for m in req.messages:
                historial.append({"role": m.role, "content": m.content})

            # ── Tokenización en dos pasos (compatible con Python 3.14) ──
            # apply_chat_template solo genera el string del prompt.
            # El tokenizado a tensor se hace por separado para evitar el bug
            # KeyError:shape / AttributeError en transformers + Python 3.14.
            prompt_str = tokenizer.apply_chat_template(
                historial,
                tokenize=False,
                add_generation_prompt=True,
            )
            encoded = tokenizer(
                prompt_str,
                return_tensors="pt",
                add_special_tokens=False,
            )
            input_ids = encoded["input_ids"].to(device)
            attention_mask = encoded["attention_mask"].to(device)

            streamer = TextIteratorStreamer(
                tokenizer, skip_prompt=True, skip_special_tokens=True
            )

            generation_kwargs = dict(
                input_ids=input_ids,
                attention_mask=attention_mask,
                streamer=streamer,
                max_new_tokens=req.max_tokens,
                do_sample=True,
                temperature=0.6,
                top_p=0.9,
                repetition_penalty=1.1,
                pad_token_id=tokenizer.eos_token_id,
            )

            hilo = Thread(target=model.generate, kwargs=generation_kwargs)
            hilo.start()

            for chunk in streamer:
                if chunk:
                    yield chunk

            hilo.join()

        except Exception as e:
            logger.error(f"Error en generación: {e}", exc_info=True)
            yield f"[Error del modelo: {str(e)}]"

    return StreamingResponse(generar(), media_type="text/plain")


@app.get("/status")
async def status():
    """Verifica si el backend está activo y qué documento tiene cargado."""
    return {
        "online": True,
        "modelo": MODEL_ID,
        "device": device,
        "documento_activo": documento_activo["nombre"] or None,
        "paginas": documento_activo["paginas"],
    }


@app.delete("/documento")
async def limpiar_documento():
    """Borra el documento activo para empezar con uno nuevo."""
    global documento_activo
    documento_activo = {"texto": "", "paginas": 0, "nombre": "", "tiene_tablas": False}
    return {"status": "cleared"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)