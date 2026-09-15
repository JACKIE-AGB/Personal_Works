document.addEventListener('DOMContentLoaded', () => {
    // Al cargar la página se muestran los registros por default
    cargarTodo();
});

function cargarTodo() {
    cargarTabla('alumnos', 'obtener_alumnos', renderAlumnos);
    cargarTabla('colegiaturas', 'obtener_colegiaturas', renderColegiaturas);
    cargarTabla('calificaciones', 'obtener_calificaciones', renderCalificaciones);
}

function cargarTabla(tipo, accion, callbackRender) {
    fetch(`api.php?action=${accion}`)
        .then(response => response.json())
        .then(data => {
            const tbody = document.getElementById(`tbody-${tipo}`);
            tbody.innerHTML = '';
            data.forEach(item => {
                tbody.innerHTML += callbackRender(item);
            });
        })
        .catch(error => console.error('Error al obtener datos:', error));
}

// Generadores de HTML para las filas
function renderAlumnos(item) {
    return `
        <tr>
            <td>${item.alumno_id}</td>
            <td>${item.nombre}</td>
            <td>${item.apellido}</td>
            <td>${item.fecha_nacimiento || ''}</td>
            <td>${item.telefono || ''}</td>
            <td>${item.email || ''}</td>
        </tr>
    `;
}

function renderColegiaturas(item) {
    const badgeClass = item.estado_pago === 'Pagado' ? 'badge-pagado' : '';
    return `
        <tr>
            <td>${item.colegiatura_id}</td>
            <td>${item.alumno_id}</td>
            <td>$${parseFloat(item.monto).toFixed(2)}</td>
            <td>${item.mes_pagado || ''}</td>
            <td>${item.fecha_pago || ''}</td>
            <td><span class="${badgeClass}">${item.estado_pago}</span></td>
        </tr>
    `;
}

function renderCalificaciones(item) {
    return `
        <tr>
            <td>${item.calificacion_id}</td>
            <td>${item.alumno_id}</td>
            <td>${item.materia}</td>
            <td>${item.nota !== null ? item.nota : ''}</td>
            <td>${item.periodo || ''}</td>
        </tr>
    `;
}

// Función ejecutada por los botones "Agregar..."
function agregarRegistro(tipo) {
    const contenedor = document.getElementById(`form-${tipo}`);
    const inputs = contenedor.querySelectorAll('input, select');
    const payload = {};

    let formularioValido = true;

    inputs.forEach(input => {
        if (input.hasAttribute('required') && !input.value.trim()) {
            formularioValido = false;
        }
        payload[input.name] = input.value;
    });

    if (!formularioValido) {
        alert('Por favor llena los campos requeridos (*).');
        return;
    }

    let accion = '';
    if (tipo === 'alumnos') accion = 'agregar_alumno';
    if (tipo === 'colegiaturas') accion = 'agregar_colegiatura';
    if (tipo === 'calificaciones') accion = 'agregar_calificacion';

    fetch(`api.php?action=${accion}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(res => {
        if (res.status === 'ok') {
            // Limpiar inputs del formulario
            inputs.forEach(i => {
                if (i.tagName === 'SELECT') {
                    i.selectedIndex = 0;
                } else {
                    i.value = '';
                }
            });

            // Recargar únicamente la tabla modificada
            if (tipo === 'alumnos') cargarTabla('alumnos', 'obtener_alumnos', renderAlumnos);
            if (tipo === 'colegiaturas') cargarTabla('colegiaturas', 'obtener_colegiaturas', renderColegiaturas);
            if (tipo === 'calificaciones') cargarTabla('calificaciones', 'obtener_calificaciones', renderCalificaciones);
        } else {
            alert('Ocurrió un error al guardar el registro en la BD.');
        }
    })
    .catch(err => console.error('Error:', err));
}