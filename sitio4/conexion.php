<?php
$host = "localhost:8000";
$usuario = "root";
$password = "SQLWORKBENCH";
$base_datos = "EscuelaDB";

$conexion = new mysqli($host, $usuario, $password, $base_datos);

if ($conexion->connect_error) {
    die("Error de conexión: " . $conexion->connect_error);
}

$conexion->set_charset("utf8");
?>