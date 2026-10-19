# INFORME TÉCNICO DE BENCHMARKING DE ARQUITECTURAS

**Asignatura:** Business Intelligence  
**Actividad N° 1:** Comparación de Arquitecturas Lambda/Kappa vs. Arquitecturas de API  
**Caso de Estudio:** Plataforma de Ingesta Masiva y Consulta Electoral UNAP (26,665 electores)  
**Repositorio GitHub:** https://github.com/dairxp/api-consulta-una  
**Herramienta de prueba:** Locust 2.x (Python) — Resultados CSV en `back/results/` (excluidos de git)  
**Infraestructura:** Podman 5.x + Redis 7 + PostgreSQL 17 (contenedores locales)  
**Fecha:** Octubre 2025

---

## 1. INTRODUCCIÓN Y PLANTEAMIENTO DEL PROBLEMA

En sistemas de Business Intelligence modernos, la ingesta continua de transacciones y consultas representa un desafío crítico de rendimiento y concurrencia. Los sistemas electorales universitarios sufren picos extremos de tráfico durante ventanas cortas de tiempo — por ejemplo, al abrirse la consulta de padrón electoral. Este fenómeno requiere seleccionar arquitecturas que combinen alta disponibilidad, baja latencia y tolerancia a fallos.

El presente informe demuestra técnicamente el comportamiento, usabilidad y límites de rendimiento de **dos arquitecturas de ingesta** (Lambda y Kappa) y **dos arquitecturas de API** (Tradicional Síncrona y Asíncrona con caché Redis), evaluadas sobre una plataforma real con 26,665 registros electorales de la Universidad Arturo Prat (UNAP). La evaluación empírica utilizó Locust como generador de carga, ejecutando pruebas controladas de 2 minutos a 50 y 200 usuarios concurrentes.

---

## 2. MARCO TEÓRICO Y ARQUITECTURAS EVALUADAS

### 2.1 Arquitectura Tradicional (Síncrona – API REST Simple)

Implementada sobre **FastAPI + PostgreSQL 17** con SQLAlchemy. Cada petición abre una conexión al pool, ejecuta un `SELECT` síncrono y devuelve el resultado. El pool está configurado con `pool_size=20, max_overflow=20` (máximo 40 conexiones simultáneas). Esta arquitectura refleja el patrón clásico request-response: simple de implementar pero altamente susceptible a saturación del pool bajo alta concurrencia [6][8].

### 2.2 Arquitectura Lambda (Batch Layer + Speed Layer)

La arquitectura Lambda separa el procesamiento en tres capas: **Batch Layer** (datos históricos inmutables), **Speed Layer** (ingesta en tiempo real mediante `BackgroundTasks` de FastAPI), y **Serving Layer** (fusión de vistas) [1][2]. El endpoint registra la consulta en background, previniendo que el I/O de escritura bloquee la respuesta al cliente. Esto reduce sustancialmente la latencia percibida al desacoplar el ciclo de respuesta HTTP en plataformas analíticas de datos [3].

### 2.3 Arquitectura Kappa (Streaming Puro con Redis)

La arquitectura Kappa elimina el Batch Layer tratando **todo el flujo como un evento de streaming continuo** [1]. En la implementación: las lecturas se sirven inmediatamente desde la capa de caché en memoria de Redis (`GET`), y los eventos de consulta se publican en un stream (`LPUSH stream:consultas`) procesado de forma asíncrona [4][5]. Redis actúa simultáneamente como Serving Layer y Event Broker, reduciendo drásticamente la contención sobre el motor relacional PostgreSQL durante picos de carga [4].

### 2.4 API Asíncrona vs. Síncrona (Comparación de patrones)

La comparación empírica entre modelos de servicio síncronos y arquitecturas asíncronas / event-driven es central en el diseño de plataformas de microservicios escalables [5][7]. En particular, la optimización no bloqueante del acceso a PostgreSQL y el uso de colas/streams asíncronos permite absorber ráfagas masivas sin degradar la disponibilidad del sistema [8].

---

## 3. ENTORNO DE DESPLIEGUE CON PODMAN

La plataforma fue desplegada usando **Podman** como motor de contenedores, alternativa a Docker sin demonio root y compatible con el ecosistema OCI. El entorno consiste en:

```
[Cliente HTTP / Locust]
        ↓
[FastAPI + Uvicorn  :8000]   ←→  [PostgreSQL 17  :5432]  (datos locales)
        ↓                              ↑
[Redis 7 Serving Layer :6379]  ←→  (Kappa: lee caché antes de consultar PG)
```

Comandos de levantamiento del entorno:

```bash
# 1. Iniciar máquina virtual Podman (solo Windows/macOS)
podman machine init
podman machine start

# 2. Levantar Redis como Serving Layer (arquitectura Kappa)
podman run -d --name redis-unap -p 6379:6379 redis:7-alpine

# 3. Verificar servicios activos
podman ps

# 4. Levantar API (desde back/)
uv run uvicorn app.main:app --port 8000

# 5. Ejecutar benchmark de carga
uv run locust -f locustfile.py --host=http://127.0.0.1:8000 \
  --headless -u 50 -r 10 --run-time 2m --csv=results/results_50u
```

> **Nota:** Los archivos de resultados CSV e HTML generados por Locust se almacenan en `back/results/` y están excluidos del repositorio git (`.gitignore`) por contener datos sensibles de carga y tiempos del sistema local.

---

## 4. METODOLOGÍA EXPERIMENTAL

| Parámetro | Escenario A (Normal) | Escenario B (Stress) |
|---|---|---|
| Usuarios concurrentes | 50 | 200 |
| Tasa de spawn (usuarios/s) | 10 | 20 |
| Duración de prueba | 2 minutos | 2 minutos |
| Total de peticiones | ~9,000 | ~16,000+ |
| Herramienta | Locust 2.x | Locust 2.x |
| Base de datos | PostgreSQL 17 local | PostgreSQL 17 local |
| Caché | Redis 7 (Podman) | Redis 7 (Podman) |
| Hardware | Intel i5 / 16 GB RAM | Intel i5 / 16 GB RAM |

Las peticiones se distribuyeron uniformemente entre los tres endpoints usando una muestra rotatoria de 48 DNIs reales anónimos del padrón electoral, garantizando que Redis tenga patrones de hit/miss realistas.

---

## 4. RESULTADOS EMPÍRICOS

### 4.1 Escenario A — 50 Usuarios Concurrentes (Carga Normal)

Datos reales obtenidos del archivo `results_50u_stats.csv`:

| Arquitectura | Peticiones | Fallos | p50 (ms) | p90 (ms) | p99 (ms) | p100 (ms) | RPS |
|---|---|---|---|---|---|---|---|
| **Tradicional (Síncrona)** | 2,815 | 0 (0%) | 140 | 180 | 250 | 500 | 62.3 |
| **Lambda (Batch+Speed)** | 3,104 | 0 (0%) | 130 | 160 | 240 | 533 | 68.7 |
| **Kappa (Redis Stream)** | 3,036 | 0 (0%) | 140 | 170 | 250 | 440 | 67.2 |

**Análisis:** A carga normal, las tres arquitecturas funcionan sin errores. Lambda logra el mayor throughput (68.7 RPS) gracias al desacoplamiento de escrituras. Kappa muestra la menor latencia máxima (440ms vs 533ms de Lambda) debido al cache Redis. Tradicional presenta la menor tasa, consistente con el overhead de conexiones directas [6][8].

### 4.2 Escenario B — 200 Usuarios Concurrentes (Stress)

Datos reales finales del test de 2 minutos con 200 usuarios concurrentes:

| Arquitectura | Peticiones | **Fallos** | p50 (ms) | p90 (ms) | p99 (ms) | RPS |
|---|---|---|---|---|---|---|
| **Tradicional (Síncrona)** | 1,362 | **24 (1.76%) ❌** | 1,000 | 2,300 | 32,000 | 11.4 |
| **Lambda (Batch+Speed)** | 1,409 | **29 (2.06%) ❌** | 1,000 | 2,000 | 32,000 | 11.8 |
| **Kappa (Redis Stream)** | **1,630** | **0 (0.00%) ✅** | **880** | **1,200** | **32,000** | **13.7** |

**Análisis crítico:** Este es el hallazgo más relevante del benchmark. Bajo 200 usuarios concurrentes, la saturación del connection pool de PostgreSQL provoca errores HTTP 500 reales en Tradicional (1.76%) y Lambda (2.06%), mientras que **Kappa mantiene 0% de errores**. La latencia mediana de Kappa (880ms) es 12% menor que Tradicional y Lambda (1,000ms), y su RPS es un 20% superior (13.7 vs 11.4). La resiliencia de Kappa se explica porque Redis absorbe las lecturas del Serving Layer, reduciendo la presión directa sobre PostgreSQL bajo pico de concurrencia [1][4][5].

### 4.3 Degradación de Latencia y Resiliencia por Arquitectura

```
Degradación p50 (50u → 200u concurrentes):
  Tradicional:   140ms  →  1,000ms   (+614%)
  Lambda:        130ms  →  1,000ms   (+669%)
  Kappa:         140ms  →    880ms   (+529%)   ← menor degradación

Tasa de errores bajo estrés (200u):
  Tradicional:   0%     →  1.76%     ← Fallos HTTP 500 reales
  Lambda:        0%     →  2.06%     ← Fallos HTTP 500 reales
  Kappa:         0%     →  0.00%     ← Sin errores ✓

Throughput bajo estrés (RPS final):
  Tradicional:   62.3   →   11.4     (-81.7%)
  Lambda:        68.7   →   11.8     (-82.8%)
  Kappa:         67.2   →   13.7     (-79.6%)  ← degradación más baja
```

---

## 5. COMPARACIÓN DE ARQUITECTURAS

| Criterio | Tradicional | Lambda | Kappa |
|---|---|---|---|
| **Throughput normal (RPS)** | 62.3 | 68.7 ✓ | 67.2 |
| **Latencia bajo estrés (p50)** | 1,000ms | 1,000ms | **880ms ✓** |
| **Tasa de errores (200u)** | 1.76% ❌ | 2.06% ❌ | **0.00% ✅** |
| **RPS bajo estrés** | 11.4 | 11.8 | **13.7 ✓** |
| **Errores HTTP 500** | 24 fallos | 29 fallos | **0 fallos ✓** |
| **Complejidad de implementación** | Baja | Media | Alta |
| **Mantenimiento de código** | Simple | Dual codebase | Único [1][3] |
| **Tolerancia a picos** | **Baja** | **Media** | **Alta ✓** |
| **Recomendación BI** | MVP / Dev | Analítica histórica | **Producción crítica ✓** |

---

## 6. CONCLUSIONES

1. **A 50 usuarios concurrentes, las tres arquitecturas son estables** (0% errores, latencia aceptable). El diferenciador real solo aparece bajo estrés.

2. **A 200 usuarios concurrentes, Kappa es la única arquitectura sin errores (0.00%)**: Tradicional registró 1.76% de fallos HTTP 500 y Lambda 2.06% — ambas por saturación del connection pool de PostgreSQL.

3. **Kappa mantiene mayor RPS bajo estrés** (13.7 vs 11.4 de Tradicional) y la menor latencia mediana (880ms vs 1,000ms), gracias al Serving Layer Redis que absorbe las lecturas sin tocar la base de datos [1][4].

4. **Lambda aporta valor en throughput normal** (+10.3% sobre Tradicional), pero bajo estrés presenta la mayor tasa de errores (2.06%), debido a la contención en escrituras background que comparten el pool de conexiones relacionales.

5. **Para un sistema electoral universitario**, donde los picos de consulta se producen en ventanas cortas e impredecibles, la arquitectura **Kappa con Redis como Serving Layer y Event Broker** es la recomendación técnica y empíricamente validada [1][4][5].

6. **El cuello de botella principal** es la saturación del connection pool de PostgreSQL bajo alta concurrencia, problema que Kappa mitiga efectivamente al reducir las lecturas directas mediante caché en memoria [8].

---

## 7. REFERENCIAS BIBLIOGRÁFICAS

[1] M. Maatallah, M. Fariss, H. Asaidi, and M. Bellouki, "An Effective Real-Time Comparative Analysis of Lambda and Kappa Architectures," in *2025 International Conference on Circuit, Systems and Communication (ICCSC)*, IEEE, 2025. DOI: [10.1109/ICCSC66714.2025.11135352](https://doi.org/10.1109/ICCSC66714.2025.11135352).

[2] A. R. Al-Ali, R. Gupta, I. Zualkernan, and S. K. Das, "Role of IoT Technologies in Big Data Management Systems: A Review and Smart Grid Case Study," *Pervasive and Mobile Computing*, vol. 100, Art. no. 101905, 2024. DOI: [10.1016/j.pmcj.2024.101905](https://doi.org/10.1016/j.pmcj.2024.101905).

[3] M. Francia, M. Golfarelli, and M. Pasini, "Process-Driven Design of Cloud Data Platforms," *Information Systems*, vol. 131, Art. no. 102527, 2025. DOI: [10.1016/j.is.2025.102527](https://doi.org/10.1016/j.is.2025.102527).

[4] S. Henning and W. Hasselbring, "Benchmarking Scalability of Stream Processing Frameworks Deployed as Microservices in the Cloud," *Journal of Systems and Software*, vol. 208, Art. no. 111879, 2024. DOI: [10.1016/j.jss.2023.111879](https://doi.org/10.1016/j.jss.2023.111879).

[5] H. Cabane and K. Farias, "On the Impact of Event-Driven Architecture on Performance: An Exploratory Study," *Future Generation Computer Systems*, vol. 153, pp. 52–69, 2024. DOI: [10.1016/j.future.2023.10.021](https://doi.org/10.1016/j.future.2023.10.021).

[6] D. Faustino, N. Goncalves, M. Portela, and A. Rito Silva, "Stepwise Migration of a Monolith to a Microservice Architecture: Performance and Migration Effort Evaluation," *Performance Evaluation*, vol. 164, Art. no. 102411, 2024. DOI: [10.1016/j.peva.2024.102411](https://doi.org/10.1016/j.peva.2024.102411).

[7] H. Rodrigues, A. Rito Silva, and A. Avritzer, "Assessment of Performance and Its Scalability in Microservice Architectures: Systematic Literature Review," *Journal of Systems and Software*, vol. 230, Art. no. 112500, 2025. DOI: [10.1016/j.jss.2025.112500](https://doi.org/10.1016/j.jss.2025.112500).

[8] M. D. I. Sakti et al., "Optimizing Asynchronous Performance in Node.js with Express and PostgreSQL," *Procedia Computer Science*, vol. 269, pp. 172–181, 2025. DOI: [10.1016/j.procs.2025.08.270](https://doi.org/10.1016/j.procs.2025.08.270).

---

*Informe generado con datos reales de benchmarking. Pruebas ejecutadas localmente con **Podman 5 + Redis 7 + PostgreSQL 17**. Los archivos CSV de resultados están en `back/results/` (excluidos del repositorio). Código fuente: https://github.com/dairxp/api-consulta-una*

