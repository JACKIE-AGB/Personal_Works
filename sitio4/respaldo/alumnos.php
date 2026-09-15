<?php
require_once __DIR__ . '/../db.php';

$metodo = $_SERVER['REQUEST_METHOD'];

if ($metodo === 'GET') {
    try {
        $stmt = $pdo->query(
            'SELECT alumno_id, nombre, apellido, fecha_nacimiento, telefono, email
             FROM alumnos
             ORDER BY alumno_id'
        );
        echo json_encode(['success' => true, 'data' => $stmt->fetchAll()]);
    } catch (PDOException $e) {
        http_response_code(500);
        echo json_encode(['success' => false, 'error' => $e->getMessage()]);
    }
    exit;
}

if ($metodo === 'POST') {
    $input = json_decode(file_get_contents('php://input'), true);

    if (!$input || empty($input['alumno_id']) || empty($input['nombre']) || empty($input['apellido'])) {
        http_response_code(400);
        echo json_encode([
            'success' => false,
            'error'   => 'Faltan campos requeridos: alumno_id, nombre y apellido.',
        ]);
        exit;
    }

    try {
        $stmt = $pdo->prepare(
            'INSERT INTO alumnos (alumno_id, nombre, apellido, fecha_nacimiento, telefono, email)
             VALUES (:alumno_id, :nombre, :apellido, :fecha_nacimiento, :telefono, :email)'
        );
        $stmt->execute([
            ':alumno_id'         => $input['alumno_id'],
            ':nombre'            => $input['nombre'],
            ':apellido'          => $input['apellido'],
            ':fecha_nacimiento'  => $input['fecha_nacimiento'] !== '' ? $input['fecha_nacimiento'] : null,
            ':telefono'          => $input['telefono'] !== '' ? $input['telefono'] : null,
            ':email'             => $input['email'] !== '' ? $input['email'] : null,
        ]);
        echo json_encode(['success' => true]);
    } catch (PDOException $e) {
        http_response_code(500);
        // Código 23000 = violación de restricción (ej. ID duplicado)
        $mensaje = $e->getCode() === '23000'
            ? 'Ya existe un alumno con ese ID.'
            : $e->getMessage();
        echo json_encode(['success' => false, 'error' => $mensaje]);
    }
    exit;
}

http_response_code(405);
echo json_encode(['success' => false, 'error' => 'Método no permitido.']);