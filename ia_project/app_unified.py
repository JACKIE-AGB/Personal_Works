import streamlit as st
import requests
import os

# Dirección del backend unificado
API_URL = "http://127.0.0.1:8001"

st.set_page_config(page_title="Chatbot Inteligente", layout="centered", page_icon="🤖")

st.title("🤖 Asistente Inteligente de Documentos")

# Inicializar session_state para ambos modos
if "pdf_messages" not in st.session_state:
    st.session_state.pdf_messages = []
if "folder_messages" not in st.session_state:
    st.session_state.folder_messages = []
if "folder_path" not in st.session_state:
    st.session_state.folder_path = ""
if "pdf_ready" not in st.session_state:
    st.session_state.pdf_ready = False
if "folder_ready" not in st.session_state:
    st.session_state.folder_ready = False

# Crear pestañas
tab1, tab2 = st.tabs(["📄 Chat con PDF Individual", "📂 Chat con Carpeta de PDFs"])

# ============================================
# TAB 1: PDF INDIVIDUAL
# ============================================
with tab1:
    st.markdown("### 📄 Sube un PDF y haz preguntas")
    
    # Subir PDF
    uploaded_file = st.file_uploader("Selecciona un archivo PDF", type="pdf", key="pdf_uploader")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if uploaded_file and st.button("📤 Procesar PDF", key="process_pdf"):
            with st.spinner("Procesando PDF..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                response = requests.post(f"{API_URL}/upload_pdf/", files=files)
                
                if response.status_code == 200:
                    st.session_state.pdf_ready = True
                    st.success("✅ PDF listo para preguntas")
                else:
                    st.session_state.pdf_ready = False
                    st.error(f"❌ Error: {response.text}")
    
    with col2:
        if st.button("🗑️ Limpiar chat", key="clear_pdf_chat"):
            st.session_state.pdf_messages = []
            st.rerun()
    
    # Selector de estilo
    style_pdf = st.selectbox(
        "🎨 Estilo de respuesta",
        ["normal", "amable", "agresivo"],
        key="pdf_style"
    )
    
    # Mostrar estado del índice
    if st.session_state.pdf_ready:
        st.info("📌 PDF cargado y listo para consultas")
    else:
        st.warning("⚠️ Sube un PDF para comenzar")
    
    st.divider()
    
    # Mostrar historial del chat PDF
    for msg in st.session_state.pdf_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    # Input del chat PDF
    if prompt := st.chat_input("Escribe tu pregunta sobre el PDF...", key="pdf_input"):
        if not st.session_state.pdf_ready:
            st.error("❌ Primero sube y procesa un PDF")
        else:
            st.session_state.pdf_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            with st.chat_message("assistant"):
                with st.spinner("Pensando..."):
                    try:
                        response = requests.post(
                            f"{API_URL}/ask_pdf/",
                            data={"question": prompt, "style": style_pdf}
                        )
                        
                        if response.status_code == 200:
                            answer = response.json().get("answer", "No se recibió respuesta")
                        else:
                            answer = f"❌ Error: {response.text}"
                    except Exception as e:
                        answer = f"❌ Error de conexión: {str(e)}"
                
                st.markdown(answer)
                st.session_state.pdf_messages.append({"role": "assistant", "content": answer})

# ============================================
# TAB 2: CARPETA DE PDFs
# ============================================
with tab2:
    st.markdown("### 📂 Indexa una carpeta con PDFs y haz preguntas")
    
    # Entrada de ruta de carpeta
    folder_path_input = st.text_input(
        "📁 Ruta de la carpeta",
        value=st.session_state.folder_path,
        placeholder="Ejemplo: C:/Users/tus/documentos",
        key="folder_path_input"
    )
    
    col_idx, col_clr = st.columns(2)
    
    with col_idx:
        if st.button("🚀 Indexar carpeta", key="index_folder", use_container_width=True):
            folder_to_index = folder_path_input if folder_path_input else st.session_state.folder_path
            
            if not folder_to_index:
                st.error("❌ Ingresa una ruta válida")
            elif not os.path.exists(folder_to_index):
                st.error(f"❌ La ruta no existe: {folder_to_index}")
            else:
                with st.spinner("Indexando PDFs..."):
                    try:
                        response = requests.post(
                            f"{API_URL}/index_folder/",
                            data={"folder_path": folder_to_index}
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            st.session_state.folder_ready = True
                            st.session_state.folder_path = folder_to_index
                            st.success(f"✅ {data['message']}")
                            
                            with st.expander("📄 Archivos procesados"):
                                for f in data.get("files", []):
                                    st.write(f"• {f}")
                        else:
                            st.error(f"❌ Error: {response.text}")
                    except Exception as e:
                        st.error(f"❌ No se pudo conectar: {str(e)}")
    
    with col_clr:
        if st.button("🗑️ Eliminar índice", key="clear_index", use_container_width=True):
            try:
                response = requests.post(f"{API_URL}/clear_index/")
                if response.status_code == 200:
                    st.session_state.folder_ready = False
                    st.session_state.folder_path = ""
                    st.session_state.folder_messages = []
                    st.success("✅ Índice eliminado correctamente")
                    st.rerun()
                else:
                    st.error("❌ Error al eliminar índice")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    # Mostrar estado del índice de carpetas
    if st.session_state.folder_ready:
        st.info(f"📌 Carpeta activa: `{st.session_state.folder_path}`")
    else:
        st.warning("⚠️ No hay ningún índice activo. Indexa una carpeta para comenzar")
    
    st.divider()
    
    # Mostrar historial del chat carpeta
    for msg in st.session_state.folder_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    # Input del chat carpeta
    if prompt := st.chat_input("Escribe tu pregunta sobre los documentos...", key="folder_input"):
        if not st.session_state.folder_ready:
            st.error("❌ Primero indexa una carpeta")
        else:
            st.session_state.folder_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            with st.chat_message("assistant"):
                with st.spinner("Consultando documentos..."):
                    try:
                        response = requests.post(
                            f"{API_URL}/ask_folder/",
                            data={"question": prompt}
                        )
                        
                        if response.status_code == 200:
                            answer = response.json().get("answer", "No se recibió respuesta")
                        else:
                            answer = f"❌ Error: {response.text}"
                    except Exception as e:
                        answer = f"❌ Error de conexión: {str(e)}"
                
                st.markdown(answer)
                st.session_state.folder_messages.append({"role": "assistant", "content": answer})