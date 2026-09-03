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
-- Table structure for table `colegiaturas`
--

DROP TABLE IF EXISTS `colegiaturas`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `colegiaturas` (
  `colegiatura_id` int NOT NULL,
  `alumno_id` int DEFAULT NULL,
  `monto` decimal(10,2) NOT NULL,
  `mes_pagado` varchar(20) NOT NULL,
  `fecha_pago` date DEFAULT NULL,
  `estado_pago` varchar(15) DEFAULT 'Pagado',
  PRIMARY KEY (`colegiatura_id`),
  KEY `alumno_id` (`alumno_id`),
  CONSTRAINT `colegiaturas_ibfk_1` FOREIGN KEY (`alumno_id`) REFERENCES `alumnos` (`alumno_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `colegiaturas`
--

LOCK TABLES `colegiaturas` WRITE;
/*!40000 ALTER TABLE `colegiaturas` DISABLE KEYS */;
INSERT INTO `colegiaturas` VALUES (1,1,1500.00,'Marzo','2026-03-10','Pagado'),(2,2,1500.00,'Septiembre','2026-09-11','Pagado'),(4,4,1500.00,'Junio','2026-06-13','Pagado'),(5,5,1500.00,'Noviembre','2026-11-14','Pagado'),(6,6,1500.00,'Febrero','2026-02-15','Pagado'),(7,7,1500.00,'Mayo','2026-05-16','Pagado'),(8,8,1500.00,'Agosto','2026-08-17','Pagado'),(9,9,1500.00,'Abril','2026-04-18','Pagado'),(11,11,1500.00,'Octubre','2026-10-20','Pagado'),(13,13,1500.00,'Mayo','2026-05-22','Pagado'),(14,14,1500.00,'Enero','2026-01-23','Pagado'),(15,15,1500.00,'Septiembre','2026-09-24','Pagado'),(16,16,1500.00,'Marzo','2026-03-25','Pagado'),(17,17,1500.00,'Febrero','2026-02-26','Pagado'),(18,18,1500.00,'Junio','2026-06-27','Pagado'),(19,19,1500.00,'Agosto','2026-08-28','Pagado'),(20,20,1500.00,'Octubre','2026-10-29','Pagado');
/*!40000 ALTER TABLE `colegiaturas` ENABLE KEYS */;
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
