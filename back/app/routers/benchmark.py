"""
================================================================================
COMPARACIÓN DE ARQUITECTURAS DE INGESTA Y DE API (Business Intelligence)
Actividad N° 1 - Benchmark Técnico

Endpoints disponibles:
  1. GET /api/v1/tradicional/{dni} -> API Tradicional (Síncrona y Bloqueante)
  2. GET /api/v1/lambda/{dni}      -> Arquitectura Lambda (Batch Layer + Speed Layer + Serving Layer)
  3. GET /api/v1/kappa/{dni}       -> Arquitectura Kappa (Stream Pipeline Unificado + Serving Layer)
================================================================================
"""

from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.orm import Session
import time
import queue
import threading
from datetime import datetime

from app.database import get_db, SessionLocal
from app.models import Padron, LogConsulta

router = APIRouter(
    prefix="/api/v1",
    tags=["Comparación de Arquitecturas (Tradicional vs Lambda vs Kappa)"]
)

# ------------------------------------------------------------------------------
# 1. COMPONENTES ARQUITECTURA KAPPA (Stream Log + Consumidor Batch)
# ------------------------------------------------------------------------------
# Buffer continuo de streaming (simula Apache Kafka Topic / Redis Stream)
stream_event_log = queue.Queue(maxsize=300000)

# Serving Layer rápida en memoria (simula Redis / Speed Layer en RAM)
KAPPA_SERVING_CACHE: dict[str, dict] = {}


def kappa_stream_processor():
    """
    Motor de Procesamiento Streaming (Arquitectura Kappa):
    Consume continuamente los eventos del log y realiza micro-lotes (batch)
    hacia PostgreSQL usando una única conexión periódica.
    """
    while True:
        batch = []
        try:
            # Esperar por el primer evento del stream
            evento = stream_event_log.get(timeout=0.5)
            batch.append(evento)
            # Drenar hasta 250 eventos en cola para inserción masiva
            while len(batch) < 250:
                try:
                    batch.append(stream_event_log.get_nowait())
                except queue.Empty:
                    break
        except queue.Empty:
            continue

        if batch:
            db: Session = SessionLocal()
            try:
                registros = [
                    LogConsulta(
                        documento=item["dni"],
                        tipo_busqueda="DNI",
                        ip_cliente=item["ip"],
                        fue_encontrado=item["encontrado"],
                        tipo_persona=item["tipo"],
                        es_miembro_mesa=False
                    )
                    for item in batch
                ]
                db.bulk_save_objects(registros)
                db.commit()
            except Exception as e:
                print(f"[Kappa Processor Error]: {e}")
                db.rollback()
            finally:
                db.close()

            for _ in batch:
                stream_event_log.task_done()


# Iniciar el consumidor de Kappa en segundo plano
threading.Thread(target=kappa_stream_processor, daemon=True).start()


# ------------------------------------------------------------------------------
# 2. COMPONENTES ARQUITECTURA LAMBDA (Speed Layer delta)
# ------------------------------------------------------------------------------
# Capa Speed: almacena en memoria los deltas en tiempo real antes de consolidación
LAMBDA_SPEED_LAYER: list[dict] = []
LAMBDA_LOCK = threading.Lock()


def lambda_speed_worker(dni: str, ip: str, encontrado: bool, tipo: str | None):
    """Speed Layer de Lambda: almacena temporalmente y consolida periódicamente."""
    with LAMBDA_LOCK:
        LAMBDA_SPEED_LAYER.append({
            "dni": dni,
            "ip": ip,
            "timestamp": datetime.now(),
            "encontrado": encontrado,
            "tipo": tipo
        })
        if len(LAMBDA_SPEED_LAYER) >= 100:
            a_guardar = list(LAMBDA_SPEED_LAYER)
            LAMBDA_SPEED_LAYER.clear()
            
            # Capa Batch persistiendo a PostgreSQL
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
# URL: /api/v1/tradicional/{dni}
=
@router.get("/tradicional/{dni}")
@router.get("/benchmark/ingesta-directa/{dni}")  # Alias compatible
def api_tradicional(dni: str, request: Request, db: Session = Depends(get_db)):
    """
    ARQUITECTURA 1: API REST TRADICIONAL
    - Consulta la BD de forma síncrona.
    - Realiza un INSERT bloqueante en la tabla 'log_consultas' en la misma transacción HTTP.
    - Cuello de botella: Satura el Connection Pool bajo alta concurrencia.
    """
    inicio = time.perf_counter()

    # 1. Lectura síncrona en PostgreSQL
    persona = db.query(Padron).filter(Padron.dni == dni).first()

    # 2. Ingesta individual síncrona bloqueante
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
    db.commit()  # Espera a que el disco confirme la escritura

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
# URL: /api/v1/lambda/{dni}

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
    - Speed Layer: Encola el evento en tiempo real en la Speed Layer sin bloquear.
    - Serving Layer: Fusiona datos maestros con deltas en tiempo real.
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


# ENDPOINT 3: ARQUITECTURA KAPPA (Flujo de Streaming Unificado + Serving Layer)
# URL: /api/v1/kappa/{dni}

@router.get("/kappa/{dni}")
@router.get("/benchmark/ingesta-async/{dni}")  # Alias compatible
def arquitectura_kappa(dni: str, request: Request, db: Session = Depends(get_db)):
    """
    ARQUITECTURA 3: ARQUITECTURA KAPPA
    - Log de Eventos Unificado: Cada consulta entra a un Stream Log inmutable.
    - Serving Layer: Capa rápida en memoria para respuestas < 2 ms.
    - Stream Processor: Un único pipeline de streaming consolida a la BD en micro-lotes.
    """
    inicio = time.perf_counter()
    ip = request.client.host if request.client else "unknown"

    # 1. Serving Layer (Capa de Servicio en RAM)
    datos = KAPPA_SERVING_CACHE.get(dni)
    if not datos:
        persona = db.query(Padron).filter(Padron.dni == dni).first()
        if persona:
            datos = {
                "encontrado": True,
                "nombre": persona.nombre_completo,
                "tipo": persona.tipo,
                "local": persona.elector.local_votacion if persona.elector else None
            }
            KAPPA_SERVING_CACHE[dni] = datos
        else:
            datos = {"encontrado": False, "nombre": None, "tipo": None, "local": None}

    # 2. Ingesta al Stream Log (No bloqueante)
    try:
        stream_event_log.put_nowait({
            "dni": dni,
            "ip": ip,
            "encontrado": datos["encontrado"],
            "tipo": datos["tipo"]
        })
    except queue.Full:
        pass

    latencia_ms = (time.perf_counter() - inicio) * 1000

    return {
        "arquitectura": "3. Arquitectura Kappa (Streaming Puro)",
        "patron": "Unified Event Stream + Kappa Processor + Serving Layer",
        "dni": dni,
        "encontrado": datos["encontrado"],
        "nombre": datos["nombre"],
        "eventos_en_stream": stream_event_log.qsize(),
        "latencia_ms": round(latencia_ms, 2)
    }
