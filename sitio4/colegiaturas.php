<?php
/**
 * api/colegiaturas.php
 * GET  ?alumno_id=X -> lista colegiaturas (de un alumno, o todas si no se manda)
 * POST -> agrega una nueva colegiatura (recibe JSON)
 */

header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../db.php';

$metodo = $_SERVER['REQUEST_METHOD'];

try {
    if ($metodo === 'GET') {
        $alumnoId = $_GET['alumno_id'] ?? null;

        if ($alumnoId) {
            $stmt = $pdo->prepare("SELECT * FROM Colegiaturas WHERE alumno_id = :id ORDER BY Colegiatura_id DESC");
            $stmt->execute([':id' => $alumnoId]);
        } else {
            $stmt = $pdo->query("SELECT * FROM Colegiaturas ORDER BY Colegiatura_id DESC");
        }

        echo json_encode(['success' => true, 'data' => $stmt->fetchAll()]);
        exit;
    }

    if ($metodo === 'POST') {
        $body = json_decode(file_get_contents('php://input'), true);
        if (!is_array($body)) {
            http_response_code(400);
            echo json_encode(['success' => false, 'error' => 'Datos inválidos enviados al servidor.']);
            exit;
        }

        $alumno_id  = $body['alumno_id']  ?? null;
        $monto      = $body['monto']      ?? null;
        $mes_pago   = trim($body['mes_pago'] ?? '');
        $fecha_pago = trim($body['fecha_pago'] ?? '');
        $estado_pago= trim($body['estado_pago'] ?? 'Pendiente');

        $errores = [];
        if (!$alumno_id || !ctype_digit((string)$alumno_id)) $errores[] = 'Falta el alumno.';
        if ($monto === null || !is_numeric($monto) || $monto < 0) $errores[] = 'El monto debe ser un número válido.';
        if ($mes_pago === '') $errores[] = 'El mes de pago es obligatorio.';
        if ($fecha_pago !== '' && !preg_match('/^\d{4}-\d{2}-\d{2}$/', $fecha_pago)) {
            $errores[] = 'La fecha de pago debe tener formato AAAA-MM-DD.';
        }

        // Verificar que el alumno exista
        if (empty($errores)) {
            $chk = $pdo->prepare("SELECT 1 FROM Alumnos WHERE Alumno_id = :id");
            $chk->execute([':id' => $alumno_id]);
            if (!$chk->fetch()) {
                $errores[] = 'El alumno indicado no existe.';
            }
        }

        if (!empty($errores)) {
            http_response_code(422);
            echo json_encode(['success' => false, 'error' => implode(' ', $errores)]);
            exit;
        }

        $stmt = $pdo->prepare(
            "INSERT INTO Colegiaturas (alumno_id, monto, mes_pago, fecha_pago, estado_pago)
             VALUES (:alumno_id, :monto, :mes_pago, :fecha_pago, :estado_pago)"
        );
        $stmt->execute([
            ':alumno_id'   => $alumno_id,
            ':monto'       => $monto,
            ':mes_pago'    => $mes_pago,
            ':fecha_pago'  => $fecha_pago ?: null,
            ':estado_pago' => $estado_pago ?: 'Pendiente',
        ]);

        $nuevoId = $pdo->lastInsertId();
        $stmt = $pdo->prepare("SELECT * FROM Colegiaturas WHERE Colegiatura_id = :id");
        $stmt->execute([':id' => $nuevoId]);

        echo json_encode(['success' => true, 'data' => $stmt->fetch()]);
        exit;
    }

    http_response_code(405);
    echo json_encode(['success' => false, 'error' => 'Método no permitido.']);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => 'Error en la base de datos: ' . $e->getMessage()]);
}
