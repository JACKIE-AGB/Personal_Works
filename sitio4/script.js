// script.js
// Conecta el front-end con api.php (que a su vez habla con MySQL)

const API_URL = 'api.php'; // como todo corre en localhost:8000, la ruta es relativa

// Configuración de cada tabla: en qué <tbody> pintar, y qué columnas mostrar (en orden)
const TABLAS = {
    alumnos: {
        tbodyId: 'tbody-alumnos',
        columnas: ['alumno_id', 'nombre', 'apellido', 'fecha_nacimiento', 'telefono', 'email']
    },
    colegiaturas: {
        tbodyId: 'tbody-colegiaturas',
        columnas: ['colegiatura_id', 'alumno_id', 'monto', 'mes_pagado', 'fecha_pago', 'estado_pago']
    },
    calificaciones: {
        tbodyId: 'tbody-calificaciones',
        columnas: ['calificacion_id', 'alumno_id', 'materia', 'nota', 'periodo']
    }
};

// Al cargar la página, pedir los datos de las 3 tablas
document.addEventListener('DOMContentLoaded', () => {
    Object.keys(TABLAS).forEach(cargarTabla);
});

// Pide los registros de una tabla a la API y los pinta en su <tbody>
async function cargarTabla(nombreTabla) {
    const config = TABLAS[nombreTabla];
    const tbody = document.getElementById(config.tbodyId);

    try {
        const respuesta = await fetch(`${API_URL}?tabla=${nombreTabla}`);
        const datos = await respuesta.json();

        if (datos.error) {
            console.error(datos.error);
            return;
        }

        tbody.innerHTML = ''; // limpiar antes de repintar

        datos.forEach(registro => {
            const fila = document.createElement('tr');
            fila.innerHTML = config.columnas
                .map(col => `<td>${registro[col] ?? ''}</td>`)
                .join('');
            tbody.appendChild(fila);
        });

    } catch (error) {
        console.error('Error cargando', nombreTabla, error);
    }
}

// Lee los inputs del formulario de una tabla y los envía a la API por POST
async function agregarRegistro(nombreTabla) {
    const filaFormulario = document.getElementById(`form-${nombreTabla}`);
    const inputs = filaFormulario.querySelectorAll('input, select');

    const datosForm = new FormData();
    datosForm.append('tabla', nombreTabla);

    let vacioObligatorio = false;
    inputs.forEach(input => {
        if (input.required && !input.value) vacioObligatorio = true;
        datosForm.append(input.name, input.value);
    });

    if (vacioObligatorio) {
        alert('Por favor llena los campos obligatorios.');
        return;
    }

    try {
        const respuesta = await fetch(API_URL, {
            method: 'POST',
            body: datosForm
        });
        const resultado = await respuesta.json();

        if (resultado.error) {
            alert('Error: ' + resultado.error);
            return;
        }

        // Limpiar el formulario y recargar la tabla para ver el nuevo registro
        inputs.forEach(input => { if (input.tagName === 'INPUT') input.value = ''; });
        cargarTabla(nombreTabla);

    } catch (error) {
        console.error('Error agregando registro:', error);
        alert('No se pudo agregar el registro.');
    }
}
