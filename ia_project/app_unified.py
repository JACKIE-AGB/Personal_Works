import streamlit as st
import requests
import os
import tkinter as tk
from tkinter import filedialog
import time
from pathlib import Path

API_URL = "http://127.0.0.1:8001"

st.set_page_config(
    page_title="Enterprise Document Assistant - Nomic AI",
    layout="wide",
    page_icon="🧠"
)

st.markdown("""
<style>
    .stChatMessage { padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem; }
    .metric-card { background-color: #f0f2f6; padding: 1rem; border-radius: 0.5rem; text-align: center; }
    .active-doc-banner {
        background: linear-gradient(90deg, #1a472a, #2d6a4f);
        color: white;
        padding: 0.6rem 1rem;
        border-radius: 0.4rem;
        margin-bottom: 1rem;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

# ─── Estados de sesión ───────────────────────────────────────────────────────
if "pdf_messages" not in st.session_state:
    st.session_state.pdf_messages = []
if "folder_messages" not in st.session_state:
    st.session_state.folder_messages = []
if "folder_path" not in st.session_state:
    st.session_state.folder_path = ""
if "indexed" not in st.session_state:
    st.session_state.indexed = False
if "indexing_progress" not in st.session_state:
    st.session_state.indexing_progress = None
if "doc_count_info" not in st.session_state:
    st.session_state.doc_count_info = None


def select_folder():
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder_selected = filedialog.askdirectory(master=root)
    root.destroy()
    return folder_selected


def check_indexing_status():
    try:
        response = requests.get(f"{API_URL}/indexing_status")
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None


def check_health():
    try:
        response = requests.get(f"{API_URL}/health", timeout=2)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None


def get_pdf_info():
    try:
        r = requests.get(f"{API_URL}/pdf_info", timeout=2)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return {}


def get_folder_info():
    try:
        r = requests.get(f"{API_URL}/folder_info", timeout=2)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return {}


def get_folder_doc_count(path: str):
    try:
        r = requests.get(f"{API_URL}/folder_doc_count", params={"folder_path": path}, timeout=5)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None


# ─── Header ──────────────────────────────────────────────────────────────────
st.title("🧠 Asistente Inteligente Empresarial con Nomic Embed")
st.caption("Modelo de embeddings nomic-embed-text-v1.5 | Contexto de 8192 tokens | Alta precisión")

# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📊 Estado del Sistema")

    health = check_health()

    if health:
        st.success("✅ Backend conectado (Nomic Embed)")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("PDF Listo", "✅" if health.get('pdf_ready') else "❌")
        with col2:
            st.metric("Biblioteca", "✅" if health.get('folder_ready') else "❌")

        if health.get('indexing_in_progress', False):
            st.warning("🔄 Indexación en progreso...")

        st.divider()
        st.info(f"**Modelo:** {health.get('embedding_model', 'Nomic v1.5')}")
        st.info(f"**Contexto:** {health.get('chunk_size', 2000)} tokens")
        st.info(f"**Límite carpeta:** {health.get('max_documents', 100)} documentos")

        # Sincronizar estado de folder con health real del backend (bidireccional)
        if health.get('folder_ready'):
            st.session_state.indexed = True
        else:
            # El índice no existe en disco → resetear session state para evitar falsos positivos
            st.session_state.indexed = False
    else:
        st.error("❌ Backend desconectado")

    st.divider()
    st.caption("💡 **Ventajas Nomic Embed:**\n- 8192 tokens de contexto\n- Calidad superior (+11%)\n- 100+ idiomas\n- Eficiente en CPU")

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["📄 Documento Individual", "📚 Biblioteca Empresarial"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — DOCUMENTO INDIVIDUAL
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### 📄 Análisis de Documento Individual")

    pdf_ready = health.get('pdf_ready', False) if health else False
    pdf_info = get_pdf_info() if pdf_ready else {}

    # ── Banner: documento activo ──────────────────────────────────────────────
    if pdf_ready and pdf_info:
        st.markdown(
            f'<div class="active-doc-banner">'
            f'📄 Documento activo: <strong>{pdf_info.get("filename", "PDF indexado")}</strong> '
            f'— {pdf_info.get("pages", "?")} páginas · {pdf_info.get("chunks", "?")} segmentos'
            f'</div>',
            unsafe_allow_html=True
        )

    # ── Sección de carga (colapsable si ya hay PDF activo) ────────────────────
    upload_label = "🔄 Cambiar documento" if pdf_ready else "📤 Subir documento PDF"
    with st.expander(upload_label, expanded=not pdf_ready):
        col1, col2 = st.columns([2, 1])
        with col1:
            uploaded_file = st.file_uploader("Selecciona un PDF", type="pdf", key="pdf_upload")
        with col2:
            if uploaded_file and st.button("🚀 Procesar con Nomic", type="primary", use_container_width=True):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                with st.spinner("Procesando con Nomic Embed..."):
                    res = requests.post(f"{API_URL}/upload_pdf/", files=files)
                    if res.status_code == 200:
                        data = res.json()
                        st.success(
                            f"✅ {data.get('message')} — "
                            f"{data.get('pages', 0)} páginas, {data.get('chunks', 0)} segmentos"
                        )
                        st.rerun()
                    else:
                        st.error(f"❌ Error: {res.json().get('error', 'Desconocido')}")

        if pdf_ready:
            if st.button("🗑️ Eliminar índice PDF", use_container_width=True):
                requests.post(f"{API_URL}/clear_pdf/")
                st.session_state.pdf_messages = []
                st.success("✅ Índice PDF eliminado")
                time.sleep(1)
                st.rerun()

    # ── Chat (siempre visible si hay PDF listo) ───────────────────────────────
    if pdf_ready:
        col1, col2 = st.columns([3, 1])
        with col1:
            style = st.selectbox(
                "Estilo de respuesta", ["normal", "amable", "agresivo"],
                format_func=lambda x: {
                    "normal": "📝 Profesional",
                    "amable": "😊 Amable",
                    "agresivo": "⚡ Directo"
                }[x]
            )
        with col2:
            if st.button("🗑️ Limpiar chat", use_container_width=True):
                st.session_state.pdf_messages = []
                st.rerun()

        for msg in st.session_state.pdf_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("Pregunta sobre el documento...", key="pdf_input"):
            st.session_state.pdf_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.write(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Analizando con Nomic..."):
                    res = requests.post(f"{API_URL}/ask_pdf/", data={"question": prompt, "style": style})
                    ans = res.json().get("answer", "Error de conexión")
                    st.write(ans)
                    st.session_state.pdf_messages.append({"role": "assistant", "content": ans})
    else:
        st.info("⬆️ Sube un PDF para comenzar a hacer preguntas.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — BIBLIOTECA EMPRESARIAL
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### 📚 Consulta a Biblioteca con Nomic Embed")
    st.info("💡 **Contexto ampliado:** Nomic permite 8192 tokens por consulta. Límite: **100 documentos** por carpeta.")

    folder_ready = health.get('folder_ready', False) if health else False
    folder_info = get_folder_info() if folder_ready else {}

    # ── Banner: biblioteca activa ─────────────────────────────────────────────
    if folder_ready and folder_info:
        limit_note = " ⚠️ (límite de 100 aplicado)" if folder_info.get("limit_applied") else ""
        st.markdown(
            f'<div class="active-doc-banner">'
            f'📚 Biblioteca activa: <strong>{folder_info.get("folder_path", "Carpeta indexada")}</strong> '
            f'— {folder_info.get("processed_files", "?")} documentos · '
            f'{folder_info.get("total_chunks", "?")} segmentos{limit_note}'
            f'</div>',
            unsafe_allow_html=True
        )

    # ── Sección de indexación (colapsable si ya hay biblioteca activa) ────────
    index_label = "🔄 Cambiar biblioteca" if folder_ready else "📁 Indexar carpeta"
    with st.expander(index_label, expanded=not folder_ready):

        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            path_input = st.text_input("📁 Ruta de la carpeta", value=st.session_state.folder_path)
            if path_input != st.session_state.folder_path:
                st.session_state.folder_path = path_input
                st.session_state.doc_count_info = None  # Reset al cambiar ruta

        with col2:
            if st.button("🔍 Explorar", use_container_width=True):
                selected = select_folder()
                if selected:
                    st.session_state.folder_path = selected
                    st.session_state.doc_count_info = None
                    st.rerun()

        with col3:
            if st.button("🗑️ Limpiar índice", use_container_width=True):
                with st.spinner("Eliminando índice Nomic..."):
                    requests.post(f"{API_URL}/clear_index/")
                    st.session_state.indexed = False
                    st.session_state.folder_messages = []
                    st.session_state.indexing_progress = None
                    st.session_state.doc_count_info = None
                    st.success("✅ Índice eliminado")
                    time.sleep(1)
                    st.rerun()

        # ── Verificar conteo de documentos ────────────────────────────────────
        if st.session_state.folder_path and os.path.exists(st.session_state.folder_path):
            if st.session_state.doc_count_info is None:
                with st.spinner("Contando documentos..."):
                    st.session_state.doc_count_info = get_folder_doc_count(st.session_state.folder_path)

            info = st.session_state.doc_count_info
            if info:
                count = info.get("count", 0)
                limit = info.get("limit", 100)
                exceeds = info.get("exceeds_limit", False)

                if exceeds:
                    st.warning(
                        f"⚠️ **La carpeta contiene {count} PDFs**, que supera el límite de {limit}. "
                        f"Solo se procesarán los primeros **{info.get('will_process', limit)}** documentos."
                    )
                elif count == 0:
                    st.error("❌ No se encontraron archivos PDF en esta carpeta.")
                else:
                    st.success(f"✅ Carpeta lista: **{count} PDFs** encontrados (dentro del límite de {limit}).")

        # ── Botones de acción ─────────────────────────────────────────────────
        col1, col2 = st.columns([1, 1])
        with col1:
            can_index = (
                st.session_state.folder_path
                and os.path.exists(st.session_state.folder_path)
                and st.session_state.doc_count_info is not None
                and st.session_state.doc_count_info.get("count", 0) > 0
            )
            if st.button("🚀 Indexar carpeta", type="primary", use_container_width=True, disabled=not can_index):
                with st.spinner("Iniciando indexación con Nomic..."):
                    res = requests.post(f"{API_URL}/index_folder/", data={"folder_path": st.session_state.folder_path})
                    if res.status_code == 200:
                        data = res.json()
                        msg = f"✅ Indexación Nomic iniciada — procesando {data.get('will_process', '?')} documentos"
                        if data.get("limit_applied"):
                            msg += f" (de {data.get('total_found', '?')} encontrados)"
                        st.success(msg)
                        st.session_state.indexing_progress = {"checking": True}
                        st.rerun()
                    else:
                        st.error(f"❌ Error: {res.json().get('error', 'Desconocido')}")

        with col2:
            if st.button("🔄 Verificar estado", use_container_width=True):
                st.session_state.indexing_progress = {"checking": True}
                st.rerun()

    # ── Barra de progreso de indexación ──────────────────────────────────────
    if st.session_state.get('indexing_progress'):
        status = check_indexing_status()
        if status and status.get('in_progress', False):
            progress = status.get('progress_percentage', 0)
            st.progress(progress / 100)
            st.metric("Progreso Nomic", f"{progress:.1f}%")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📄 Archivos", f"{status['processed_files']}/{status['total_files']}")
            with col2:
                st.metric("⏱️ Tiempo", f"{status.get('elapsed_seconds', 0):.0f}s")
            with col3:
                st.metric("📌 Actual", status.get('current_file', '...')[:25])

            time.sleep(2)
            st.rerun()
        elif status and not status.get('in_progress'):
            st.success(f"✅ Indexación Nomic completada — {status['processed_files']} archivos")
            st.session_state.indexed = True
            st.session_state.indexing_progress = None
            st.rerun()

    # ── Chat (visible solo si el backend confirma que el índice existe en disco) ──
    if folder_ready:
        st.divider()

        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("🗑️ Limpiar chat", use_container_width=True, key="clear_folder_chat"):
                st.session_state.folder_messages = []
                st.rerun()

        for msg in st.session_state.folder_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt_folder := st.chat_input("Pregunta sobre la biblioteca... (Nomic contexto 8K)", key="folder_input"):
            st.session_state.folder_messages.append({"role": "user", "content": prompt_folder})
            with st.chat_message("user"):
                st.write(prompt_folder)

            with st.chat_message("assistant"):
                with st.spinner("Buscando con Nomic Embed..."):
                    res = requests.post(f"{API_URL}/ask_folder/", data={"question": prompt_folder})
                    ans = res.json().get("answer", "Error de conexión")
                    st.markdown(ans)
                    st.session_state.folder_messages.append({"role": "assistant", "content": ans})
    else:
        st.info("⬆️ Indexa una carpeta para comenzar a hacer preguntas.")

# ─── Footer ──────────────────────────────────────────────────────────────────
st.divider()
st.caption("🧠 Powered by Nomic Embed v1.5 | 8192 tokens de contexto | Alta precisión semántica")