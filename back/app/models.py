from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class Padron(Base):
    """
    Tabla maestra con toda la comunidad UNAP.
    PK = dni (identificador real único de la persona).
    codigo = código universitario, indexado pero NO único
             (la fuente puede tener 9 casos de código duplicado).
    """
    __tablename__ = "padron"

    dni         = Column(String(20), primary_key=True)
    codigo      = Column(String(20), index=True)          # indexado, no unique
    ap_paterno  = Column(String(100))
    ap_materno  = Column(String(100))
    nombres     = Column(String(150))
    tipo        = Column(String(50))      # "ESTUDIANTE DE PREGRADO" | "DOCENTE" | etc.
    fac_cod              = Column(String(10))
    facultad             = Column(String(300))
    esc_cod              = Column(String(10))
    escuela_profesional  = Column(String(300))

    # Relaciones
    elector     = relationship("Elector",     back_populates="padron", uselist=False)
    miembros    = relationship("MiembroMesa", back_populates="padron")

    @property
    def nombre_completo(self) -> str:
        """Construye: APELLIDO1 APELLIDO2, NOMBRES"""
        apellidos = f"{self.ap_paterno or ''} {self.ap_materno or ''}".strip()
        nombres   = (self.nombres or "").strip()
        if apellidos and nombres:
            return f"{apellidos}, {nombres}"
        return apellidos or nombres


class Elector(Base):
    """
    Electores con mesa y local de votación asignados.
    FK → padron.dni  (el DNI es el ancla real).
    mesa se guarda como VARCHAR porque el Excel lo trae como texto.
    """
    __tablename__ = "electores"

    dni             = Column(
        String(20),
        ForeignKey("padron.dni", ondelete="CASCADE"),
        primary_key=True
    )
    mesa            = Column(String(10))
    posicion        = Column(Integer)
    local_votacion  = Column(String(300))

    # Relación
    padron = relationship("Padron", back_populates="elector")


class MiembroMesa(Base):
    """
    Personas asignadas como miembros de mesa.
    FK → padron.dni.
    local_mesa    = ubicación física del pabellón (LOCAL_PABELLON).
    facultad_mesa = facultad dueña de la mesa  (LOCAL DE LA MESA FACULTAD).
    Sin columna dia: elección de un solo día.
    """
    __tablename__ = "miembros_mesa"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    dni_miembro   = Column(
        String(20),
        ForeignKey("padron.dni", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    numero_mesa   = Column(String(10), nullable=False)
    local_mesa    = Column(String(300))
    facultad_mesa = Column(String(300))
    cargo         = Column(String(60))    # PRESIDENTE | SECRETARIO | etc.
    miembro       = Column(String(20))    # TITULAR | SUPLENTE
    categoria     = Column(String(100))   # DOCENTE ASOCIADO | ESTUDIANTE | etc.

    # Relación
    padron = relationship("Padron", back_populates="miembros")


from sqlalchemy import Boolean, DateTime
from sqlalchemy.sql import func

class LogConsulta(Base):
    """
    Tabla de auditoría para registrar cada consulta realizada al sistema.
    """
    __tablename__ = "log_consultas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    documento = Column(String(20), index=True)
    tipo_busqueda = Column(String(10))  # 'DNI' o 'CODIGO'
    fecha_hora = Column(DateTime(timezone=True), server_default=func.now())
    ip_cliente = Column(String(50))
    fue_encontrado = Column(Boolean)
    tipo_persona = Column(String(50), nullable=True)
    es_miembro_mesa = Column(Boolean, default=False)