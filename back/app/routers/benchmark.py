"""
COMPARACIÓN DE ARQUITECTURAS DE INGESTA Y DE API (Business Intelligence)
Actividad N° 1 - Benchmark Técnico con PostgreSQL + Redis en Podman

Endpoints disponibles:
  1. GET /api/v1/tradicional/{dni} -> API Tradicional (Síncrona y Bloqueante)
  2. GET /api/v1/lambda/{dni}      -> Arquitectura Lambda (Batch Layer + Speed Layer + Serving Layer)
  3. GET /api/v1/kappa/{dni}       -> Arquitectura Kappa (Redis Streams / Event Buffer + Serving Layer)

"""

from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.orm import Session
import time
import json
import queue
import threading
from datetime import datetime
import redis

from app.database import get_db, SessionLocal
from app.models import Padron, LogConsulta

router = APIRouter(
    prefix="/api/v1",
    tags=["Comparación de Arquitecturas (Tradicional vs Lambda vs Kappa)"]
)

# CONEXIÓN A REDIS (Contenedor Podman)

try:
    redis_conn = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True, socket_timeout=1)
    redis_conn.ping()
    REDIS_ACTIVO = True
    print("[INFO] Conectado exitosamente a Redis en Podman (localhost:6379)")
except Exception as err:
    REDIS_ACTIVO = False
    redis_conn = None
    print(f"[WARN] Redis no disponible ({err}). Usando fallback en memoria.")

# Fallback en memoria si Redis no estuviera disponible
memory_fallback_queue = queue.Queue(maxsize=300000)
MEMORY_SERVING_CACHE: dict[str, dict] = {}

# MOTOR DE PROCESAMIENTO KAPPA (Consumidor Streaming en Lotes)

def kappa_stream_consumer():
    """
    Consumidor de Streaming (Arquitectura Kappa):
    Extrae continuamente los eventos desde Redis (o cola fallback) y realiza
    inserciones masivas (micro-batches) en PostgreSQL usando 1 sola conexión.
    """
    while True:
        items = []
        try:
            if REDIS_ACTIVO and redis_conn:
                # Extraer hasta 250 eventos de la cola Redis de golpe
                raw_events = redis_conn.lpop("stream:consultas", count=250)
                if raw_events:
                    items = [json.loads(e) for e in raw_events]
                else:
                    time.sleep(0.1)
            else:
                item = memory_fallback_queue.get(timeout=0.5)
                items.append(item)
                while len(items) < 250:
                    try:
                        items.append(memory_fallback_queue.get_nowait())
                    except queue.Empty:
                        break
        except Exception:
            time.sleep(0.1)
            continue

        if items:
            db: Session = SessionLocal()
            try:
                registros = [
                    LogConsulta(
                        documento=it["dni"],
                        tipo_busqueda="DNI",
                        ip_cliente=it["ip"],
                        fue_encontrado=it["encontrado"],
                        tipo_persona=it.get("tipo"),
                        es_miembro_mesa=False
                    )
                    for it in items
                ]
                db.bulk_save_objects(registros)
                db.commit()
            except Exception as e:
                print(f"[Kappa Processor Error]: {e}")
                db.rollback()
            finally:
                db.close()


# Iniciar el consumidor de Kappa en segundo plano
threading.Thread(target=kappa_stream_consumer, daemon=True).start()


# SPEED LAYER DE ARQUITECTURA LAMBDA (Worker de consolidación)

LAMBDA_SPEED_QUEUE: list[dict] = []
LAMBDA_LOCK = threading.Lock()


def lambda_speed_worker(dni: str, ip: str, encontrado: bool, tipo: str | None):
    """Speed Layer de Lambda: almacena temporalmente y consolida periódicamente."""
    with LAMBDA_LOCK:
        LAMBDA_SPEED_QUEUE.append({
            "dni": dni,
            "ip": ip,
            "timestamp": datetime.now().isoformat(),
            "encontrado": encontrado,
            "tipo": tipo
        })
        if len(LAMBDA_SPEED_QUEUE) >= 100:
            a_guardar = list(LAMBDA_SPEED_QUEUE)
            LAMBDA_SPEED_QUEUE.clear()

            db: Session = SessionLocal()
            try:
                logs = [
                    LogConsulta(
                        documento=it["dni"],
                        tipo_busqueda="DNI",
                        ip_cliente=it["ip"],
                        fue_encontrado=it["encontrado"],
                        tipo_persona=it["tipo"],
                        es_miembro_mesa=False
                    )
                    for it in a_guardar
                ]
                db.bulk_save_objects(logs)
                db.commit()
            except Exception as ex:
                print(f"[Lambda Batch Layer Error]: {ex}")
                db.rollback()
            finally:
                db.close()


# ENDPOINT 1: ARQUITECTURA DE API TRADICIONAL (Síncrona y Bloqueante)

@router.get("/tradicional/{dni}")
@router.get("/benchmark/ingesta-directa/{dni}")
def api_tradicional(dni: str, request: Request, db: Session = Depends(get_db)):
    """
    ARQUITECTURA 1: API REST TRADICIONAL
    - Consulta la base de datos de forma síncrona.
    - Ejecuta un INSERT bloqueante en 'log_consultas' en la misma transacción HTTP.
    - Cuello de botella: Satura las conexiones de PostgreSQL bajo estrés masivo.
    """
    inicio = time.perf_counter()

    # 1. Lectura síncrona en PostgreSQL
    persona = db.query(Padron).filter(Padron.dni == dni).first()

    # 2. Ingesta síncrona bloqueante directa
    ip = request.client.host if request.client else "unknown"
    log = LogConsulta(
        documento=dni,
        tipo_busqueda="DNI",
        ip_cliente=ip,
        fue_encontrado=persona is not None,
        tipo_persona=persona.tipo if persona else None,
        es_miembro_mesa=False
    )
    db.add(log)
    db.commit()

    latencia_ms = (time.perf_counter() - inicio) * 1000

    return {
        "arquitectura": "1. API Tradicional (Sincrona Bloqueante)",
        "patron": "Request-Response directo a RDBMS",
        "dni": dni,
        "encontrado": persona is not None,
        "nombre": persona.nombre_completo if persona else None,
        "local_votacion": persona.elector.local_votacion if (persona and persona.elector) else None,
        "latencia_ms": round(latencia_ms, 2)
    }


# ENDPOINT 2: ARQUITECTURA LAMBDA (Batch Layer + Speed Layer + Serving Layer)
@router.get("/lambda/{dni}")
def arquitectura_lambda(
    dni: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    ARQUITECTURA 2: ARQUITECTURA LAMBDA
    - Batch Layer: Consulta las vistas maestras indexadas de PostgreSQL.
    - Speed Layer: Encola el evento reciente en la Speed Layer sin bloquear.
    - Serving Layer: Vista consolidada maestro + deltas.
    """
    inicio = time.perf_counter()
    ip = request.client.host if request.client else "unknown"

    # 1. Batch Layer (Lectura del maestro)
    persona = db.query(Padron).filter(Padron.dni == dni).first()

    # 2. Speed Layer (Ingesta en tiempo real desacoplada)
    background_tasks.add_task(
        lambda_speed_worker,
        dni=dni,
        ip=ip,
        encontrado=persona is not None,
        tipo=persona.tipo if persona else None
    )

    latencia_ms = (time.perf_counter() - inicio) * 1000

    return {
        "arquitectura": "2. Arquitectura Lambda",
        "patron": "Batch Layer (Master DB) + Speed Layer (Deltas) + Serving Layer",
        "dni": dni,
        "encontrado": persona is not None,
        "nombre": persona.nombre_completo if persona else None,
        "latencia_ms": round(latencia_ms, 2)
    }

# ENDPOINT 3: ARQUITECTURA KAPPA (Redis Streams + Serving Layer en Memoria)
@router.get("/kappa/{dni}")
@router.get("/benchmark/ingesta-async/{dni}")
def arquitectura_kappa(dni: str, request: Request, db: Session = Depends(get_db)):
    """
    ARQUITECTURA 3: ARQUITECTURA KAPPA (Con Redis en Podman)
    - Serving Layer: Cache en Redis Key-Value para respuestas en < 1 ms.
    - Stream Log: Evento publicado en Redis Stream/List ('stream:consultas') en 1 ms.
    - Stream Processor: Worker que vuelca micro-lotes masivos a PostgreSQL.
    """
    inicio = time.perf_counter()
    ip = request.client.host if request.client else "unknown"

    datos = None

    # 1. Serving Layer (Consulta rápida en Redis)
    if REDIS_ACTIVO and redis_conn:
        try:
            cached_str = redis_conn.get(f"elector:{dni}")
            if cached_str:
                datos = json.loads(cached_str)
        except Exception:
            pass

    # Si no estaba en Redis, consultar PostgreSQL y guardarlo en la Serving Layer
    if not datos:
        persona = db.query(Padron).filter(Padron.dni == dni).first()
        if persona:
            datos = {
                "encontrado": True,
                "nombre": persona.nombre_completo,
                "tipo": persona.tipo,
                "local": persona.elector.local_votacion if persona.elector else None
            }
        else:
            datos = {"encontrado": False, "nombre": None, "tipo": None, "local": None}

        if REDIS_ACTIVO and redis_conn:
            try:
                redis_conn.set(f"elector:{dni}", json.dumps(datos), ex=3600)
            except Exception:
                pass

    # 2. Ingesta al Stream Log (Redis)
    evento = {
        "dni": dni,
        "ip": ip,
        "encontrado": datos["encontrado"],
        "tipo": datos["tipo"],
        "timestamp": time.time()
    }

    if REDIS_ACTIVO and redis_conn:
        try:
            redis_conn.rpush("stream:consultas", json.dumps(evento))
        except Exception:
            memory_fallback_queue.put_nowait(evento)
    else:
        memory_fallback_queue.put_nowait(evento)

    latencia_ms = (time.perf_counter() - inicio) * 1000

    return {
        "arquitectura": "3. Arquitectura Kappa (Streaming Puro con Redis en Podman)",
        "patron": "Unified Stream Broker (Redis) + Stream Processor + Serving Layer (RAM)",
        "dni": dni,
        "encontrado": datos["encontrado"],
        "nombre": datos["nombre"],
        "motor_streaming": "Redis en Podman" if REDIS_ACTIVO else "In-Memory Buffer",
        "latencia_ms": round(latencia_ms, 2)
    }
