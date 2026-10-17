from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from datetime import datetime
import time

from app.database import get_db, SessionLocal
from app.models import Padron, LogConsulta

router = APIRouter(
    prefix="/api/v1/benchmark",
    tags=["Benchmark - Comparación de Arquitecturas"]
)


def worker_ingesta_asincrona(
    documento: str,
    tipo_busqueda: str,
    ip_cliente: str,
    fue_encontrado: bool,
    tipo_persona: str | None
):
    """
    Simulación de Ingesta Asíncrona (Arquitectura orientada a eventos / Kappa):
    Se ejecuta en background sin bloquear la respuesta HTTP al cliente.
    """
    db: Session = SessionLocal()
    try:
        log = LogConsulta(
            documento=documento,
            tipo_busqueda=tipo_busqueda,
            ip_cliente=ip_cliente,
            fue_encontrado=fue_encontrado,
            tipo_persona=tipo_persona,
            es_miembro_mesa=False
        )
        db.add(log)
        db.commit()
    except Exception as e:
        print(f"[Worker Background Error]: {e}")
    finally:
        db.close()


# ==============================================================================
# ARQUITECTURA 1: Ingesta Directa Síncrona (API Tradicional)
# ==============================================================================
@router.get("/ingesta-directa/{dni}")
def test_ingesta_directa(dni: str, request: Request, db: Session = Depends(get_db)):
    """
    Arquitectura 1:
    - Ingesta SÍNCRONA y BLOQUEANTE.
    - La API consulta y realiza el INSERT directo en la misma transacción HTTP.
    - El cliente queda esperando la persistencia en disco de PostgreSQL.
    """
    inicio = time.perf_counter()
    
    # 1. Lectura
    persona = db.query(Padron).filter(Padron.dni == dni).first()
    
    # 2. Ingesta Síncrona Bloqueante (simula cuello de botella en DB)
    log = LogConsulta(
        documento=dni,
        tipo_busqueda="DNI",
        ip_cliente=request.client.host if request.client else "unknown",
        fue_encontrado=persona is not None,
        tipo_persona=persona.tipo if persona else None,
        es_miembro_mesa=False
    )
    db.add(log)
    db.commit()  # Bloquea la conexión hasta confirmar escritura

    latencia_ms = (time.perf_counter() - inicio) * 1000

    return {
        "arquitectura": "1. Ingesta Directa Sincrona (Tradicional)",
        "encontrado": persona is not None,
        "nombre": persona.nombre_completo if persona else None,
        "latencia_interna_ms": round(latencia_ms, 2)
    }


# ==============================================================================
# ARQUITECTURA 2: Ingesta Asíncrona Desacoplada (Streaming / Event-Driven)
# ==============================================================================
@router.get("/ingesta-async/{dni}")
def test_ingesta_async(
    dni: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Arquitectura 2:
    - Ingesta ASÍNCRONA y DESACOPLADA (Estilo Kappa / Event-Driven).
    - La API consulta y despacha el evento a un buffer/cola en memoria.
    - Responde al cliente de inmediato sin esperar la persistencia en DB.
    """
    inicio = time.perf_counter()

    # 1. Lectura
    persona = db.query(Padron).filter(Padron.dni == dni).first()

    # 2. Ingesta Asíncrona (Se delega a la cola sin bloquear al usuario)
    ip_cliente = request.client.host if request.client else "unknown"
    background_tasks.add_task(
        worker_ingesta_asincrona,
        documento=dni,
        tipo_busqueda="DNI",
        ip_cliente=ip_cliente,
        fue_encontrado=persona is not None,
        tipo_persona=persona.tipo if persona else None
    )

    latencia_ms = (time.perf_counter() - inicio) * 1000

    return {
        "arquitectura": "2. Ingesta Asincrona Desacoplada (Event-Driven / Kappa)",
        "encontrado": persona is not None,
        "nombre": persona.nombre_completo if persona else None,
        "latencia_interna_ms": round(latencia_ms, 2)
    }
