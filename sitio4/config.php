<?php
// config.php
// Datos de conexión a tu base de datos local en MySQL Workbench.
// Ajusta $usuario y $password si tu MySQL local los tiene distintos.

$host     = 'localhost';
$usuario  = 'root';
$password = '';           // <-- pon aquí tu contraseña de MySQL si tienes una
$basedatos = 'EscuelaDB';

$conn = new mysqli($host, $usuario, $password, $basedatos);

if ($conn->connect_error) {
    http_response_code(500);
    header('Content-Type: application/json');
    echo json_encode(['error' => 'Error de conexión: ' . $conn->connect_error]);
    exit;
}

$conn->set_charset('utf8mb4');
