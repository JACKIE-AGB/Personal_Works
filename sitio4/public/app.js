// app.js
// Toda la comunicación con la base de datos pasa por la API del backend (server.js)
// usando fetch(). No hay datos "quemados" en el HTML: todo viene de /api/...

const API = "/api";

// ---------- Referencias al DOM ----------
const form = document.getElementById("form-alumno");
const alumnoIdInput = document.getElementById("alumno_id");
const nombreInput = document.getElementById("nombre");
const apellidoInput = document.getElementById("apellido");
const fechaNacInput = document.getElementById("fecha_nacimiento");
const telefonoInput = document.getElementById("telefono");
const emailInput = document.getElementById("email");
const formTitle = document.getElementById("form-title");
const btnGuardar = document.getElementById("btn-guardar");
const btnCancelar = document.getElementById("btn-cancelar");

const buscarInput = document.getElementById("buscar");
const btnBuscar = document.getElementById("btn-buscar");
const btnLimpiar = document.getElementById("btn-limpiar");

const tbody = document.getElementById("alumnos-tbody");
const contador = document.getElementById("contador");
const sinResultados = document.getElementById("sin-resultados");

const panelDetalle = document.getElementById("panel-detalle");
const detalleTitulo = document.getElementById("detalle-titulo");
const btnCerrarDetalle = document.getElementById("btn-cerrar-detalle");

const formColegiatura = document.getElementById("form-colegiatura");
const listaColegiaturas = document.getElementById("lista-colegiaturas");

const formCalificacion = document.getElementById("form-calificacion");
const listaCalificaciones = document.getElementById("lista-calificaciones");

const toast = document.getElementById("toast");

let alumnoSeleccionadoId = null;

// ---------- Utilidades ----------
function mostrarToast(mensaje, esError = false) {
  toast.textContent = mensaje;
  toast.classList.toggle("error", esError);
  toast.hidden = false;
  clearTimeout(mostrarToast._t);
  mostrarToast._t = setTimeout(() => (toast.hidden = true), 2500);
}

async function apiFetch(url, options) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Error en la solicitud");
  return data;
}

function limpiarFormAlumno() {
  form.reset();
  alumnoIdInput.value = "";
  formTitle.textContent = "Agregar alumno";
  btnGuardar.textContent = "➕ Agregar alumno";
  btnCancelar.hidden = true;
}

// ---------- ALUMNOS: cargar y renderizar ----------
async function cargarAlumnos(query = "") {
  try {
    const url = query
      ? `${API}/alumnos?q=${encodeURIComponent(query)}`
      : `${API}/alumnos`;
    const alumnos = await apiFetch(url);
    renderAlumnos(alumnos);
  } catch (err) {
    mostrarToast("No se pudieron cargar los alumnos: " + err.message, true);
  }
}

function renderAlumnos(alumnos) {
  tbody.innerHTML = "";
  contador.textContent = alumnos.length;
  sinResultados.hidden = alumnos.length !== 0;

  for (const a of alumnos) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${a.alumno_id}</td>
      <td>${escapeHtml(a.nombre)}</td>
      <td>${escapeHtml(a.apellido)}</td>
      <td>${a.fecha_nacimiento || "—"}</td>
      <td>${a.telefono || "—"}</td>
      <td>${a.email || "—"}</td>
      <td class="row-actions">
        <button class="btn btn-secondary btn-sm" data-action="ver" data-id="${a.alumno_id}">Ver</button>
        <button class="btn btn-secondary btn-sm" data-action="editar" data-id="${a.alumno_id}">Editar</button>
        <button class="btn btn-danger btn-sm" data-action="eliminar" data-id="${a.alumno_id}">Eliminar</button>
      </td>
    `;
    tbody.appendChild(tr);
  }
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// ---------- ALUMNOS: agregar / editar ----------
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    nombre: nombreInput.value.trim(),
    apellido: apellidoInput.value.trim(),
    fecha_nacimiento: fechaNacInput.value || null,
    telefono: telefonoInput.value.trim() || null,
    email: emailInput.value.trim() || null,
  };

  try {
    if (alumnoIdInput.value) {
      // Editar
      await apiFetch(`${API}/alumnos/${alumnoIdInput.value}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      mostrarToast("Alumno actualizado ✅");
    } else {
      // Crear
      await apiFetch(`${API}/alumnos`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      mostrarToast("Alumno agregado ✅");
    }
    limpiarFormAlumno();
    cargarAlumnos(buscarInput.value.trim());
  } catch (err) {
    mostrarToast("Error: " + err.message, true);
  }
});

btnCancelar.addEventListener("click", limpiarFormAlumno);

// ---------- ALUMNOS: acciones de la tabla (ver / editar / eliminar) ----------
tbody.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const id = btn.dataset.id;
  const accion = btn.dataset.action;

  if (accion === "eliminar") {
    if (!confirm("¿Eliminar este alumno y todos sus registros?")) return;
    try {
      await apiFetch(`${API}/alumnos/${id}`, { method: "DELETE" });
      mostrarToast("Alumno eliminado 🗑️");
      if (alumnoSeleccionadoId == id) panelDetalle.hidden = true;
      cargarAlumnos(buscarInput.value.trim());
    } catch (err) {
      mostrarToast("Error: " + err.message, true);
    }
  }

  if (accion === "editar") {
    try {
      const a = await apiFetch(`${API}/alumnos/${id}`);
      alumnoIdInput.value = a.alumno_id;
      nombreInput.value = a.nombre;
      apellidoInput.value = a.apellido;
      fechaNacInput.value = a.fecha_nacimiento || "";
      telefonoInput.value = a.telefono || "";
      emailInput.value = a.email || "";
      formTitle.textContent = `Editando a ${a.nombre} ${a.apellido}`;
      btnGuardar.textContent = "💾 Guardar cambios";
      btnCancelar.hidden = false;
      form.scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      mostrarToast("Error: " + err.message, true);
    }
  }

  if (accion === "ver") {
    abrirDetalle(id);
  }
});

// ---------- BÚSQUEDA ----------
btnBuscar.addEventListener("click", () => cargarAlumnos(buscarInput.value.trim()));
buscarInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") cargarAlumnos(buscarInput.value.trim());
});
btnLimpiar.addEventListener("click", () => {
  buscarInput.value = "";
  cargarAlumnos();
});

// ---------- DETALLE: colegiaturas y calificaciones ----------
async function abrirDetalle(alumnoId) {
  try {
    const alumno = await apiFetch(`${API}/alumnos/${alumnoId}`);
    alumnoSeleccionadoId = alumnoId;
    detalleTitulo.textContent = `Detalle de ${alumno.nombre} ${alumno.apellido}`;
    panelDetalle.hidden = false;
    panelDetalle.scrollIntoView({ behavior: "smooth" });
    await Promise.all([cargarColegiaturas(alumnoId), cargarCalificaciones(alumnoId)]);
  } catch (err) {
    mostrarToast("Error: " + err.message, true);
  }
}

btnCerrarDetalle.addEventListener("click", () => {
  panelDetalle.hidden = true;
  alumnoSeleccionadoId = null;
});

async function cargarColegiaturas(alumnoId) {
  const items = await apiFetch(`${API}/alumnos/${alumnoId}/colegiaturas`);
  listaColegiaturas.innerHTML = "";
  if (items.length === 0) {
    listaColegiaturas.innerHTML = `<li>Sin registros de colegiatura.</li>`;
    return;
  }
  for (const c of items) {
    const li = document.createElement("li");
    li.innerHTML = `
      <span>$${Number(c.monto).toFixed(2)} — ${c.fecha_pago || "sin fecha"}
        <span class="estado-${c.estado_pago}">(${c.estado_pago})</span>
      </span>
      <button class="btn btn-danger btn-sm" data-id="${c.colegiatura_id}">✖</button>
    `;
    li.querySelector("button").addEventListener("click", async () => {
      await apiFetch(`${API}/colegiaturas/${c.colegiatura_id}`, { method: "DELETE" });
      cargarColegiaturas(alumnoId);
    });
    listaColegiaturas.appendChild(li);
  }
}

async function cargarCalificaciones(alumnoId) {
  const items = await apiFetch(`${API}/alumnos/${alumnoId}/calificaciones`);
  listaCalificaciones.innerHTML = "";
  if (items.length === 0) {
    listaCalificaciones.innerHTML = `<li>Sin calificaciones registradas.</li>`;
    return;
  }
  for (const c of items) {
    const li = document.createElement("li");
    li.innerHTML = `
      <span>${escapeHtml(c.materia)} — <strong>${c.nota}</strong> ${c.periodo ? `(${escapeHtml(c.periodo)})` : ""}</span>
      <button class="btn btn-danger btn-sm" data-id="${c.calificacion_id}">✖</button>
    `;
    li.querySelector("button").addEventListener("click", async () => {
      await apiFetch(`${API}/calificaciones/${c.calificacion_id}`, { method: "DELETE" });
      cargarCalificaciones(alumnoId);
    });
    listaCalificaciones.appendChild(li);
  }
}

formColegiatura.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!alumnoSeleccionadoId) return;
  try {
    await apiFetch(`${API}/alumnos/${alumnoSeleccionadoId}/colegiaturas`, {
      method: "POST",
      body: JSON.stringify({
        monto: document.getElementById("col-monto").value,
        fecha_pago: document.getElementById("col-fecha").value || null,
        estado_pago: document.getElementById("col-estado").value,
      }),
    });
    formColegiatura.reset();
    cargarColegiaturas(alumnoSeleccionadoId);
    mostrarToast("Colegiatura registrada ✅");
  } catch (err) {
    mostrarToast("Error: " + err.message, true);
  }
});

formCalificacion.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!alumnoSeleccionadoId) return;
  try {
    await apiFetch(`${API}/alumnos/${alumnoSeleccionadoId}/calificaciones`, {
      method: "POST",
      body: JSON.stringify({
        materia: document.getElementById("cal-materia").value.trim(),
        nota: document.getElementById("cal-nota").value,
        periodo: document.getElementById("cal-periodo").value.trim() || null,
      }),
    });
    formCalificacion.reset();
    cargarCalificaciones(alumnoSeleccionadoId);
    mostrarToast("Calificación registrada ✅");
  } catch (err) {
    mostrarToast("Error: " + err.message, true);
  }
});

// ---------- Inicio ----------
cargarAlumnos();
