<?php
// api.php
// Endpoint único para las 3 tablas.
// GET  api.php?tabla=alumnos            -> lista todos los registros
// POST api.php  (form-data: tabla=alumnos, + campos)  -> inserta un registro

header('Content-Type: application/json; charset=utf-8');
require_once 'config.php';

// Lista blanca de tablas permitidas (nombre "amigable" -> nombre real en la BD)
$tablasPermitidas = [
    'alumnos'       => 'Alumnos',
    'colegiaturas'  => 'Colegiaturas',
    'calificaciones'=> 'Calificaciones',
];

$metodo = $_SERVER['REQUEST_METHOD'];
$tablaParam = $_GET['tabla'] ?? $_POST['tabla'] ?? '';

if (!array_key_exists($tablaParam, $tablasPermitidas)) {
    http_response_code(400);
    echo json_encode(['error' => 'Tabla no válida']);
    exit;
}

$tabla = $tablasPermitidas[$tablaParam];

// ---------------------------------------------------------
// GET: devolver todos los registros de la tabla solicitada
// ---------------------------------------------------------
if ($metodo === 'GET') {
    $resultado = $conn->query("SELECT * FROM `$tabla`");

    if (!$resultado) {
        http_response_code(500);
        echo json_encode(['error' => $conn->error]);
        exit;
    }

    $filas = [];
    while ($fila = $resultado->fetch_assoc()) {
        $filas[] = $fila;
    }

    echo json_encode($filas);
    exit;
}

// ---------------------------------------------------------
// POST: insertar un nuevo registro
// ---------------------------------------------------------
if ($metodo === 'POST') {

    switch ($tablaParam) {

        case 'alumnos':
            $stmt = $conn->prepare(
                "INSERT INTO Alumnos (alumno_id, nombre, apellido, fecha_nacimiento, telefono, email)
                 VALUES (?, ?, ?, ?, ?, ?)"
            );
            $stmt->bind_param(
                'isssss',
                $_POST['alumno_id'],
                $_POST['nombre'],
                $_POST['apellido'],
                $_POST['fecha_nacimiento'],
                $_POST['telefono'],
                $_POST['email']
            );
            break;

        case 'colegiaturas':
            $stmt = $conn->prepare(
                "INSERT INTO Colegiaturas (colegiatura_id, alumno_id, monto, mes_pagado, fecha_pago, estado_pago)
                 VALUES (?, ?, ?, ?, ?, ?)"
            );
            $stmt->bind_param(
                'iidsss',
                $_POST['colegiatura_id'],
                $_POST['alumno_id'],
                $_POST['monto'],
                $_POST['mes_pagado'],
                $_POST['fecha_pago'],
                $_POST['estado_pago']
            );
            break;

        case 'calificaciones':
            $stmt = $conn->prepare(
                "INSERT INTO Calificaciones (calificacion_id, alumno_id, materia, nota, periodo)
                 VALUES (?, ?, ?, ?, ?)"
            );
            $stmt->bind_param(
                'iisds',
                $_POST['calificacion_id'],
                $_POST['alumno_id'],
                $_POST['materia'],
                $_POST['nota'],
                $_POST['periodo']
            );
            break;
    }

    if ($stmt->execute()) {
        echo json_encode(['ok' => true, 'mensaje' => 'Registro agregado correctamente']);
    } else {
        http_response_code(500);
        echo json_encode(['error' => $stmt->error]);
    }

    $stmt->close();
    exit;
}

http_response_code(405);
echo json_encode(['error' => 'Método no permitido']);
