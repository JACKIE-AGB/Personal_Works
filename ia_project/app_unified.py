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
</style>
""", unsafe_allow_html=True)

# Estados
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
        return response.status_code == 200
    except:
        return False

st.title("🧠 Asistente Inteligente Empresarial con Nomic Embed")
st.caption("Modelo de embeddings nomic-embed-text-v1.5 | Contexto de 8192 tokens | Alta precisión")

with st.sidebar:
    st.header("📊 Estado del Sistema")
    
    health_status = check_health()
    if health_status:
        st.success("✅ Backend conectado (Nomic Embed)")
    else:
        st.error("❌ Backend desconectado")
    
    try:
        health = requests.get(f"{API_URL}/health").json()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("PDF Listo", "✅" if health['pdf_ready'] else "❌")
        with col2:
            st.metric("Biblioteca", "✅" if health['folder_ready'] else "❌")
        
        if health.get('indexing_in_progress', False):
            st.warning("🔄 Indexación en progreso...")
        
        st.divider()
        st.info(f"**Modelo:** {health.get('embedding_model', 'Nomic v1.5')}")
        st.info(f"**Contexto:** {health.get('chunk_size', 2000)} tokens")
    except:
        pass
    
    st.divider()
    st.caption("💡 **Ventajas Nomic Embed:**\n- 8192 tokens de contexto\n- Calidad superior (+11%)\n- 100+ idiomas\n- Eficiente en CPU")

tab1, tab2 = st.tabs(["📄 Documento Individual", "📚 Biblioteca Empresarial"])

# ============================================
# TAB 1 (sin cambios funcionales)
# ============================================
with tab1:
    st.markdown("### 📄 Análisis de Documento Individual")
    
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
                    st.success(f"✅ {data.get('message')} - {data.get('pages', 0)} páginas, {data.get('chunks', 0)} segmentos")
                else:
                    st.error(f"❌ Error: {res.json().get('error', 'Desconocido')}")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        style = st.selectbox("Estilo de respuesta", ["normal", "amable", "agresivo"],
                            format_func=lambda x: {"normal": "📝 Profesional", "amable": "😊 Amable", "agresivo": "⚡ Directo"}[x])
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

# ============================================
# TAB 2 (sin cambios funcionales)
# ============================================
with tab2:
    st.markdown("### 📚 Consulta a Biblioteca con Nomic Embed")
    st.info("💡 **Contexto ampliado:** Nomic permite 8192 tokens por consulta, capturando más información que antes.")
    
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        path_input = st.text_input("📁 Ruta de la carpeta", value=st.session_state.folder_path)
        if path_input != st.session_state.folder_path:
            st.session_state.folder_path = path_input
    
    with col2:
        if st.button("🔍 Explorar", use_container_width=True):
            selected = select_folder()
            if selected:
                st.session_state.folder_path = selected
                st.rerun()
    
    with col3:
        if st.button("🗑️ Limpiar índice", use_container_width=True):
            with st.spinner("Eliminando índice Nomic..."):
                requests.post(f"{API_URL}/clear_index/")
                st.session_state.indexed = False
                st.session_state.folder_messages = []
                st.session_state.indexing_progress = None
                st.success("✅ Índice eliminado")
                time.sleep(1)
                st.rerun()
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🚀 Indexar carpeta", type="primary", use_container_width=True):
            if st.session_state.folder_path and os.path.exists(st.session_state.folder_path):
                with st.spinner("Iniciando indexación con Nomic..."):
                    res = requests.post(f"{API_URL}/index_folder/", data={"folder_path": st.session_state.folder_path})
                    if res.status_code == 200:
                        st.success("✅ Indexación Nomic iniciada")
                        st.session_state.indexing_progress = {"checking": True}
                        st.rerun()
                    else:
                        st.error(f"❌ Error: {res.json().get('error', 'Desconocido')}")
            else:
                st.warning("⚠️ Selecciona una carpeta válida")
    
    with col2:
        if st.button("🔄 Verificar estado", use_container_width=True):
            st.session_state.indexing_progress = {"checking": True}
            st.rerun()
    
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
            st.success(f"✅ Indexación Nomic completada - {status['processed_files']} archivos")
            st.session_state.indexed = True
            st.session_state.indexing_progress = None
            st.rerun()
    
    if st.session_state.indexed:
        st.divider()
        
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

st.divider()
st.caption("🧠 Powered by Nomic Embed v1.5 | 8192 tokens de contexto | Alta precisión semántica")