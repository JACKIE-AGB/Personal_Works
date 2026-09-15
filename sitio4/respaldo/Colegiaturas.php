<?php
require_once __DIR__ . '/../db.php';

$metodo = $_SERVER['REQUEST_METHOD'];

if ($metodo === 'GET') {
    try {
        $stmt = $pdo->query(
            'SELECT colegiatura_id, alumno_id, monto, mes_pagado, fecha_pago, estado_pago
             FROM colegiaturas
             ORDER BY colegiatura_id'
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

    if (!$input || empty($input['colegiatura_id']) || empty($input['alumno_id']) || $input['monto'] === '' || $input['monto'] === null) {
        http_response_code(400);
        echo json_encode([
            'success' => false,
            'error'   => 'Faltan campos requeridos: colegiatura_id, alumno_id y monto.',
        ]);
        exit;
    }

    try {
        $stmt = $pdo->prepare(
            'INSERT INTO colegiaturas (colegiatura_id, alumno_id, monto, mes_pagado, fecha_pago, estado_pago)
             VALUES (:colegiatura_id, :alumno_id, :monto, :mes_pagado, :fecha_pago, :estado_pago)'
        );
        $stmt->execute([
            ':colegiatura_id' => $input['colegiatura_id'],
            ':alumno_id'      => $input['alumno_id'],
            ':monto'          => $input['monto'],
            ':mes_pagado'     => $input['mes_pagado'] !== '' ? $input['mes_pagado'] : null,
            ':fecha_pago'     => $input['fecha_pago'] !== '' ? $input['fecha_pago'] : null,
            ':estado_pago'    => $input['estado_pago'] !== '' ? $input['estado_pago'] : 'Pendiente',
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