from pydantic import BaseModel


class MiembroMesaInfo(BaseModel):
    """Datos del cargo como miembro de mesa."""
    cargo:         str | None = None   # PRESIDENTE | SECRETARIO | etc.
    miembro:       str | None = None   # TITULAR | SUPLENTE
    numero_mesa:   str | None = None
    local_mesa:    str | None = None
    facultad_mesa: str | None = None
    categoria:     str | None = None   # DOCENTE ASOCIADO | ESTUDIANTE | etc.
    link_mapa_mesa: str | None = None

    model_config = {"from_attributes": True}


class ElectorResponse(BaseModel):
    """
    Respuesta completa al consultar por DNI o código.
    Incluye datos de votación y, si aplica, datos como miembro de mesa.
    """
    # Identidad
    dni:                 str
    codigo:              str | None = None
    nombre_completo:     str
    tipo:                str
    facultad:            str | None = None
    escuela_profesional: str | None = None

    # Dónde vota (mesa como str para compatibilidad con VARCHAR en BD)
    mesa:           str | None = None
    posicion:       int | None = None
    local_votacion: str | None = None
    link_mapa:      str | None = None

    # Si es miembro de mesa
    es_miembro_mesa: bool = False
    miembro_mesa:    list[MiembroMesaInfo] = []

    model_config = {"from_attributes": True}