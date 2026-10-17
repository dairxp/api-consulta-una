from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Padron, Elector, MiembroMesa, LogConsulta
from app.schemas import ElectorResponse, MiembroMesaInfo
from app.limiter import limiter

router = APIRouter(
    prefix="/api/v1/consulta",
    tags=["Consulta"]
)

#   Mapas por local de votación
#   Aplica tanto para local_votacion como para local_mesa

MAPAS_LOCALES: dict[str, str] = {
    "CEPREUNA": "https://www.google.com/maps/search/?api=1&query=CEPREUNA,+Jr.+Acora+235,+Puno,+Peru",
    "EDIFICIO ADMINISTRATIVO": "https://www.google.com/maps/search/?api=1&query=Edificio+Universitario+UNAP,+Av.+Ejercito+355,+Puno,+Peru",
    "CIENCIAS JURÍDICAS": "https://www.google.com/maps/search/?api=1&query=Facultad+de+Ciencias+Juridicas+y+Politicas+UNAP,+Pasaje+Grau+con+Jr.+Conde+de+Lemos,+Puno,+Peru",
    "INSTITUTO DE IDIOMAS": "https://www.google.com/maps/search/?api=1&query=Instituto+de+Idiomas+UNAP,+Jr.+Lima+317,+Puno,+Peru",
    "INGENIERÍA ECONÓMICA": "https://www.google.com/maps/search/?api=1&query=-15.8369976,-70.0291897",
    "EDUCACION CONTINUA": "https://www.google.com/maps/search/?api=1&query=Educacion+Continua+UNAP,+Av.+El+Sol+329,+Puno,+Peru"
}


def get_link_mapa(local: str | None) -> str | None:
    """Busca el link de mapa para un local dado (búsqueda parcial)."""
    if not local:
        return None
    local_upper = local.upper()
    for key, url in MAPAS_LOCALES.items():
        if key in local_upper:
            return url
    return None


def registrar_log_bd(
    documento: str,
    tipo_busqueda: str,
    ip_cliente: str,
    fue_encontrado: bool,
    tipo_persona: str | None,
    es_miembro_mesa: bool
):
    """Guarda un registro de la consulta en segundo plano sin bloquear la respuesta."""
    db: Session = SessionLocal()
    try:
        nuevo_log = LogConsulta(
            documento=documento,
            tipo_busqueda=tipo_busqueda,
            ip_cliente=ip_cliente,
            fue_encontrado=fue_encontrado,
            tipo_persona=tipo_persona,
            es_miembro_mesa=es_miembro_mesa
        )
        db.add(nuevo_log)
        db.commit()
    except Exception as e:
        print(f"Error al registrar log: {e}")
    finally:
        db.close()


#   Endpoint principal: GET /api/v1/consulta/{identificador}
#   Acepta DNI (8 dígitos numéricos) o CÓDIGO universitario.
#
#   Códigos de respuesta:
#     200  → encontrado, datos completos
#     404  → no existe en el padrón
#     409  → código universitario ambiguo (múltiples personas con ese código)
#            → el usuario debe buscar por DNI

from slowapi.util import get_remote_address

@router.get(
    "/{identificador}",
    response_model=ElectorResponse,
    summary="Consultar elector por DNI o Código",
    description=(
        "Devuelve los datos electorales de una persona buscando por DNI o código universitario. "
        "Incluye mesa de votación, local, y si es miembro de mesa (con su cargo y local asignado)."
    )
)
@limiter.shared_limit("30/minute", scope="global_consulta")
def consultar(
    identificador: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    # ── 1. Búsqueda Híbrida Inteligente ───────────────────────────────────
    # Buscamos en ambas columnas a la vez. 
    # Esto soluciona el problema de los DNIs con letras (pasaportes, carnets)
    # sin tener que adivinar si el texto es un código o un DNI.
    candidatos = db.query(Padron).filter(
        (Padron.dni == identificador) |
        (Padron.codigo == identificador)
    ).all()
    
    ip_cliente = request.client.host if request.client else "unknown"

    persona: Padron | None = None
    tipo_busqueda = "INDEFINIDO"

    if len(candidatos) > 1:
        # Conflicto: Hay más de un registro con este texto.
        # Caso raro: ¿Y si este texto es exactamente el DNI de uno de ellos?
        # El DNI manda. Si uno de los candidatos tiene esto como DNI, es el ganador.
        candidatos_dni = [c for c in candidatos if c.dni == identificador]
        
        if len(candidatos_dni) == 1:
            persona = candidatos_dni[0]
            tipo_busqueda = "DNI"
        else:
            # Si ninguno lo tiene como DNI, entonces ambos lo tienen como código (error de la BD).
            tipo_busqueda = "CODIGO"
            registrar_log_bd(
                documento=identificador,
                tipo_busqueda=tipo_busqueda,
                ip_cliente=ip_cliente,
                fue_encontrado=True,
                tipo_persona=None,
                es_miembro_mesa=False
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    "Este código universitario corresponde a más de un registro. "
                    "Por favor, ingresa tu DNI para consultar tu local de votación."
                )
            )
    elif len(candidatos) == 1:
        persona = candidatos[0]
        # Para el log, determinamos cómo lo encontró
        tipo_busqueda = "DNI" if persona.dni == identificador else "CODIGO"

    # ── Persona no encontrada ─────────────────────────────────────────────
    if persona is None:
        # Guardamos el log síncronamente porque 'raise HTTPException' cancela los BackgroundTasks
        registrar_log_bd(
            documento=identificador,
            tipo_busqueda=tipo_busqueda,
            ip_cliente=ip_cliente,
            fue_encontrado=False,
            tipo_persona=None,
            es_miembro_mesa=False
        )
        raise HTTPException(
            status_code=404,
            detail="Persona no encontrada en el padrón electoral"
        )

    # ── 2. Datos de votación ──────────────────────────────────────────────
    elector: Elector | None = (
        db.query(Elector)
        .filter(Elector.dni == persona.dni)
        .first()
    )

    # ── 3. Verificar si es miembro de mesa ────────────────────────────────
    miembros: list[MiembroMesa] = (
        db.query(MiembroMesa)
        .filter(MiembroMesa.dni_miembro == persona.dni)
        .all()
    )

    # ── 4. Construir lista de cargos ──────────────────────────────────────
    miembros_info: list[MiembroMesaInfo] = [
        MiembroMesaInfo(
            cargo=m.cargo,
            miembro=m.miembro,
            numero_mesa=m.numero_mesa,
            local_mesa=m.local_mesa,
            facultad_mesa=m.facultad_mesa,
            categoria=m.categoria,
            link_mapa_mesa=get_link_mapa(m.local_mesa)
        )
        for m in miembros
    ]

    es_miembro_mesa = len(miembros_info) > 0

    # Registrar log en background
    background_tasks.add_task(
        registrar_log_bd,
        documento=identificador,
        tipo_busqueda=tipo_busqueda,
        ip_cliente=ip_cliente,
        fue_encontrado=True,
        tipo_persona=persona.tipo,
        es_miembro_mesa=es_miembro_mesa
    )

    # ── 5. Armar respuesta ────────────────────────────────────────────────
    return ElectorResponse(
        # Identidad
        dni=persona.dni,
        codigo=persona.codigo,
        nombre_completo=persona.nombre_completo,
        tipo=persona.tipo or "",
        facultad=persona.facultad,
        escuela_profesional=persona.escuela_profesional,

        # Votación
        mesa=elector.mesa if elector else None,
        posicion=elector.posicion if elector else None,
        local_votacion=elector.local_votacion if elector else None,
        link_mapa=get_link_mapa(elector.local_votacion) if elector else None,

        # Miembro de mesa
        es_miembro_mesa=es_miembro_mesa,
        miembro_mesa=miembros_info,
    )