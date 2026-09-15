<?php
header("Content-Type: application/json; charset=UTF-8");
require_once "database.php";

$method = $_SERVER['REQUEST_METHOD'];
$action = $_GET['action'] ?? '';

// --- OBTENER REGISTROS (GET) ---
if ($method === 'GET') {
    if ($action === 'obtener_alumnos') {
        $stmt = $pdo->query("SELECT * FROM alumnos");
        echo json_encode($stmt->fetchAll());
        exit;
    }

    if ($action === 'obtener_colegiaturas') {
        $stmt = $pdo->query("SELECT * FROM colegiaturas");
        echo json_encode($stmt->fetchAll());
        exit;
    }

    if ($action === 'obtener_calificaciones') {
        $stmt = $pdo->query("SELECT * FROM calificaciones");
        echo json_encode($stmt->fetchAll());
        exit;
    }
}

// --- AGREGAR REGISTROS (POST) ---
if ($method === 'POST') {
    $data = json_decode(file_get_contents("php://input"), true);

    if ($action === 'agregar_alumno') {
        $sql = "INSERT INTO alumnos (alumno_id, nombre, apellido, fecha_nacimiento, telefono, email) 
                VALUES (:alumno_id, :nombre, :apellido, :fecha_nacimiento, :telefono, :email)";
        $stmt = $pdo->prepare($sql);
        $result = $stmt->execute([
            ':alumno_id'        => $data['alumno_id'],
            ':nombre'           => $data['nombre'],
            ':apellido'         => $data['apellido'],
            ':fecha_nacimiento' => $data['fecha_nacimiento'] ?: null,
            ':telefono'         => $data['telefono'] ?: null,
            ':email'            => $data['email'] ?: null
        ]);
        echo json_encode(["status" => $result ? "ok" : "error"]);
        exit;
    }

    if ($action === 'agregar_colegiatura') {
        $sql = "INSERT INTO colegiaturas (colegiatura_id, alumno_id, monto, mes_pagado, fecha_pago, estado_pago) 
                VALUES (:colegiatura_id, :alumno_id, :monto, :mes_pagado, :fecha_pago, :estado_pago)";
        $stmt = $pdo->prepare($sql);
        $result = $stmt->execute([
            ':colegiatura_id' => $data['colegiatura_id'],
            ':alumno_id'      => $data['alumno_id'],
            ':monto'          => $data['monto'],
            ':mes_pagado'     => $data['mes_pagado'] ?: null,
            ':fecha_pago'     => $data['fecha_pago'] ?: null,
            ':estado_pago'    => $data['estado_pago']
        ]);
        echo json_encode(["status" => $result ? "ok" : "error"]);
        exit;
    }

    if ($action === 'agregar_calificacion') {
        $sql = "INSERT INTO calificaciones (calificacion_id, alumno_id, materia, nota, periodo) 
                VALUES (:calificacion_id, :alumno_id, :materia, :nota, :periodo)";
        $stmt = $pdo->prepare($sql);
        $result = $stmt->execute([
            ':calificacion_id' => $data['calificacion_id'],
            ':alumno_id'       => $data['alumno_id'],
            ':materia'         => $data['materia'],
            ':nota'            => $data['nota'] ?: null,
            ':periodo'         => $data['periodo'] ?: null
        ]);
        echo json_encode(["status" => $result ? "ok" : "error"]);
        exit;
    }
}
?>