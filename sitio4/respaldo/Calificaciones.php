<?php
require_once __DIR__ . '/../db.php';

$metodo = $_SERVER['REQUEST_METHOD'];

if ($metodo === 'GET') {
    try {
        $stmt = $pdo->query(
            'SELECT calificacion_id, alumno_id, materia, nota, periodo
             FROM calificaciones
             ORDER BY calificacion_id'
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

    if (!$input || empty($input['calificacion_id']) || empty($input['alumno_id']) || empty($input['materia'])) {
        http_response_code(400);
        echo json_encode([
            'success' => false,
            'error'   => 'Faltan campos requeridos: calificacion_id, alumno_id y materia.',
        ]);
        exit;
    }

    try {
        $stmt = $pdo->prepare(
            'INSERT INTO calificaciones (calificacion_id, alumno_id, materia, nota, periodo)
             VALUES (:calificacion_id, :alumno_id, :materia, :nota, :periodo)'
        );
        $stmt->execute([
            ':calificacion_id' => $input['calificacion_id'],
            ':alumno_id'       => $input['alumno_id'],
            ':materia'         => $input['materia'],
            ':nota'            => $input['nota'] !== '' ? $input['nota'] : null,
            ':periodo'         => $input['periodo'] !== '' ? $input['periodo'] : null,
        ]);
        echo json_encode(['success' => true]);
    } catch (PDOException $e) {
        http_response_code(500);
        if ($e->getCode() === '23000') {
            $mensaje = 'ID duplicado o el alumno_id no existe en la tabla alumnos.';
        } else {
            $mensaje = $e->getMessage();
        }
        echo json_encode(['success' => false, 'error' => $mensaje]);
    }
    exit;
}

http_response_code(405);
echo json_encode(['success' => false, 'error' => 'Método no permitido.']);