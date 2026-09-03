-- MySQL dump 10.13  Distrib 8.0.45, for Win64 (x86_64)
--
-- Host: localhost    Database: escueladb
-- ------------------------------------------------------
-- Server version	8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `alumnos`
--

DROP TABLE IF EXISTS `alumnos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alumnos` (
  `alumno_id` int NOT NULL,
  `nombre` varchar(50) NOT NULL,
  `apellido` varchar(50) NOT NULL,
  `fecha_nacimiento` date DEFAULT NULL,
  `telefono` varchar(15) DEFAULT NULL,
  `email` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`alumno_id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alumnos`
--

LOCK TABLES `alumnos` WRITE;
/*!40000 ALTER TABLE `alumnos` DISABLE KEYS */;
INSERT INTO `alumnos` VALUES (1,'Juan','Pérez','2005-03-15','3111234567','juan.perez@email.com'),(2,'María','García','2006-07-22','3112345678','maria.garcia@email.com'),(4,'Ana','Martínez','2006-01-18','3114567890','ana.martinez@email.com'),(5,'Luis','Garcia','2005-09-05','3115678901','luis.hernandez@email.com'),(6,'Sofía','Ramírez','2006-04-12','3116789012','sofia.ramirez@email.com'),(7,'Diego','Torres','2005-12-25','3117890123','diego.torres@email.com'),(8,'Laura','Flores','2006-06-30','3118901234','laura.flores@email.com'),(9,'Miguel','Castillo','2005-02-14','3119012345','miguel.castillo@email.com'),(11,'Andrés','Ortiz','2005-05-19','3111234501','andres.ortiz@email.com'),(13,'Fernando','Mendoza','2005-01-27','3113456703','fernando.mendoza@email.com'),(14,'Gabriela','Rojas','2006-03-11','3114567804','gabriela.rojas@email.com'),(15,'Ricardo','Navarro','2005-07-07','3115678905','ricardo.navarro@email.com'),(16,'Daniela','Cruz','2006-09-16','3116789006','daniela.cruz@email.com'),(17,'Jorge','Reyes','2005-10-21','3117890107','jorge.reyes@email.com'),(18,'Natalia','Mendoza','2006-02-28','3118901208','natalia.mendoza@email.com'),(19,'Alejandro','Silva','2005-06-13','3119012309','alejandro.silva@email.com'),(20,'Paola','Jiménez','2006-11-04','3110123410','paola.jimenez@email.com');
/*!40000 ALTER TABLE `alumnos` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-09-03  9:41:52
