// ==========================================================
// app.js - Lógica del frontend. Toda la comunicación con el
// backend se hace por fetch() hacia los endpoints PHP en /api
// ==========================================================

const API_ALUMNOS    = 'api/alumnos.php';
const API_DETALLE     = 'api/alumno_detalle.php';
const API_COLEGIATURAS= 'api/colegiaturas.php';
const API_CALIFICACIONES = 'api/calificaciones.php';

let alumnoSeleccionadoId = null;

document.addEventListener('DOMContentLoaded', () => {
    cargarAlumnos();

    document.getElementById('formAlumno').addEventListener('submit', agregarAlumno);
    document.getElementById('btnBuscarAlumno').addEventListener('click', buscarAlumno);
    document.getElementById('btnLimpiarBuscar').addEventListener('click', () => {
        document.getElementById('inputBuscar').value = '';
        cargarAlumnos();
    });
    document.getElementById('inputBuscar').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); buscarAlumno(); }
    });
    document.getElementById('btnCerrarDetalle').addEventListener('click', cerrarDetalle);
    document.getElementById('formColegiatura').addEventListener('submit', agregarColegiatura);
    document.getElementById('formCalificacion').addEventListener('submit', agregarCalificacion);
});

// ---------- Utilidades de UI ----------

function mostrarAlerta(mensaje, tipo = 'error') {
    const box = document.getElementById('alertBox');
    const div = document.createElement('div');
    div.className = `alert alert-${tipo}`;
    div.textContent = mensaje;
    box.appendChild(div);
    setTimeout(() => div.remove(), 4500);
}

async function llamarApi(url, opciones = {}) {
    let respuesta;
    try {
        respuesta = await fetch(url, opciones);
    } catch (err) {
        // Esto ocurre normalmente si el servidor PHP no está corriendo
        mostrarAlerta('No se pudo conectar con el servidor. ¿Está corriendo "php -S localhost:8000"?', 'error');
        throw err;
    }

    let json;
    try {
        json = await respuesta.json();
    } catch (err) {
        mostrarAlerta('El servidor devolvió una respuesta inválida.', 'error');
        throw err;
    }

    if (!respuesta.ok || !json.success) {
        mostrarAlerta(json.error || 'Ocurrió un error inesperado.', 'error');
        throw new Error(json.error || 'Error desconocido');
    }

    return json.data;
}

// ---------- Alumnos ----------

async function cargarAlumnos() {
    const tbody = document.getElementById('tbodyAlumnos');
    tbody.innerHTML = '<tr><td colspan="7" class="loading-row">Cargando alumnos...</td></tr>';
    try {
        const alumnos = await llamarApi(API_ALUMNOS);
        renderAlumnos(alumnos);
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No se pudieron cargar los alumnos.</td></tr>';
    }
}

function renderAlumnos(alumnos) {
    const tbody = document.getElementById('tbodyAlumnos');
    tbody.innerHTML = '';

    if (!alumnos || alumnos.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No se encontraron alumnos.</td></tr>';
        return;
    }

    alumnos.forEach(a => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${a.Alumno_id}</td>
            <td>${escapeHtml(a.nombre)}</td>
            <td>${escapeHtml(a.apellido)}</td>
            <td>${a.fecha_nacimiento || '-'}</td>
            <td>${a.telefono || '-'}</td>
            <td>${a.email || '-'}</td>
            <td><button class="link-btn" data-id="${a.Alumno_id}">Ver detalle</button></td>
        `;
        tr.querySelector('.link-btn').addEventListener('click', () => verDetalle(a.Alumno_id));
        tbody.appendChild(tr);
    });
}

async function agregarAlumno(e) {
    e.preventDefault();
    const form = e.target;
    const boton = document.getElementById('btnAgregarAlumno');

    const datos = {
        nombre: form.nombre.value.trim(),
        apellido: form.apellido.value.trim(),
        fecha_nacimiento: form.fecha_nacimiento.value,
        telefono: form.telefono.value.trim(),
        email: form.email.value.trim(),
    };

    // Validaciones en el front (además de las del back)
    if (!datos.nombre || !datos.apellido) {
        mostrarAlerta('Nombre y apellido son obligatorios.', 'warning');
        return;
    }
    if (datos.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(datos.email)) {
        mostrarAlerta('El email no tiene un formato válido.', 'warning');
        return;
    }

    boton.disabled = true;
    try {
        await llamarApi(API_ALUMNOS, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(datos),
        });
        mostrarAlerta('Alumno agregado correctamente.', 'success');
        form.reset();
        cargarAlumnos();
    } catch (e) {
        // el error ya se mostró en llamarApi
    } finally {
        boton.disabled = false;
    }
}

async function buscarAlumno() {
    const q = document.getElementById('inputBuscar').value.trim();
    if (!q) {
        mostrarAlerta('Escribe algo para buscar (nombre, apellido, email o id).', 'warning');
        cargarAlumnos();
        return;
    }
    try {
        const alumnos = await llamarApi(`${API_ALUMNOS}?q=${encodeURIComponent(q)}`);
        renderAlumnos(alumnos);
        if (alumnos.length === 0) {
            mostrarAlerta('No se encontraron alumnos con ese criterio.', 'warning');
        }
    } catch (e) { /* ya mostrado */ }
}

// ---------- Detalle: colegiaturas + calificaciones ----------

async function verDetalle(id) {
    try {
        const detalle = await llamarApi(`${API_DETALLE}?id=${id}`);
        alumnoSeleccionadoId = id;

        document.getElementById('detalleNombre').textContent =
            `${detalle.alumno.nombre} ${detalle.alumno.apellido} (ID ${detalle.alumno.Alumno_id})`;

        renderColegiaturas(detalle.colegiaturas);
        renderCalificaciones(detalle.calificaciones);

        const seccion = document.getElementById('detalleSection');
        seccion.hidden = false;
        seccion.scrollIntoView({ behavior: 'smooth' });
    } catch (e) { /* ya mostrado */ }
}

function cerrarDetalle() {
    document.getElementById('detalleSection').hidden = true;
    alumnoSeleccionadoId = null;
}

function renderColegiaturas(lista) {
    const tbody = document.getElementById('tbodyColegiaturas');
    tbody.innerHTML = '';
    if (!lista || lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty-row">Sin registros.</td></tr>';
        return;
    }
    lista.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(c.mes_pago)}</td>
            <td>$${Number(c.monto).toFixed(2)}</td>
            <td>${c.fecha_pago || '-'}</td>
            <td>${escapeHtml(c.estado_pago)}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderCalificaciones(lista) {
    const tbody = document.getElementById('tbodyCalificaciones');
    tbody.innerHTML = '';
    if (!lista || lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" class="empty-row">Sin registros.</td></tr>';
        return;
    }
    lista.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(c.materia)}</td>
            <td>${c.nota}</td>
            <td>${escapeHtml(c.periodo)}</td>
        `;
        tbody.appendChild(tr);
    });
}

async function agregarColegiatura(e) {
    e.preventDefault();
    if (!alumnoSeleccionadoId) {
        mostrarAlerta('Selecciona un alumno primero.', 'warning');
        return;
    }
    const form = e.target;
    const datos = {
        alumno_id: alumnoSeleccionadoId,
        mes_pago: form.mes_pago.value.trim(),
        monto: form.monto.value,
        fecha_pago: form.fecha_pago.value,
        estado_pago: form.estado_pago.value,
    };

    if (!datos.mes_pago || datos.monto === '' || Number(datos.monto) < 0) {
        mostrarAlerta('Revisa el mes y el monto de la colegiatura.', 'warning');
        return;
    }

    try {
        await llamarApi(API_COLEGIATURAS, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(datos),
        });
        mostrarAlerta('Colegiatura agregada correctamente.', 'success');
        form.reset();
        verDetalle(alumnoSeleccionadoId);
    } catch (e) { /* ya mostrado */ }
}

async function agregarCalificacion(e) {
    e.preventDefault();
    if (!alumnoSeleccionadoId) {
        mostrarAlerta('Selecciona un alumno primero.', 'warning');
        return;
    }
    const form = e.target;
    const datos = {
        alumno_id: alumnoSeleccionadoId,
        materia: form.materia.value.trim(),
        nota: form.nota.value,
        periodo: form.periodo.value.trim(),
    };

    if (!datos.materia || datos.nota === '' || Number(datos.nota) < 0 || Number(datos.nota) > 10 || !datos.periodo) {
        mostrarAlerta('Revisa materia, nota (0-10) y periodo.', 'warning');
        return;
    }

    try {
        await llamarApi(API_CALIFICACIONES, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(datos),
        });
        mostrarAlerta('Calificación agregada correctamente.', 'success');
        form.reset();
        verDetalle(alumnoSeleccionadoId);
    } catch (e) { /* ya mostrado */ }
}

// ---------- Helpers ----------

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
