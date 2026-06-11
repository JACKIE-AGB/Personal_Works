from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from contextlib import asynccontextmanager
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_classic.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document
from langchain_groq import ChatGroq
from langchain_community.embeddings import HuggingFaceEmbeddings
from typing import List
from pathlib import Path

import tempfile
import os
import shutil
import fitz  # PyMuPDF
import base64
import asyncio
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# =======================================
# ESTADO DE PRE-INDEXACIÓN
# =======================================
PREINDEX_STATUS = {
    "running": False,
    "done": False,
    "total": 0,
    "indexed": 0,
    "errors": 0,
    "current_file": "",
    "log": []          # lista de mensajes para el frontend
}

# Mapa: relative_path → conversation_id  (para lookup rápido al hacer clic)
PREINDEX_MAP: dict[str, str] = {}

def _preindex_single_document(doc: dict) -> tuple[str, str | None]:
    """
    Indexa un documento de XAMPP en hilo de fondo.
    Devuelve (relative_path, conversation_id | None).
    """
    full_path  = doc["full_path"]
    rel_path   = doc["relative_path"]
    file_name  = doc["name"]
    ext        = os.path.splitext(full_path)[1].lower()

    try:
        raw_docs = []

        if ext == ".pdf":
            raw_docs = extract_pdf_parallel(full_path)

        elif ext == ".txt":
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            raw_docs = [Document(page_content=content,
                                 metadata={"source": full_path, "page": 1})]
        else:
            return rel_path, None

        if not raw_docs:
            return rel_path, None

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs     = splitter.split_documents(raw_docs)

        conv_id  = f"xampp_{uuid.uuid4().hex[:8]}"
        conv_dir = os.path.join(BD_INDICES_DIR, conv_id)   # ← carpeta persistente de BD

        vectorstore = FAISS.from_documents(docs, embeddings)
        vectorstore.save_local(conv_dir)

        # 👇 REEMPLAZA EL BLOQUE DE GUARDADO POR ESTE CÓDIGO CON LOCK 👇
        with FILE_LOCK:
            meta = load_metadata()
            meta[conv_id] = {
                "id":          conv_id,
                "title":       file_name,
                "type":        "xampp",
                "target_name": file_name,
                "file_path":   full_path,
                "file_path_bd": conv_dir,
                "relative_path": rel_path,
                "history":     [],
                "created_at":  datetime.now().isoformat()
            }
            save_metadata(meta)
            # NO registrar como sesión temporal — es un índice permanente de la BD

            # Persistir en disco para sobrevivir reinicios (guardar fingerprint del archivo)
            mtime, size = _get_file_fingerprint(full_path)
            pmap = load_preindex_map()
            pmap[rel_path] = {"conv_id": conv_id, "mtime": mtime, "size": size}
            save_preindex_map(pmap)
        # 👆 FIN DEL CÓDIGO CORREGIDO 👆

        print(f"  ✅ Pre-indexado: {file_name}  →  {conv_id}")
        return rel_path, conv_id

    except Exception as e:
        print(f"  ⚠️ Error pre-indexando {file_name}: {e}")
        return rel_path, None


def run_preindex():
    """Ejecuta la pre-indexación completa en un hilo de fondo.
    - Los documentos ya indexados y sin cambios se recuperan del mapa persistente (instantáneo).
    - Los documentos nuevos o modificados se re-indexan automáticamente.
    - Si la carpeta bd_indices/ no existe, se re-indexa todo desde cero.
    """
    global PREINDEX_STATUS, PREINDEX_MAP

    PREINDEX_STATUS["running"] = True
    PREINDEX_STATUS["done"]    = False
    PREINDEX_STATUS["log"]     = []
    PREINDEX_STATUS["indexed"] = 0
    PREINDEX_STATUS["errors"]  = 0

    # ── Verificar si la carpeta de caché existe (si no, re-indexar todo) ──
    cache_exists = os.path.isdir(BD_INDICES_DIR) and os.path.exists(PREINDEX_MAP_FILE)
    if not cache_exists:
        print("📂 Carpeta bd_indices/ no encontrada — se re-indexará todo desde cero.")
        os.makedirs(BD_INDICES_DIR, exist_ok=True)

    # ── Recuperar índices pre-existentes del disco ──
    persisted = load_preindex_map() if cache_exists else {}
    meta       = load_metadata()

    # Validar cada entrada: que el índice FAISS exista y el archivo fuente no haya cambiado
    valid_persisted = {}
    stale_paths = []
    for rel_path, entry in persisted.items():
        conv_id  = entry.get("conv_id", entry) if isinstance(entry, dict) else entry
        conv_dir = os.path.join(BD_INDICES_DIR, conv_id)
        full_path = os.path.join(XAMPP_DOCS_PATH, rel_path)

        # Dentro del ciclo "for rel_path, entry in persisted.items():"
        # 👇 REEMPLAZA LA LÍNEA DE "index_ok" POR ESTA 👇
        index_ok = conv_id in meta and os.path.exists(os.path.join(conv_dir, "index.faiss"))
        file_changed = _file_changed(rel_path, full_path, persisted)

        if index_ok and not file_changed:
            valid_persisted[rel_path] = entry
        else:
            reason = "índice huérfano" if not index_ok else "archivo modificado en BD"
            print(f"  ♻️  Re-indexando ({reason}): {rel_path}")
            stale_paths.append(rel_path)
            # Limpiar índice viejo si existe
            if os.path.exists(conv_dir):
                shutil.rmtree(conv_dir, ignore_errors=True)
            if conv_id in meta:
                del meta[conv_id]

    if stale_paths:
        save_metadata(meta)

    # Sincronizar mapa en memoria con los válidos
    PREINDEX_MAP.update({
        rel: (entry["conv_id"] if isinstance(entry, dict) else entry)
        for rel, entry in valid_persisted.items()
    })
    if len(valid_persisted) != len(persisted):
        save_preindex_map(valid_persisted)   # limpiar entradas obsoletas del disco

    reused = len(valid_persisted)
    if reused:
        print(f"⚡ {reused} documento(s) ya pre-indexados y sin cambios — reutilizando caché.")

    docs = scan_xampp_documents()
    PREINDEX_STATUS["total"] = len(docs)

    # Filtrar: pendientes = nuevos + modificados
    pending = [
        d for d in docs
        if d["relative_path"] not in PREINDEX_MAP or d["relative_path"] in stale_paths
    ]

    if not pending:
        print("✅ Todos los documentos de la BD ya están en caché — arranque instantáneo.")
        PREINDEX_STATUS["indexed"] = reused
        PREINDEX_STATUS["running"] = False
        PREINDEX_STATUS["done"]    = True
        return

    print(f"⚙️  Pre-indexando {len(pending)} documento(s) (nuevos o modificados)...")

    futures = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for doc in pending:
            PREINDEX_STATUS["current_file"] = doc["name"]
            f = pool.submit(_preindex_single_document, doc)
            futures[f] = doc["name"]

        for future in as_completed(futures):
            name = futures[future]
            try:
                rel_path, conv_id = future.result()
                if conv_id:
                    PREINDEX_MAP[rel_path] = conv_id
                    PREINDEX_STATUS["indexed"] += 1
                    msg = f"✅ {name}"
                else:
                    PREINDEX_STATUS["errors"] += 1
                    msg = f"⚠️ {name} (sin contenido o error)"
            except Exception as e:
                PREINDEX_STATUS["errors"] += 1
                msg = f"❌ {name}: {e}"

            PREINDEX_STATUS["log"].append(msg)
            PREINDEX_STATUS["current_file"] = name

    PREINDEX_STATUS["indexed"] += reused   # sumar los recuperados del caché
    PREINDEX_STATUS["running"] = False
    PREINDEX_STATUS["done"]    = True
    print(f"✅ Pre-indexación completa: {PREINDEX_STATUS['indexed']} OK "
          f"({reused} de caché, {PREINDEX_STATUS['indexed']-reused} nuevos), "
          f"{PREINDEX_STATUS['errors']} errores.")


# =======================================
# LIFESPAN: LIMPIEZA + PRE-INDEXACIÓN
# =======================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Servidor iniciado — limpiando sesiones de usuario anteriores...")
    delete_user_conversations()   # ← solo borra sesiones de usuario, NO índices de la BD
    start_cleanup_scheduler()

    # Lanzar pre-indexación en hilo de fondo (reutiliza índices existentes si los hay)
    preindex_thread = threading.Thread(target=run_preindex, daemon=True)
    preindex_thread.start()

    yield

    print("🛑 Servidor apagado — eliminando sesiones de usuario...")
    delete_user_conversations()   # ← conserva índices de la BD para el próximo arranque

app = FastAPI(title="CFE Intelligent Document & Vision API", version="4.2", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("⛔ GROQ_API_KEY no encontrada en el archivo .env")

# =======================================
# CONFIGURACIÓN DE MODELOS Y RUTAS PERSISTENTES
# =======================================
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"   # Soporta visión + texto técnico complejo
TEXT_MODEL   = "meta-llama/llama-4-scout-17b-16e-instruct"   # Mismo modelo: rápido, preciso y multimodal

MAX_DOCUMENTS       = 150
UPLOAD_DIR          = "uploaded_pdfs"
XAMPP_DOCS_PATH     = r"C:\xampp\htdocs\ia_docs"
APACHE_BASE_URL     ="http://localhost/ia_docs"
SUPPORTED_EXTENSIONS = [".pdf"]
INDICES_BASE_DIR    = "stored_conversations"
BD_INDICES_DIR      = os.path.join(INDICES_BASE_DIR, "bd_indices")   # ← carpeta dedicada para índices de BD (persistente)
METADATA_FILE       = os.path.join(INDICES_BASE_DIR, "conversations.json")
TEMP_SESSIONS_FILE  = os.path.join(INDICES_BASE_DIR, "temp_sessions.json")
PREINDEX_MAP_FILE   = os.path.join(BD_INDICES_DIR, "preindex_map.json")   # ← vive dentro de bd_indices

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(INDICES_BASE_DIR, exist_ok=True)
os.makedirs(BD_INDICES_DIR, exist_ok=True)

# ── Embeddings ──
embeddings = HuggingFaceEmbeddings(
    model_name="intfloat/multilingual-e5-small",
    encode_kwargs={"normalize_embeddings": True},
    model_kwargs={"device": "cpu"},
)

# ── Pool de hilos ──
MAX_WORKERS = min(8, (os.cpu_count() or 4) * 2)
_executor   = ThreadPoolExecutor(max_workers=MAX_WORKERS)
GROQ_CONCURRENCY = 6

CANCELLATION_TOKENS = {}

FILE_LOCK = threading.Lock()

# ── Caché de índices FAISS en memoria (evita load_local en cada consulta) ──
_FAISS_CACHE: dict[str, object] = {}

def _get_conv_dir(conv_id: str, meta: dict = None) -> str:
    """
    Devuelve la ruta correcta del índice FAISS según el tipo de conversación:
    - Tipo 'xampp' → BD_INDICES_DIR/conv_id  (persistente, nunca se borra solo)
    - Otros tipos  → INDICES_BASE_DIR/conv_id (sesión de usuario)
    Si meta no se pasa, intenta inferirlo por prefijo del conv_id.
    """
    if meta is None:
        meta = load_metadata()
    conv_type = meta.get(conv_id, {}).get("type", "")
    if conv_type == "xampp" or conv_id.startswith("xampp_"):
        return os.path.join(BD_INDICES_DIR, conv_id)
    return os.path.join(INDICES_BASE_DIR, conv_id)

def load_preindex_map() -> dict:
    """
    Carga el mapa de pre-indexación persistente desde disco.
    Formato: { relative_path: { "conv_id": str, "mtime": float, "size": int } }
    También acepta formato legado { relative_path: conv_id } y lo migra automáticamente.
    """
    os.makedirs(BD_INDICES_DIR, exist_ok=True)
    if os.path.exists(PREINDEX_MAP_FILE):
        try:
            with open(PREINDEX_MAP_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Migración automática: si los valores son strings (formato legado), convertir
            migrated = False
            for key, val in list(data.items()):
                if isinstance(val, str):
                    data[key] = {"conv_id": val, "mtime": 0.0, "size": 0}
                    migrated = True
            if migrated:
                save_preindex_map(data)
                print("⚙️  Mapa de pre-indexación migrado al formato extendido (mtime/size).")
            return data
        except Exception:
            return {}
    return {}

def save_preindex_map(pmap: dict):
    """Guarda el mapa de pre-indexación en bd_indices/ (sobrevive reinicios)."""
    os.makedirs(BD_INDICES_DIR, exist_ok=True)
    with open(PREINDEX_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(pmap, f, ensure_ascii=False, indent=4)

def _get_file_fingerprint(full_path: str) -> tuple:
    """Devuelve (mtime, size) de un archivo para detectar cambios."""
    try:
        stat = os.stat(full_path)
        return stat.st_mtime, stat.st_size
    except Exception:
        return 0.0, 0

def _file_changed(rel_path: str, full_path: str, pmap: dict) -> bool:
    """Devuelve True si el archivo fue modificado desde la última indexación."""
    entry = pmap.get(rel_path)
    if not entry:
        return True
    mtime, size = _get_file_fingerprint(full_path)
    stored_mtime = entry.get("mtime", 0.0) if isinstance(entry, dict) else 0.0
    stored_size  = entry.get("size", 0)    if isinstance(entry, dict) else 0
    # Considerar cambiado si mtime o size difieren (tolerancia 2s para FAT32/NTFS)
    return abs(mtime - stored_mtime) > 2.0 or size != stored_size

def _pmap_conv_id(value) -> str:
    """Extrae el conv_id de una entrada del preindex_map, sea dict o string."""
    if isinstance(value, dict):
        return value["conv_id"]
    return value   # formato legado: ya es un string

def load_metadata() -> dict:
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_metadata(meta: dict):
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=4)

def load_temp_sessions() -> dict:
    if os.path.exists(TEMP_SESSIONS_FILE):
        try:
            with open(TEMP_SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_temp_sessions(sessions: dict):
    with open(TEMP_SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=4)

def register_temp_session(conversation_id: str):
    sessions = load_temp_sessions()
    sessions[conversation_id] = {
        "created_at": datetime.now().isoformat(),
        "last_accessed": datetime.now().isoformat()
    }
    save_temp_sessions(sessions)

def unregister_temp_session(conversation_id: str):
    sessions = load_temp_sessions()
    if conversation_id in sessions:
        del sessions[conversation_id]
        save_temp_sessions(sessions)

def cleanup_expired_sessions(max_age_hours: int = 24):
    sessions = load_temp_sessions()
    now = datetime.now()
    expired = []
    
    for conv_id, data in sessions.items():
        try:
            created_at = datetime.fromisoformat(data["created_at"])
            age_hours = (now - created_at).total_seconds() / 3600
            if age_hours > max_age_hours:
                expired.append(conv_id)
        except Exception:
            expired.append(conv_id)
    
    for conv_id in expired:
        delete_conversation_files(conv_id)
        if conv_id in sessions:
            del sessions[conv_id]
    
    if expired:
        save_temp_sessions(sessions)
    
    return len(expired)

def delete_conversation_files(conversation_id: str):
    conv_dir = _get_conv_dir(conversation_id)
    if os.path.exists(conv_dir):
        try:
            shutil.rmtree(conv_dir)
            _FAISS_CACHE.pop(conv_dir, None)   # invalidar caché
            print(f"🧹 Limpiados archivos de conversación: {conversation_id}")
        except Exception as e:
            print(f"⚠️ Error limpiando {conversation_id}: {e}")

def delete_user_conversations():
    """
    Borra únicamente las conversaciones subidas por el usuario (tipo 'pdf' y 'folder').
    Los índices pre-indexados de la BD (tipo 'xampp') se conservan en BD_INDICES_DIR
    para no tener que re-indexar al reiniciar el servidor.
    """
    meta = load_metadata()
    xampp_ids = {cid for cid, data in meta.items() if data.get("type") in ("xampp", "xampp_folder")}

    # Conservar en metadata solo los índices de BD
    new_meta = {cid: data for cid, data in meta.items() if cid in xampp_ids}

    # Borrar directorios de conversaciones de usuario (NO tocar BD_INDICES_DIR)
    if os.path.exists(INDICES_BASE_DIR):
        for item in os.listdir(INDICES_BASE_DIR):
            item_path = os.path.join(INDICES_BASE_DIR, item)
            # Proteger bd_indices/ y los archivos JSON
            if item == "bd_indices" or not os.path.isdir(item_path):
                continue
            if item not in xampp_ids:
                try:
                    shutil.rmtree(item_path)
                    _FAISS_CACHE.pop(item_path, None)
                except Exception as e:
                    print(f"⚠️ Error eliminando índice de usuario {item_path}: {e}")

    save_metadata(new_meta)

    # Limpiar temp_sessions (solo sesiones de usuario)
    if os.path.exists(TEMP_SESSIONS_FILE):
        try:
            os.remove(TEMP_SESSIONS_FILE)
        except:
            pass

    # Limpiar archivos PDF subidos por el usuario
    if os.path.exists(UPLOAD_DIR):
        for item in os.listdir(UPLOAD_DIR):
            item_path = os.path.join(UPLOAD_DIR, item)
            try:
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except Exception as e:
                print(f"⚠️ Error eliminando archivo {item_path}: {e}")

    os.makedirs(INDICES_BASE_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    print(f"🧹 Sesiones de usuario limpiadas. Índices BD conservados: {len(xampp_ids)}.")

def delete_all_conversations():
    if os.path.exists(METADATA_FILE):
        try:
            os.remove(METADATA_FILE)
        except:
            pass
    
    if os.path.exists(TEMP_SESSIONS_FILE):
        try:
            os.remove(TEMP_SESSIONS_FILE)
        except:
            pass

    if os.path.exists(INDICES_BASE_DIR):
        for item in os.listdir(INDICES_BASE_DIR):
            item_path = os.path.join(INDICES_BASE_DIR, item)
            if os.path.isdir(item_path):
                try:
                    shutil.rmtree(item_path)
                except Exception as e:
                    print(f"⚠️ Error eliminando índice {item_path}: {e}")

    if os.path.exists(UPLOAD_DIR):
        for item in os.listdir(UPLOAD_DIR):
            item_path = os.path.join(UPLOAD_DIR, item)
            try:
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except Exception as e:
                print(f"⚠️ Error eliminando archivo {item_path}: {e}")

    os.makedirs(INDICES_BASE_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    print("🧹 Limpieza total de sesión completada.")

def start_cleanup_scheduler():
    def cleanup_loop():
        while True:
            time.sleep(3600)
            cleaned = cleanup_expired_sessions(max_age_hours=24)
            if cleaned > 0:
                print(f"🧹 Limpieza automática: {cleaned} sesiones expiradas eliminadas")
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()

# =======================================
# EXTRACCIÓN DE PDF
# =======================================
def _extract_pages_data(file_path: str, cancel_token: str = None) -> list[dict]:
    pages_data = []
    file_name  = os.path.basename(file_path)

    with fitz.open(file_path) as pdf:
        for page_num, page in enumerate(pdf):
            if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
                break

            text = page.get_text().strip()
            has_images = len(page.get_images()) > 0
            needs_vision = has_images and len(text) < 300

            img_b64 = None
            if needs_vision:
                pix = page.get_pixmap(dpi=72)
                img_b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")

            pages_data.append({
                "page_num": page_num,
                "file_name": file_name,
                "file_path": file_path,
                "text": text,
                "needs_vision": needs_vision,
                "img_b64": img_b64,
            })
    return pages_data

def _analyze_page(page_data: dict, cancel_token: str = None) -> Document:
    if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
        return None

    content = (f"ARCHIVO: {page_data['file_name']}\n"
               f"PÁGINA: {page_data['page_num'] + 1}\n")

    if page_data["text"]:
        content += f"CONTENIDO TEXTUAL:\n{page_data['text']}\n"

    if page_data["needs_vision"] and page_data["img_b64"]:
        try:
            llm = ChatGroq(model=VISION_MODEL, api_key=GROQ_API_KEY, temperature=0.0)
            msg = HumanMessage(content=[
                {"type": "text", "text": "Eres ingeniero CFE. Describe técnicamente: equipos, conexiones, valores numéricos, nomenclaturas. Sé conciso."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{page_data['img_b64']}"}}
            ])
            response = llm.invoke([msg])
            content += f"\n[DESCRIPCIÓN TÉCNICA DE PLANO/IMAGEN]:\n{response.content}\n"
        except Exception as ve:
            print(f"⚠️ Error visual — {page_data['file_name']} pág.{page_data['page_num']+1}: {ve}")

    return Document(
        page_content=content,
        metadata={"source": page_data["file_path"], "page": page_data["page_num"] + 1},
    )

def extract_pdf_parallel(file_path: str, cancel_token: str = None) -> list[Document]:
    pages_data = _extract_pages_data(file_path, cancel_token)
    documents = [None] * len(pages_data)

    text_only = [p for p in pages_data if not p["needs_vision"]]
    need_vision = [p for p in pages_data if p["needs_vision"]]

    for pd_item in text_only:
        if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
            return []
        documents[pd_item["page_num"]] = _analyze_page(pd_item, cancel_token)

    if need_vision:
        with ThreadPoolExecutor(max_workers=GROQ_CONCURRENCY) as vis_pool:
            futures = {vis_pool.submit(_analyze_page, pd_item, cancel_token): pd_item["page_num"] for pd_item in need_vision}
            for future in as_completed(futures):
                if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
                    break
                page_num = futures[future]
                try:
                    documents[page_num] = future.result()
                except Exception as e:
                    print(f"⚠️ Error en pág.{page_num}: {e}")

    return [doc for doc in documents if doc is not None]

def _process_single_pdf(file_path: str, cancel_token: str = None) -> list[Document]:
    try:
        if cancel_token and CANCELLATION_TOKENS.get(cancel_token) == True:
            return []
        return extract_pdf_parallel(file_path, cancel_token)
    except Exception as e:
        print(f"⚠️ Omitiendo {os.path.basename(file_path)}: {e}")
        return []

# =======================================
# ESCANEAR DOCUMENTOS EN XAMPP/APACHE
# =======================================

def scan_xampp_documents():
    documents = []

    if not os.path.exists(XAMPP_DOCS_PATH):
        return documents

    for root, dirs, files in os.walk(XAMPP_DOCS_PATH):

        for file in files:
            ext = os.path.splitext(file)[1].lower()

            if ext not in SUPPORTED_EXTENSIONS:
                continue

            full_path = os.path.join(root, file)

            relative_path = os.path.relpath(full_path, XAMPP_DOCS_PATH)

            documents.append({
                "name": file,
                "relative_path": relative_path.replace("\\", "/"),
                "full_path": full_path,
                "type": "file",
                "url": f"{APACHE_BASE_URL}/{relative_path.replace(os.sep, '/')}"
            })

    return documents

@app.get("/xampp_documents/")
async def xampp_documents():
    docs = scan_xampp_documents()
    # Añadir flag indicando si cada documento ya está pre-indexado
    for doc in docs:
        doc["preindexed"] = doc["relative_path"] in PREINDEX_MAP
    return {
        "total": len(docs),
        "documents": docs
    }

@app.get("/preindex_ready/")
async def preindex_ready():
    """
    Endpoint liviano para que el frontend sepa si todos los documentos de la BD
    ya están pre-indexados y listos para responder sin espera.
    """
    total_docs = len(scan_xampp_documents())
    indexed    = len(PREINDEX_MAP)
    ready      = PREINDEX_STATUS["done"] or (not PREINDEX_STATUS["running"] and indexed > 0)
    return {
        "ready":   ready,
        "indexed": indexed,
        "total":   total_docs,
        "pending": max(0, total_docs - indexed)
    }


@app.get("/preindex_status/")
async def preindex_status():
    """Devuelve el estado actual de la pre-indexación al arranque."""
    return {
        "running":      PREINDEX_STATUS["running"],
        "done":         PREINDEX_STATUS["done"],
        "total":        PREINDEX_STATUS["total"],
        "indexed":      PREINDEX_STATUS["indexed"],
        "errors":       PREINDEX_STATUS["errors"],
        "current_file": PREINDEX_STATUS["current_file"],
        "log":          PREINDEX_STATUS["log"][-20:],   # últimos 20 mensajes
    }

# =======================================
# INDEXAR DOCUMENTO DE XAMPP
# (usa el índice pre-generado si ya está listo)
# =======================================

# =======================================
# ENDPOINT: SELECCIÓN INSTANTÁNEA DE DOCUMENTO BD (SIN RE-INDEXAR)
# =======================================
@app.post("/select_xampp_document/")
async def select_xampp_document(path: str = Form(...)):
    """
    Selección instantánea de un documento de la BD.
    ✅ NUNCA vuelve a leer el PDF si ya existe el índice.
    ✅ Respuesta inmediata (< 50ms).
    """
    # Normalizar path
    path = path.replace("\\", "/").strip("/")
    
    # Sincronizar mapa desde disco
    pmap_disk = load_preindex_map()
    # Actualizar PREINDEX_MAP en memoria extrayendo solo conv_id (nuevo formato dict)
    for rel, entry in pmap_disk.items():
        PREINDEX_MAP[rel] = entry["conv_id"] if isinstance(entry, dict) else entry
    
    # Caso 1: Ya está pre-indexado (RESPUESTA INMEDIATA)
    if path in PREINDEX_MAP:
        conv_id = _pmap_conv_id(PREINDEX_MAP[path])
        meta = load_metadata()
        conv_dir = os.path.join(BD_INDICES_DIR, conv_id)   # ← siempre en bd_indices/
        
        # Validar que el índice existe físicamente
        if conv_id in meta and os.path.exists(conv_dir):
            print(f"⚡ Selección instantánea (caché): {path} → {conv_id}")
            return {
                "conversation_id": conv_id,
                "ready": True,
                "message": "✅ Documento listo para preguntar"
            }
        else:
            # Índice huérfano - limpiar referencia corrupta
            PREINDEX_MAP.pop(path, None)
            pmap_disk.pop(path, None)
            save_preindex_map(pmap_disk)
    
    # Caso 2: No está indexado - ERROR (esto NO debería pasar si la pre-indexación funciona)
    # En lugar de indexar on-demand (que causa failed to fetch), devolvemos error controlado
    return JSONResponse(
        status_code=404,
        content={
            "error": "Documento no indexado aún",
            "message": "La pre-indexación está en progreso. Por favor espera unos segundos y vuelve a intentar.",
            "pending": True
        }
    )


# =======================================
# ENDPOINT: SELECCIÓN DE CARPETA BD (SIN RE-LEER PDFs)
# =======================================
from fastapi import Body

@app.post("/index_xampp_folder/")
async def index_xampp_folder(
    data: dict = Body(...)  # ← Recibir JSON en lugar de Form
):
    """
    Indexa o recupera una carpeta de la BD (incluye subcarpetas).
    Recibe JSON con folder_path, folder_name y paths.
    """
    try:
        folder_path = data.get("folder_path", "").replace("\\", "/").strip("/")
        folder_name = data.get("folder_name", "")
        paths = data.get("paths", [])
        
        print(f"📁 Indexando carpeta: {folder_path}")
        print(f"📄 Documentos recibidos: {len(paths)}")
        
        meta = load_metadata()
        
        # Sincronizar mapa de pre-indexación
        pmap_disk = load_preindex_map()
        for _rel, _entry in pmap_disk.items():
            PREINDEX_MAP[_rel] = _entry["conv_id"] if isinstance(_entry, dict) else _entry
        
        # Atajo 1: La carpeta completa ya fue indexada como unidad
        existing = next(
            (cid for cid, conv_data in meta.items()
             if conv_data.get("type") == "xampp_folder" and conv_data.get("folder_path") == folder_path),
            None
        )
        if existing and os.path.exists(os.path.join(BD_INDICES_DIR, existing)):
            print(f"⚡ Carpeta ya indexada como unidad: {existing}")
            return {
                "conversation_id": existing,
                "ready": True,
                "message": "✅ Carpeta lista para preguntar"
            }
        
        # Construir lista de documentos a partir de los paths recibidos
        docs_in_folder = []
        for rel_path in paths:
            rel_path = rel_path.replace("\\", "/").strip("/")
            full_path = os.path.join(XAMPP_DOCS_PATH, rel_path)
            if os.path.exists(full_path):
                docs_in_folder.append({
                    "name": os.path.basename(full_path),
                    "relative_path": rel_path,
                    "full_path": full_path,
                    "type": "file",
                    "url": f"{APACHE_BASE_URL}/{rel_path}"
                })
        
        if not docs_in_folder:
            return JSONResponse(status_code=404, content={"error": "No se encontraron documentos en la carpeta."})
        
        print(f"📊 Documentos encontrados: {len(docs_in_folder)}")
        
        # Clasificar documentos
        preindexed_ids = []
        missing_docs = []
        
        for doc in docs_in_folder:
            rel_path = doc["relative_path"]
            raw = PREINDEX_MAP.get(rel_path)
            if raw is not None:
                conv_id = _pmap_conv_id(raw)
                conv_dir = os.path.join(BD_INDICES_DIR, conv_id)
                if conv_id in meta and os.path.exists(conv_dir):
                    preindexed_ids.append((conv_id, conv_dir))
                    print(f"  ✅ Pre-indexado: {rel_path}")
                else:
                    missing_docs.append(doc)
                    print(f"  ⚠️ Índice huérfano: {rel_path}")
            else:
                missing_docs.append(doc)
                print(f"  ❌ No indexado: {rel_path}")
        
        print(f"📈 Pre-indexados: {len(preindexed_ids)}, Pendientes: {len(missing_docs)}")
        
        # Si NO hay documentos faltantes → fusión RÁPIDA
        if not missing_docs and preindexed_ids:
            print(f"⚡ Fusión instantánea de {len(preindexed_ids)} índices")
            
            conv_id = f"xamppfolder_{uuid.uuid4().hex[:8]}"
            conv_dir = os.path.join(BD_INDICES_DIR, conv_id)
            os.makedirs(conv_dir, exist_ok=True)
            
            loop = asyncio.get_event_loop()
            
            def _merge_faiss_only():
                base_id, base_dir = preindexed_ids[0]
                merged = FAISS.load_local(base_dir, embeddings, allow_dangerous_deserialization=True)
                for _, extra_dir in preindexed_ids[1:]:
                    extra = FAISS.load_local(extra_dir, embeddings, allow_dangerous_deserialization=True)
                    merged.merge_from(extra)
                merged.save_local(conv_dir)
                return len(preindexed_ids)
            
            docs_count = await loop.run_in_executor(_executor, _merge_faiss_only)
            
            meta[conv_id] = {
                "id": conv_id,
                "title": f"Carpeta: {folder_name}",
                "type": "xampp_folder",
                "target_name": f"{folder_name} ({docs_count} archivos)",
                "file_path": conv_dir,
                "folder_path": folder_path,
                "history": [],
                "created_at": datetime.now().isoformat()
            }
            save_metadata(meta)
            
            return {
                "conversation_id": conv_id,
                "ready": True,
                "message": f"✅ Carpeta lista ({docs_count} documentos pre-indexados)"
            }
        
        # Caso 2: Hay documentos faltantes - procesar SOLO los nuevos
        print(f"⚠️ Procesando {len(missing_docs)} documentos faltantes...")
        
        conv_id = f"xamppfolder_{uuid.uuid4().hex[:8]}"
        conv_dir = os.path.join(BD_INDICES_DIR, conv_id)
        os.makedirs(conv_dir, exist_ok=True)
        
        loop = asyncio.get_event_loop()
        
        # Procesar SOLO los documentos faltantes
        new_documents = []
        for doc in missing_docs:
            full_path = doc["full_path"]
            ext = os.path.splitext(full_path)[1].lower()
            print(f"  📖 Procesando: {doc['name']}")
            
            if ext == ".pdf":
                raw_docs = await loop.run_in_executor(_executor, partial(extract_pdf_parallel, full_path))
                new_documents.extend(raw_docs)
            elif ext == ".txt":
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                new_documents.append(Document(page_content=content, metadata={"source": full_path, "page": 1}))
        
        # Dividir documentos nuevos
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        new_chunks = splitter.split_documents(new_documents) if new_documents else []
        print(f"📦 Chunks generados: {len(new_chunks)}")
        
        def _build_mixed_index():
            if new_chunks:
                db = FAISS.from_documents(new_chunks, embeddings)
                print(f"  Base creada con {len(new_chunks)} chunks")
            elif preindexed_ids:
                _, base_dir = preindexed_ids[0]
                db = FAISS.load_local(base_dir, embeddings, allow_dangerous_deserialization=True)
                preindexed_ids.pop(0)
                print(f"  Base cargada desde índice existente")
            else:
                raise Exception("No hay documentos para indexar")
            
            for _, extra_dir in preindexed_ids:
                extra_store = FAISS.load_local(extra_dir, embeddings, allow_dangerous_deserialization=True)
                db.merge_from(extra_store)
                print(f"  Fusionado índice adicional")
            
            db.save_local(conv_dir)
            return len(new_chunks), len(preindexed_ids)
        
        await loop.run_in_executor(_executor, _build_mixed_index)
        
        meta[conv_id] = {
            "id": conv_id,
            "title": f"Carpeta: {folder_name}",
            "type": "xampp_folder",
            "target_name": f"{folder_name} ({len(docs_in_folder)} archivos)",
            "file_path": conv_dir,
            "folder_path": folder_path,
            "history": [],
            "created_at": datetime.now().isoformat()
        }
        save_metadata(meta)
        
        print(f"✅ Carpeta indexada correctamente: {conv_id}")
        
        return {
            "conversation_id": conv_id,
            "ready": True,
            "message": f"✅ Carpeta lista ({len(docs_in_folder)} documentos totales)"
        }
        
    except Exception as e:
        print(f"❌ Error en index_xampp_folder: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})


# =======================================
# ENDPOINT DE VERIFICACIÓN RÁPIDA (para el frontend)
# =======================================
@app.get("/check_document_ready/")
async def check_document_ready(path: str):
    """
    Endpoint ultra-rápido para que el frontend verifique si un documento está listo.
    Sin bloqueos, sin lecturas de disco pesadas.
    """
    path = path.replace("\\", "/").strip("/")
    
    # Verificar en memoria
    if path in PREINDEX_MAP:
        conv_id = _pmap_conv_id(PREINDEX_MAP[path])
        meta = load_metadata()
        conv_dir = os.path.join(BD_INDICES_DIR, conv_id)   # ← bd_indices/
        
        if conv_id in meta and os.path.exists(conv_dir):
            return {
                "ready": True,
                "conversation_id": conv_id,
                "message": "Documento listo"
            }
    
    return {
        "ready": False,
        "message": "Documento aún no indexado"
    }

def get_docs_in_xampp_folder_recursive(folder_path: str) -> list:
    """
    Escanea recursivamente una carpeta dentro de XAMPP_DOCS_PATH
    y devuelve todos los documentos PDF/TXT encontrados.
    """
    folder_path = folder_path.replace("\\", "/").strip("/")
    all_docs = []
    full_folder_path = os.path.join(XAMPP_DOCS_PATH, folder_path)
    
    if not os.path.exists(full_folder_path):
        return all_docs
    
    for root, dirs, files in os.walk(full_folder_path):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            
            full_path = os.path.join(root, file)
            relative_path = os.path.relpath(full_path, XAMPP_DOCS_PATH).replace("\\", "/")
            
            all_docs.append({
                "name": file,
                "relative_path": relative_path,
                "full_path": full_path,
                "type": "file",
                "url": f"{APACHE_BASE_URL}/{relative_path}"
            })
    
    return all_docs

@app.post("/index_xampp_document/")
async def index_xampp_document(path: str = Form(...)):

    # Normalizar path (consistencia con select_xampp_document)
    path = path.replace("\\", "/").strip("/")

    # ── Atajo: si ya fue pre-indexado, devolver el ID directamente ──
    if path in PREINDEX_MAP:
        conv_id = _pmap_conv_id(PREINDEX_MAP[path])
        meta    = load_metadata()
        if conv_id in meta:
            print(f"⚡ Usando índice pre-generado para: {path} → {conv_id}")
            return {
                "conversation_id": conv_id,
                "message": "✅ Documento ya pre-indexado — listo para preguntar"
            }
        # Si el índice fue eliminado (raro), caer al flujo normal
        del PREINDEX_MAP[path]

    full_path = os.path.join(XAMPP_DOCS_PATH, path)

    if not os.path.exists(full_path):
        return JSONResponse(
            status_code=404,
            content={"error": "Documento no encontrado"}
        )

    try:

        ext = os.path.splitext(full_path)[1].lower()

        raw_docs = []

        if ext == ".pdf":
            loop = asyncio.get_event_loop()
            raw_docs = await loop.run_in_executor(_executor, partial(extract_pdf_parallel, full_path))

        elif ext == ".txt":

            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            raw_docs = [
                Document(
                    page_content=content,
                    metadata={"source": full_path, "page": 1}
                )
            ]

        else:
            return JSONResponse(
                status_code=400,
                content={"error": "Formato no soportado"}
            )

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100
        )

        docs = splitter.split_documents(raw_docs)

        meta = load_metadata()

        conv_id  = f"xampp_{uuid.uuid4().hex[:8]}"
        conv_dir = os.path.join(BD_INDICES_DIR, conv_id)   # ← carpeta persistente

        vectorstore = FAISS.from_documents(docs, embeddings)
        vectorstore.save_local(conv_dir)

        file_name = os.path.basename(full_path)

        meta[conv_id] = {
            "id":            conv_id,
            "title":         file_name,
            "type":          "xampp",
            "target_name":   file_name,
            "file_path":     full_path,
            "file_path_bd":  conv_dir,
            "relative_path": path,
            "history":       [],
            "created_at":    datetime.now().isoformat()
        }

        save_metadata(meta)
        # NO registrar como sesión temporal — índice permanente de la BD

        # Persistir en disco con fingerprint para sobrevivir reinicios
        mtime, size = _get_file_fingerprint(full_path)
        PREINDEX_MAP[path] = conv_id
        pmap = load_preindex_map()
        pmap[path] = {"conv_id": conv_id, "mtime": mtime, "size": size}
        save_preindex_map(pmap)

        return {
            "conversation_id": conv_id,
            "message": "✅ Documento XAMPP indexado correctamente"
        }

    except Exception as e:

        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

def get_docs_in_xampp_folder(folder_path: str):
    folder_path = folder_path.replace("\\", "/").strip("/")
    docs = []

    for doc in scan_xampp_documents():
        rel = doc["relative_path"].replace("\\", "/")
        if rel == folder_path or rel.startswith(folder_path + "/"):
            docs.append(doc)

    return docs


@app.post("/index_xampp_folder/")
async def index_xampp_folder(folder_path: str = Form(...), folder_name: str = Form(...)):
    try:
        meta = load_metadata()

        folder_path = folder_path.replace("\\", "/").strip("/")

        # ── Atajo 1: carpeta ya fue indexada antes como unidad ──
        existing = next(
            (
                cid for cid, data in meta.items()
                if data.get("type") == "xampp_folder" and data.get("folder_path") == folder_path
            ),
            None
        )
        if existing and os.path.exists(os.path.join(INDICES_BASE_DIR, existing)):
            print(f"⚡ Carpeta ya indexada — devolviendo ID directo: {existing}")
            return {
                "conversation_id": existing,
                "message": "✅ Carpeta ya pre-leída — lista para preguntar"
            }

        docs_in_folder = get_docs_in_xampp_folder(folder_path)
        if not docs_in_folder:
            return JSONResponse(status_code=404, content={"error": "No se encontraron documentos en esa carpeta."})

        # ── Atajo 2: TODOS los documentos ya están pre-indexados individualmente ──
        # Fusionar los índices FAISS en memoria sin leer un solo PDF
        preindexed_ids = []
        pending_docs   = []
        for doc in docs_in_folder:
            rel = doc["relative_path"]
            raw = PREINDEX_MAP.get(rel)
            if raw is not None:
                cid = raw["conv_id"] if isinstance(raw, dict) else raw   # ← seguro siempre
                cdir = os.path.join(BD_INDICES_DIR, cid)
                if cid in meta and os.path.exists(cdir):
                    preindexed_ids.append((cid, cdir))
                else:
                    pending_docs.append(doc)
            else:
                pending_docs.append(doc)

        conv_id  = f"xamppfolder_{uuid.uuid4().hex[:8]}"
        conv_dir = os.path.join(BD_INDICES_DIR, conv_id)   # ← bd_indices/
        os.makedirs(conv_dir, exist_ok=True)

        if preindexed_ids and not pending_docs:
            # ✅ Caso ideal: todos pre-indexados — fusión instantánea
            print(f"⚡ Todos los {len(preindexed_ids)} docs ya pre-indexados — fusionando índices FAISS...")
            base_cid, base_dir = preindexed_ids[0]
            merged_store = await asyncio.get_event_loop().run_in_executor(
                _executor,
                partial(FAISS.load_local, base_dir, embeddings, allow_dangerous_deserialization=True)
            )
            for _, extra_dir in preindexed_ids[1:]:
                extra_store = await asyncio.get_event_loop().run_in_executor(
                    _executor,
                    partial(FAISS.load_local, extra_dir, embeddings, allow_dangerous_deserialization=True)
                )
                merged_store.merge_from(extra_store)

            merged_store.save_local(conv_dir)
            docs_count = len(preindexed_ids)
            chunks_count = 0   # no aplica en fusión

        else:
            # ⚙️ Caso mixto/nuevo: indexar los docs pendientes y fusionar con los ya listos
            all_documents = []
            loop = asyncio.get_event_loop()

            # Cargar documentos pendientes (no pre-indexados)
            for doc in pending_docs:
                full_path = doc["full_path"]
                ext = os.path.splitext(full_path)[1].lower()
                if ext == ".pdf":
                    raw_docs = await loop.run_in_executor(_executor, partial(extract_pdf_parallel, full_path))
                elif ext == ".txt":
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    raw_docs = [Document(page_content=content, metadata={"source": full_path, "page": 1})]
                else:
                    continue
                all_documents.extend(raw_docs)

            if not all_documents and not preindexed_ids:
                return JSONResponse(status_code=400, content={"error": "No se pudo extraer texto de la carpeta."})

            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
            docs_split = splitter.split_documents(all_documents) if all_documents else []

            if docs_split:
                db = FAISS.from_documents(docs_split, embeddings)
            else:
                # Solo había pre-indexados; cargar el primero como base
                _, base_dir = preindexed_ids[0]
                db = await asyncio.get_event_loop().run_in_executor(
                    _executor,
                    partial(FAISS.load_local, base_dir, embeddings, allow_dangerous_deserialization=True)
                )
                preindexed_ids = preindexed_ids[1:]

            # Fusionar los ya pre-indexados que haya
            for _, extra_dir in preindexed_ids:
                extra_store = await asyncio.get_event_loop().run_in_executor(
                    _executor,
                    partial(FAISS.load_local, extra_dir, embeddings, allow_dangerous_deserialization=True)
                )
                db.merge_from(extra_store)

            db.save_local(conv_dir)
            docs_count   = len(docs_in_folder)
            chunks_count = len(docs_split)

        meta[conv_id] = {
            "id": conv_id,
            "title": f"Carpeta: {folder_name}",
            "type": "xampp_folder",
            "target_name": f"{folder_name} ({len(docs_in_folder)} archivos)",
            "file_path": conv_dir,
            "folder_path": folder_path,
            "history": [],
            "created_at": datetime.now().isoformat()
        }
        save_metadata(meta)

        print(f"✅ Carpeta XAMPP lista. ID: {conv_id} — {len(docs_in_folder)} archivos")
        return {
            "conversation_id": conv_id,
            "message": "✅ Carpeta pre-leída e indexada correctamente"
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Error al indexar carpeta XAMPP '{folder_path}': {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

# =======================================
# ENDPOINTS DE CONVERSACIÓN
# =======================================
@app.get("/conversations/")
async def list_conversations():
    return load_metadata()

@app.post("/clear_conversation_history/")
async def clear_conversation_history(id: str = Form(...)):
    """
    Limpia el historial de chat de una conversación sin borrar el índice FAISS.
    Usado para conversaciones de tipo 'xampp' cuyos índices son permanentes.
    """
    meta = load_metadata()
    if id not in meta:
        return JSONResponse(status_code=404, content={"error": "Conversación no encontrada"})

    meta[id]["history"] = []
    save_metadata(meta)
    return {"message": f"✅ Historial de conversación {id} limpiado correctamente"}

@app.post("/delete_conversation/")
async def delete_conversation(id: str = Form(...)):
    meta = load_metadata()
    if id not in meta:
        return JSONResponse(status_code=404, content={"error": "Conversación no encontrada"})
    
    conv_data = meta[id]
    conv_dir = os.path.join(INDICES_BASE_DIR, id)
    if os.path.exists(conv_dir):
        try:
            shutil.rmtree(conv_dir)
        except Exception as e:
            print(f"⚠️ Error eliminando directorio {conv_dir}: {e}")
    
    del meta[id]
    save_metadata(meta)
    unregister_temp_session(id)

    # Si era un índice de BD, eliminarlo también del mapa persistente
    if conv_data.get("type") == "xampp":
        rel_path = conv_data.get("relative_path", "")
        pmap = load_preindex_map()
        if rel_path in pmap:
            del pmap[rel_path]
            save_preindex_map(pmap)
        if rel_path in PREINDEX_MAP:
            del PREINDEX_MAP[rel_path]

    return {"message": f"✅ Conversación {id} eliminada correctamente"}

# =======================================
# ENDPOINT: SUBIR PDF INDIVIDUAL
# =======================================
@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...), cancel_token: str = Form(None)):
    if not cancel_token:
        cancel_token = str(uuid.uuid4())
    CANCELLATION_TOKENS[cancel_token] = False

    try:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        loop = asyncio.get_event_loop()
        raw_docs = await loop.run_in_executor(_executor, partial(extract_pdf_parallel, file_path, cancel_token))

        if CANCELLATION_TOKENS.get(cancel_token) == True:
            if os.path.exists(file_path):
                os.remove(file_path)
            return JSONResponse(status_code=499, content={"error": "Lectura de PDF cancelada por el usuario."})

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = splitter.split_documents(raw_docs)

        meta = load_metadata()
        conv_idx = len(meta) + 1
        conv_id = f"conversacion_{conv_idx}"
        conv_dir = os.path.join(INDICES_BASE_DIR, conv_id)

        pdf_vectorstore = FAISS.from_documents(docs, embeddings)
        pdf_vectorstore.save_local(conv_dir)

        meta[conv_id] = {
            "id": conv_id,
            "title": f"Conversación {conv_idx}",
            "type": "pdf",
            "target_name": file.filename,
            "file_path": file_path,
            "history": [],
            "created_at": datetime.now().isoformat()
        }
        save_metadata(meta)
        register_temp_session(conv_id)

        return {
            "conversation_id": conv_id,
            "message": "✅ PDF procesado e indexado correctamente.",
            "pages": len(raw_docs),
            "chunks": len(docs)
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if cancel_token in CANCELLATION_TOKENS:
            del CANCELLATION_TOKENS[cancel_token]

# =======================================
# ENDPOINT: SUBIR CARPETA REMOTA (CORREGIDO)
# =======================================
@app.post("/upload_folder_remote/")
async def upload_folder_remote(files: List[UploadFile] = File(...), cancel_token: str = Form(None)):
    """
    Recibe múltiples archivos PDF simulando la subida de una carpeta completa 
    desde el entorno web remoto.
    """
    if not cancel_token:
        cancel_token = str(uuid.uuid4())
    CANCELLATION_TOKENS[cancel_token] = False
    
    saved_paths = []
    all_documents = []
    conversation_id = None
    
    try:
        print(f"📁 Recibidos {len(files)} archivos para procesar")
        
        # Filtrar solo PDFs y guardarlos
        pdf_files = [f for f in files if f.filename.lower().endswith('.pdf')]
        
        if not pdf_files:
            return JSONResponse(status_code=400, content={"error": "No se encontraron archivos PDF válidos en la carpeta subida."})
        
        print(f"📄 Procesando {len(pdf_files)} archivos PDF...")
        
        # Guardar archivos
        for file in pdf_files:
            if CANCELLATION_TOKENS.get(cancel_token) == True:
                print(f"🛑 Proceso cancelado por el usuario.")
                for path in saved_paths:
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except:
                            pass
                return JSONResponse(status_code=200, content={"message": "Proceso cancelado por el usuario", "cancelled": True})

            # Extraer el nombre base del archivo (sin rutas)
            base_filename = os.path.basename(file.filename)
            file_path = os.path.join(UPLOAD_DIR, base_filename)
            
            # Manejar duplicados
            counter = 1
            original_path = file_path
            while os.path.exists(file_path):
                name, ext = os.path.splitext(original_path)
                file_path = f"{name}_{counter}{ext}"
                counter += 1
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_paths.append(file_path)
            print(f"✅ Guardado: {os.path.basename(file_path)}")

        # Procesar cada PDF
        loop = asyncio.get_event_loop()
        for idx, path in enumerate(saved_paths):
            if CANCELLATION_TOKENS.get(cancel_token) == True:
                break
            
            print(f"🔍 Procesando ({idx+1}/{len(saved_paths)}): {os.path.basename(path)}")
            docs = await loop.run_in_executor(_executor, _process_single_pdf, path, cancel_token)
            if docs:
                all_documents.extend(docs)
                print(f"   ✓ Extraídas {len(docs)} páginas")

        if CANCELLATION_TOKENS.get(cancel_token) == True:
            for path in saved_paths:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except:
                        pass
            return JSONResponse(status_code=200, content={"message": "Proceso cancelado por el usuario", "cancelled": True})

        if not all_documents:
            return JSONResponse(status_code=400, content={"error": "No se pudo extraer texto de ningún documento técnico de la carpeta."})

        # Dividir en chunks e indexar
        print(f"📊 Total de documentos extraídos: {len(all_documents)}")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        final_splits = text_splitter.split_documents(all_documents)
        print(f"📦 Total de chunks generados: {len(final_splits)}")
        
        # Crear conversación
        meta = load_metadata()
        conv_idx = len(meta) + 1
        conversation_id = f"conversacion_{conv_idx}"
        conv_dir = _get_conv_dir(conversation_id)
        os.makedirs(conv_dir, exist_ok=True)
        
        # Crear índice FAISS
        db = FAISS.from_documents(final_splits, embeddings)
        db.save_local(conv_dir)
        
        # Obtener nombre de la carpeta (intentar extraer de la ruta original)
        folder_name = "Carpeta_Remota"
        if files and len(files) > 0:
            first_file = files[0].filename
            if '/' in first_file:
                folder_name = first_file.split('/')[0]
        
        # Guardar metadatos
        meta[conversation_id] = {
            "id": conversation_id,
            "title": f"Carpeta: {folder_name}",
            "type": "folder",
            "target_name": f"{folder_name} ({len(saved_paths)} PDFs)",
            "file_path": conv_dir,
            "history": [],
            "created_at": datetime.now().isoformat()
        }
        save_metadata(meta)
        register_temp_session(conversation_id)
        
        print(f"✅ Carpeta indexada correctamente. ID: {conversation_id}")
        
        return {
            "message": f"✅ Carpeta indexada con éxito. {len(saved_paths)} archivos cargados, {len(final_splits)} chunks creados.",
            "conversation_id": conversation_id,
            "files_processed": len(saved_paths),
            "chunks_created": len(final_splits)
        }

    except Exception as e:
        print(f"❌ Error al procesar carpeta remota: {e}")
        import traceback
        traceback.print_exc()
        for path in saved_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if cancel_token in CANCELLATION_TOKENS:
            del CANCELLATION_TOKENS[cancel_token]

# ── Helper: carga FAISS con caché en memoria ──────────────────────────────────
def _get_faiss_store(conv_dir: str):
    """Devuelve el vectorstore desde caché o lo carga desde disco."""
    if conv_dir not in _FAISS_CACHE:
        _FAISS_CACHE[conv_dir] = FAISS.load_local(
            conv_dir, embeddings, allow_dangerous_deserialization=True
        )
    return _FAISS_CACHE[conv_dir]

# ── Helper: actualiza historial limitando a MAX_HISTORY_PAIRS pares ───────────
MAX_HISTORY_PAIRS = 10   # máximo de pares user/assistant guardados por conversación

def _append_history(meta: dict, conv_id: str, question: str, answer: str, sources: list):
    history = meta[conv_id].get("history", [])
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer, "sources": sources})
    # Mantener solo los últimos N pares para evitar que el JSON crezca indefinidamente
    if len(history) > MAX_HISTORY_PAIRS * 2:
        history = history[-(MAX_HISTORY_PAIRS * 2):]
    meta[conv_id]["history"] = history

# ── Prompts compactos compartidos ─────────────────────────────────────────────
_STYLE_PERSONA = {
    "normal":   "Analista CFE. Responde profesionalmente según el contexto.",
    "amable":   "Analista CFE. Responde de forma amable y detallada.",
    "agresivo": "Analista CFE. Responde directo, técnico, sin rodeos.",
}

_TEMPLATE_PDF = """{persona}
Usa SOLO el contexto. Si no hay info suficiente, dilo.

Contexto:
{context}

Pregunta: {question}
Respuesta:"""

_TEMPLATE_FOLDER = """Ingeniero Analista CFE. Responde de forma técnica y precisa usando el contexto.

Contexto:
{context}

Pregunta: {question}
Respuesta:"""

# =======================================
# ENDPOINTS: CONSULTAS RAG
# =======================================
@app.post("/ask_pdf/")
async def ask_pdf(question: str = Form(...), style: str = Form("normal"), conversation_id: str = Form(...)):
    meta = load_metadata()
    if conversation_id not in meta:
        return JSONResponse(status_code=404, content={"error": "ID de conversación no válido."})

    conv_dir = _get_conv_dir(conversation_id)
    try:
        local_store = _get_faiss_store(conv_dir)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Error al cargar el índice: {e}"})

    persona = _STYLE_PERSONA.get(style, _STYLE_PERSONA["normal"])
    template = _TEMPLATE_PDF.replace("{persona}", persona)
    prompt = PromptTemplate(template=template, input_variables=["context", "question"])

    chain = RetrievalQA.from_chain_type(
        llm=ChatGroq(model=TEXT_MODEL, api_key=GROQ_API_KEY, temperature=0.2),
        retriever=local_store.as_retriever(search_type="mmr", search_kwargs={"k": 4}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, partial(chain.invoke, {"query": question}))
    sources = sorted(set(d.metadata["source"] for d in result["source_documents"]))

    _append_history(meta, conversation_id, question, result["result"], sources)
    save_metadata(meta)

    sessions = load_temp_sessions()
    if conversation_id in sessions:
        sessions[conversation_id]["last_accessed"] = datetime.now().isoformat()
        save_temp_sessions(sessions)

    return {"answer": result["result"], "sources": sources}

@app.post("/ask_folder/")
async def ask_folder(question: str = Form(...), conversation_id: str = Form(...)):
    meta = load_metadata()
    if conversation_id not in meta:
        return JSONResponse(status_code=404, content={"error": "ID de conversación no válido."})

    conv_dir = _get_conv_dir(conversation_id)
    try:
        local_store = _get_faiss_store(conv_dir)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Error al cargar el índice: {e}"})

    prompt = PromptTemplate(template=_TEMPLATE_FOLDER, input_variables=["context", "question"])
    chain = RetrievalQA.from_chain_type(
        llm=ChatGroq(model=TEXT_MODEL, api_key=GROQ_API_KEY, temperature=0.0),
        retriever=local_store.as_retriever(search_type="mmr", search_kwargs={"k": 5}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, partial(chain.invoke, {"query": question}))
    sources = sorted(set(d.metadata["source"] for d in result["source_documents"]))

    _append_history(meta, conversation_id, question, result["result"], sources)
    save_metadata(meta)

    sessions = load_temp_sessions()
    if conversation_id in sessions:
        sessions[conversation_id]["last_accessed"] = datetime.now().isoformat()
        save_temp_sessions(sessions)

    return {"answer": result["result"], "sources": sources}

# =======================================
# ENDPOINT DE VISTA PREVIA
# =======================================
@app.get("/preview/")
async def preview_file(path: str):
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": f"Archivo no encontrado en la ruta: {path}"})
    return FileResponse(path, media_type="application/pdf")

# =======================================
# ENDPOINTS DE LIMPIEZA
# =======================================
@app.post("/clear_index/")
async def clear_index():
    """
    Limpia SOLO sesiones de usuario (pdf / folder).
    Los índices de la BD en bd_indices/ se conservan — usa /reset_preindex/ para borrarlos.
    """
    global PREINDEX_MAP
    delete_user_conversations()   # ya protege bd_indices/
    _FAISS_CACHE.clear()
    return {"message": "✅ Sesiones de usuario e índices temporales eliminados. Caché de BD conservada."}

@app.post("/clear_all_sessions/")
async def clear_all_sessions():
    delete_user_conversations()
    return {"message": "✅ Sesiones de usuario eliminadas. Los índices de la BD se conservaron."}

@app.post("/reset_preindex/")
async def reset_preindex():
    """
    ⚠️ Borra TODA la caché de pre-indexación de la BD (bd_indices/).
    Al reiniciar el servidor, los documentos se re-leerán desde cero.
    Útil cuando se quiere forzar una re-indexación completa (ej. cambio masivo de documentos).
    """
    global PREINDEX_MAP

    bd_count = 0
    if os.path.exists(BD_INDICES_DIR):
        # Contar cuántos índices hay antes de borrar
        meta = load_metadata()
        bd_count = sum(1 for cid, data in meta.items() if data.get("type") in ("xampp", "xampp_folder"))
        try:
            shutil.rmtree(BD_INDICES_DIR)
            print(f"🗑️  Caché de BD eliminada ({bd_count} índices).")
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": f"Error al eliminar bd_indices/: {e}"})

    # Limpiar del metadata los registros de BD
    meta = load_metadata()
    new_meta = {cid: data for cid, data in meta.items() if data.get("type") not in ("xampp", "xampp_folder")}
    save_metadata(new_meta)

    # Limpiar caché en memoria
    PREINDEX_MAP.clear()
    _FAISS_CACHE.clear()

    # Recrear carpeta vacía
    os.makedirs(BD_INDICES_DIR, exist_ok=True)

    print(f"✅ Reset de pre-indexación completado. {bd_count} índices eliminados.")
    return {
        "message": f"✅ Caché de BD eliminada ({bd_count} índices). El servidor re-indexará desde cero al reiniciar.",
        "indices_deleted": bd_count
    }

@app.get("/preindex_cache_info/")
async def preindex_cache_info():
    """
    Devuelve información sobre el estado actual de la caché de pre-indexación.
    Útil para el frontend al mostrar cuántos documentos están en caché.
    """
    pmap = load_preindex_map()
    meta = load_metadata()
    bd_ids = {cid for cid, data in meta.items() if data.get("type") in ("xampp", "xampp_folder")}

    # Calcular tamaño total de bd_indices/
    total_size_mb = 0.0
    if os.path.exists(BD_INDICES_DIR):
        for dirpath, _, filenames in os.walk(BD_INDICES_DIR):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total_size_mb += os.path.getsize(fp) / (1024 * 1024)
                except Exception:
                    pass

    return {
        "cached_documents": len(pmap),
        "bd_conversations": len(bd_ids),
        "cache_dir": BD_INDICES_DIR,
        "cache_exists": os.path.isdir(BD_INDICES_DIR),
        "cache_size_mb": round(total_size_mb, 2),
        "preindex_map_file": PREINDEX_MAP_FILE,
        "map_file_exists": os.path.exists(PREINDEX_MAP_FILE)
    }

@app.get("/health")
async def health():
    meta = load_metadata()
    sessions = load_temp_sessions()
    return {
        "active_conversations": len(meta),
        "temp_sessions": len(sessions),
        "max_documents": MAX_DOCUMENTS,
        "vision_model": VISION_MODEL,
        "text_model": TEXT_MODEL,
        "workers": MAX_WORKERS,
        "status": "healthy"
    }

# =======================================
# SERVIR FRONTEND
# =======================================
from fastapi.staticfiles import StaticFiles

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)