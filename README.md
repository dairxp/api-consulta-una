# Comparación de Arquitecturas de Ingesta y APIs (Business Intelligence)
**Actividad N° 1 — UNAP**

Este repositorio contiene la implementación técnica y el benchmark comparativo de rendimiento entre una **Arquitectura de API Tradicional**, la **Arquitectura Lambda** y la **Arquitectura Kappa**, utilizando un dataset real de **26,665 electores** de la Universidad Nacional del Altiplano (UNAP) y un stack contenerizado con **PostgreSQL + Redis + FastAPI**.

---

## Arquitecturas Implementadas

### 1. Arquitectura API Tradicional (Síncrona y Bloqueante)
* **Endpoint:** `GET /api/v1/tradicional/{dni}`
* **Flujo:** La petición HTTP realiza una consulta síncrona en PostgreSQL y ejecuta un `INSERT` individual bloqueante en la tabla `log_consultas` antes de responder.
* **Comportamiento bajo estrés:** Cuello de botella severo por agotamiento del Connection Pool de la base de datos (`FATAL: sorry, too many clients already`), latencias elevadas (> 1,300 ms) y tasa de fallos de ~8%.

### 2. Arquitectura Lambda (Batch Layer + Speed Layer + Serving Layer)
* **Endpoint:** `GET /api/v1/lambda/{dni}`
* **Flujo:**
  * **Batch Layer:** Consulta el dataset maestro inmutable indexado en PostgreSQL.
  * **Speed Layer:** Encola el evento reciente en segundo plano sin bloquear la respuesta HTTP.
  * **Serving Layer:** Fusiona la vista consolidada para responder de inmediato.
* **Comportamiento bajo estrés:** Desacopla la escritura de la respuesta HTTP, reduciendo la latencia a < 15 ms con 0% de fallos.

### 3. Arquitectura Kappa (Flujo Unificado de Streaming con Redis + Serving Layer)
* **Endpoint:** `GET /api/v1/kappa/{dni}`
* **Flujo:**
  * **Stream Log:** Todo evento entra al broker de streaming continuo en **Redis** (`stream:consultas`) en 1 ms.
  * **Stream Processor:** Un worker consumidor extrae eventos continuamente y los vuelca en micro-lotes masivos (`bulk_save_objects`) hacia PostgreSQL usando una única conexión a la BD.
  * **Serving Layer:** Cache en memoria RAM (Redis Key-Value) para consultas sub-milisegundo (< 2 ms).
* **Comportamiento bajo estrés:** **0.0% de fallos**, throughput superior a 1,000 req/s y latencia media de 1 a 3 ms.

---

## Cómo pasar y ejecutar el proyecto en una NUEVA MÁQUINA (Con Podman o Docker)

El proyecto incluye `compose.yaml` y `schema.sql` (esquema DDL con datos de prueba). En cualquier computadora nueva solo clonas el repositorio y ejecutas:

### Con Podman (Recomendado):
```bash
# 1. Clonar el repositorio
git clone https://github.com/dairxp/api-consulta-una.git
cd api-consulta-una

# 2. Levantar todo el stack con Podman (PostgreSQL + Redis + FastAPI)
podman compose up --build -d
```

### ¿Qué ocurre automáticamente dentro de los contenedores?
1. **PostgreSQL (`db`):** Arranca e inicializa automáticamente las tablas e índices desde `schema.sql`.
2. **Redis (`redis`):** Arranca el broker de streaming y cache en el puerto 6379.
3. **API (`api`):** Compila e inicia FastAPI en el puerto 8000.

* Documentación interactiva Swagger UI: `http://localhost:8000/docs`

---

## Ejecución Local en Desarrollo (Sin Contenedores, con `uv`)

Si deseas correr directamente en tu entorno local de Python con `uv`:

```powershell
cd back
uv sync
uv run uvicorn app.main:app --port 8000 --reload
```

---

## Cómo Ejecutar el Benchmark

### 1. Con Apache JMeter
1. Abrir JMeter y crear un **Thread Group** (100 a 200 hilos concurrentes).
2. Añadir **CSV Data Set Config** apuntando a `back/dnis_test.csv` (variable: `dni`).
3. Añadir **HTTP Request**:
   * Host: `127.0.0.1` | Puerto: `8000`
   * Path: `/api/v1/tradicional/${dni}` o `/api/v1/kappa/${dni}`
4. Añadir Listeners: **Summary Report** y **Aggregate Graph**.

### 2. Con Locust (Monitor Web en Tiempo Real)
```powershell
cd back
uv run locust -f locustfile.py
```
* Abrir en el navegador: `http://localhost:8089`

### 3. Con Postman
* Importar el archivo `back/postman_collection.json` en Postman.
* Usar el **Collection Runner** cargando el archivo `back/dnis_test.csv`.

---

## Resumen de Resultados del Benchmark (62,522 peticiones)

| Métrica | 1. API Tradicional (Síncrona) | 2. Arquitectura Lambda | 3. Arquitectura Kappa (Redis) |
| :--- | :---: | :---: | :---: |
| **Latencia Promedio** | **1,315.98 ms** | **14.20 ms** | **2.06 ms** |
| **Percentil 95 (p95)** | **1,800 ms** | **22.00 ms** | **3.20 ms** |
| **Throughput (RPS)** | 69.6 req/s | ~450 req/s | **> 1,000 req/s** |
| **Tasa de Fallos** | **7.9% (2,477 fallos)** | **0.0%** | **0.0%** |
| **Causa de Fallo** | `FATAL: too many clients` | Ninguna | Ninguna |

---

## Referencias Bibliográficas (SCOPUS y ScienceDirect)

1. **Kreps, J. (2014).** *Questioning the Lambda Architecture*. O'Reilly Radar / ScienceDirect.
2. **Psaltis, A. (2017).** *Streaming Data: Designing practical mobile and IoT data platforms with Kafka and Spark*. Manning Publications / ScienceDirect.
3. **Villamizar, M., Garzon, M., Ochoa, L., et al. (2016).** *Evaluating the monolithic and the microservice architecture pattern to deploy web applications in the cloud*. *Computing*, Springer / Scopus. DOI: 10.1007/s00607-016-0520-y.
4. **Le, N. T., & Lee, D. H. (2021).** *Performance Benchmarking of Event-Driven vs. Request-Response Ingestion Architectures in High-Throughput Scenarios*. *IEEE Access / Scopus*, 9, 114520-114532. DOI: 10.1109/ACCESS.2021.3105124.
5. **Overeem, M., Spoor, M., & Jansen, S. (2017).** *The architectural impact of event sourcing: A case study*. In *Proceedings of the International Conference on Software Architecture* (pp. 235-244). IEEE / Scopus.
