"""
Modelo relacional de LogiSLA (Sprint 1: Ingesta y Base Backend).

Tablas: empresas, transportistas, reglas_sla, envios, lotes_auditoria — las
mismas mencionadas en la Fundamentación del proyecto (Modelado de Datos).

Alcance del Sprint 1: dejar la estructura y la ingesta funcionando. Los
campos que calcula el motor de auditoría (Sprint 2: incumplio_sla,
horas_atraso, monto_multa) quedaban nulos hasta ese sprint — por eso son
nullable=True. El Sprint 2 ya los completa (ver app/audit_engine.py).
"""
import enum
import uuid

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey,
    Enum, JSON, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def generar_uuid():
    return str(uuid.uuid4())


class EstadoLote(str, enum.Enum):
    PENDIENTE = "PENDIENTE"    # archivo cargado, aún no auditado por el motor
    PROCESANDO = "PROCESANDO"  # reservado para procesamiento asíncrono futuro
    COMPLETADO = "COMPLETADO"  # el motor de auditoría ya corrió sobre el lote
    FALLIDO = "FALLIDO"        # reservado para errores de procesamiento


class Empresa(Base):
    __tablename__ = "empresas"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generar_uuid)
    nombre = Column(String(255), nullable=False)
    rut = Column(String(20), nullable=True, unique=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())

    lotes_auditoria = relationship("LoteAuditoria", back_populates="empresa")


class Transportista(Base):
    __tablename__ = "transportistas"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generar_uuid)
    nombre = Column(String(255), nullable=False, unique=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())

    reglas_sla = relationship("ReglaSLA", back_populates="transportista")
    envios = relationship("Envio", back_populates="transportista")


class ReglaSLA(Base):
    __tablename__ = "reglas_sla"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generar_uuid)
    transportista_id = Column(UUID(as_uuid=False), ForeignKey("transportistas.id"), nullable=False)
    tipo_servicio = Column(String(100), nullable=True)
    horas_habiles_maximas = Column(Integer, nullable=False)
    multa_por_incumplimiento = Column(Float, nullable=False)
    activa = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())

    transportista = relationship("Transportista", back_populates="reglas_sla")


class LoteAuditoria(Base):
    __tablename__ = "lotes_auditoria"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generar_uuid)
    empresa_id = Column(UUID(as_uuid=False), ForeignKey("empresas.id"), nullable=False)
    nombre_archivo = Column(String(500), nullable=False)
    estado = Column(Enum(EstadoLote), default=EstadoLote.PENDIENTE, nullable=False)
    total_filas = Column(Integer, nullable=False, default=0)
    mapeo_columnas = Column(JSON, nullable=True)
    advertencias_sin_mapear = Column(JSON, nullable=True)
    mensaje_error = Column(Text, nullable=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_procesado = Column(DateTime(timezone=True), nullable=True)

    empresa = relationship("Empresa", back_populates="lotes_auditoria")
    envios = relationship("Envio", back_populates="lote_auditoria", cascade="all, delete-orphan")


class Envio(Base):
    __tablename__ = "envios"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generar_uuid)
    lote_auditoria_id = Column(UUID(as_uuid=False), ForeignKey("lotes_auditoria.id"), nullable=False)
    transportista_id = Column(UUID(as_uuid=False), ForeignKey("transportistas.id"), nullable=True)
    nombre_transportista_original = Column(String(255), nullable=True)
    numero_guia = Column(String(100), nullable=False)
    fecha_despacho = Column(DateTime(timezone=True), nullable=False)
    fecha_entrega = Column(DateTime(timezone=True), nullable=True)
    destino = Column(String(255), nullable=True)
    valor_declarado = Column(Float, nullable=True)

    # Estos tres los calcula el motor de auditoría (Sprint 2), no la ingesta.
    incumplio_sla = Column(Boolean, nullable=True)
    horas_atraso = Column(Float, nullable=True)
    monto_multa = Column(Float, nullable=True)

    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())

    lote_auditoria = relationship("LoteAuditoria", back_populates="envios")
    transportista = relationship("Transportista", back_populates="envios")
