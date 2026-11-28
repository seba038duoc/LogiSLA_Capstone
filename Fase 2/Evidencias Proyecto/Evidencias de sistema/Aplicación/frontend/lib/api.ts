/**
 * Cliente delgado para el backend de LogiSLA.
 *
 * Endpoints que consume (ver backend/app/routers/):
 *   GET  /api/v1/empresas
 *   GET  /api/v1/lotes-auditoria?empresa_id=...
 *   POST /api/v1/lotes-auditoria/cargar?empresa_id=...
 *   GET  /api/v1/lotes-auditoria/{lote_id}/resumen
 *   GET  /api/v1/lotes-auditoria/{lote_id}/envios
 *   POST /api/v1/lotes-auditoria/{lote_id}/auditar
 *   POST /api/v1/lotes-auditoria/{lote_id}/carta?transportista=...  (IA generativa)
 *   POST /api/v1/lotes-auditoria/{lote_id}/resumen-ejecutivo  (IA generativa)
 */

/** Dirección del backend (la escribe iniciar.bat en .env.local; por defecto, el puerto 8000). */
const URL_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/* ------------------------------- Tipos -------------------------------- */

export type Empresa = { id: string; nombre: string; rut: string | null };

export type EstadoLote = "PENDIENTE" | "PROCESANDO" | "COMPLETADO" | "FALLIDO";

/** Cada guía cae en exactamente una categoría; la suma da `total`. */
export type Conteos = {
  total: number;
  /** Entregadas dentro del plazo. */
  cumplidos: number;
  /** Entregadas fuera del plazo (llevan multa). */
  incumplidos: number;
  /** Sin entrega, pero su plazo aún no vence. */
  en_transito: number;
  /** Sin entrega y con el plazo vencido a la fecha de corte (alerta, sin multa). */
  vencidas_sin_entrega: number;
  /** Su transportista no tiene regla SLA activa. */
  sin_regla: number;
  /** Sus datos no permiten auditarlas (entrega antes del despacho, repetidas, etc.). */
  datos_invalidos: number;
  /** El lote todavía no se audita. */
  pendientes: number;
  monto_multa_total: number;
};

export type LoteResumen = {
  id: string;
  nombre_archivo: string;
  estado: EstadoLote;
  total_filas: number;
  fecha_creacion: string;
  fecha_procesado: string | null;
  /** Momento (hora de Chile) en que se auditó: contra él se evalúan las guías sin entrega. */
  fecha_corte: string | null;
  conteos: Conteos;
};

export type FilaTransportista = {
  nombre: string;
  horas_habiles_maximas: number | null;
  multa_por_incumplimiento: number | null;
  conteos: Conteos;
};

/** Feriado chileno que no se contó como día hábil. */
export type Feriado = { fecha: string; nombre: string };

/** Metodología con que se auditó el lote. */
export type CriteriosAuditoria = {
  jornada: string;
  calendario: string;
  despacho_desde: string | null;
  despacho_hasta: string | null;
  feriados: Feriado[];
  reglas: string[];
};

export type LoteDetalle = LoteResumen & {
  empresa_nombre: string;
  empresa_rut: string | null;
  por_transportista: FilaTransportista[];
  criterios: CriteriosAuditoria;
};

export type ResultadoEnvio =
  | "CUMPLIDO"
  | "INCUMPLIDO"
  | "EN_TRANSITO"
  | "VENCIDA_SIN_ENTREGA"
  | "SIN_REGLA"
  | "DATOS_INVALIDOS"
  | "PENDIENTE";

export type Envio = {
  id: string;
  numero_guia: string;
  transportista: string | null;
  fecha_despacho: string;
  fecha_entrega: string | null;
  destino: string | null;
  valor_declarado: number | null;
  resultado: ResultadoEnvio;
  horas_atraso: number | null;
  monto_multa: number | null;
  /* Justificación de la auditoría de esta guía */
  /** True si el archivo trae fecha de entrega (la encomienda llegó). */
  entregada: boolean;
  /** Cuándo vencía el plazo SLA. */
  fecha_limite: string | null;
  horas_habiles_permitidas: number | null;
  /** Horas hábiles hasta la entrega o, si no hay entrega, hasta la fecha de corte. */
  horas_habiles_transcurridas: number | null;
  dias_fin_de_semana: number;
  feriados: Feriado[];
  /** Explicación en palabras del resultado. */
  justificacion: string;
};

export type RespuestaCarga = {
  lote_id: string;
  nombre_archivo: string;
  estado: string;
  total_filas: number;
  mapeo_columnas: Record<string, string>;
  advertencias_ambiguas: Record<string, string[]>;
  mensaje: string;
};

export type ResultadoAuditoria = {
  lote_id: string;
  estado: string;
  total_envios: number;
  envios_auditados: number;
  envios_incumplidos: number;
  envios_cumplidos: number;
  omitidos_sin_regla: number;
  omitidos_sin_fecha_entrega: number;
  vencidas_sin_entrega: number;
  datos_invalidos: number;
  monto_multa_total: number;
  fecha_corte: string | null;
  mensaje: string;
};

/** Carta de reclamo. `origen` dice si el cuerpo lo redactó la IA o salió de la plantilla. */
export type CartaReclamo = {
  lote_id: string;
  transportista: string;
  origen: "IA" | "PLANTILLA";
  /** "Gemini" o "Claude": qué IA la redactó (si origen es "IA"). */
  proveedor: string | null;
  modelo: string | null;
  motivo_plantilla: string | null;
  /** Por qué no redactó la IA principal, si redactó la de respaldo. */
  aviso_respaldo: string | null;
  guias_incumplidas: number;
  monto_total: number;
  texto: string;
};

/** Resumen ejecutivo del lote (HU-17). */
export type ResumenEjecutivo = {
  lote_id: string;
  origen: "IA" | "PLANTILLA";
  /** "Gemini" o "Claude": qué IA la redactó (si origen es "IA"). */
  proveedor: string | null;
  modelo: string | null;
  motivo_plantilla: string | null;
  /** Por qué no redactó la IA principal, si redactó la de respaldo. */
  aviso_respaldo: string | null;
  texto: string;
};

/* ------------------------------ Errores ------------------------------- */

/**
 * `estado` es el código HTTP; 0 significa que ni siquiera hubo respuesta
 * (backend apagado, sin red o bloqueado por CORS).
 */
export class ErrorApi extends Error {
  estado: number;
  constructor(estado: number, mensaje: string) {
    super(mensaje);
    this.name = "ErrorApi";
    this.estado = estado;
  }
}

/** Convierte cualquier error en un texto que se pueda mostrar tal cual. */
export function mensajeDeError(error: unknown): string {
  if (error instanceof ErrorApi) return error.message;
  if (error instanceof Error) return error.message;
  return String(error);
}

/** Extrae el mensaje de error que envía FastAPI (texto o lista de errores de validación). */
function detalleLegible(cuerpo: unknown, porDefecto: string): string {
  if (cuerpo && typeof cuerpo === "object" && "detail" in cuerpo) {
    const detalle = (cuerpo as { detail: unknown }).detail;
    if (typeof detalle === "string") return detalle;
    // Errores de validación de FastAPI (422): lista de {loc, msg}
    if (Array.isArray(detalle)) {
      return detalle
        .map((d) =>
          d && typeof d === "object" && "msg" in d
            ? String((d as { msg: unknown }).msg)
            : String(d),
        )
        .join(". ");
    }
  }
  return porDefecto;
}

/**
 * Llamada genérica al backend: hace la petición, convierte los errores de
 * red o de la API en ErrorApi con un mensaje entendible y devuelve el JSON.
 */
async function pedir<T>(ruta: string, opciones?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${URL_API}${ruta}`, opciones);
  } catch {
    throw new ErrorApi(
      0,
      `No hay conexión con el servidor de LogiSLA (${URL_API}). ` +
        "Revisa que el backend esté encendido y vuelve a intentarlo.",
    );
  }

  if (!response.ok) {
    let cuerpo: unknown = null;
    try {
      cuerpo = await response.json();
    } catch {
      // el cuerpo no era JSON; usamos el texto de estado
    }
    throw new ErrorApi(
      response.status,
      detalleLegible(cuerpo, response.statusText || `Error ${response.status}`),
    );
  }
  return response.json() as Promise<T>;
}

/* ----------------------------- Endpoints ------------------------------ */

/** GET /api/v1/empresas: empresas disponibles. */
export function listarEmpresas(): Promise<Empresa[]> {
  return pedir("/api/v1/empresas");
}

/** GET /api/v1/lotes-auditoria?empresa_id=...: lotes de una empresa. */
export function listarLotes(idEmpresa: string): Promise<LoteResumen[]> {
  return pedir(`/api/v1/lotes-auditoria?empresa_id=${encodeURIComponent(idEmpresa)}`);
}

/** GET /api/v1/lotes-auditoria/{id}/resumen: detalle y conteos de un lote. */
export function obtenerDetalleLote(idLote: string): Promise<LoteDetalle> {
  return pedir(`/api/v1/lotes-auditoria/${encodeURIComponent(idLote)}/resumen`);
}

/** GET /api/v1/lotes-auditoria/{id}/envios: guías del lote con su resultado. */
export function listarEnvios(idLote: string): Promise<Envio[]> {
  return pedir(`/api/v1/lotes-auditoria/${encodeURIComponent(idLote)}/envios`);
}

/** POST /api/v1/lotes-auditoria/{id}/auditar: ejecuta el motor de auditoría. */
export function auditarLote(idLote: string): Promise<ResultadoAuditoria> {
  return pedir(`/api/v1/lotes-auditoria/${encodeURIComponent(idLote)}/auditar`, { method: "POST" });
}

/** POST /api/v1/lotes-auditoria/cargar: sube el archivo CSV o Excel. */
export function cargarLoteAuditoria(idEmpresa: string, archivo: File): Promise<RespuestaCarga> {
  const datosFormulario = new FormData();
  datosFormulario.append("file", archivo);
  return pedir(`/api/v1/lotes-auditoria/cargar?empresa_id=${encodeURIComponent(idEmpresa)}`, {
    method: "POST",
    body: datosFormulario,
  });
}

/** POST /api/v1/lotes-auditoria/{id}/carta: carta de reclamo para un transportista. */
export function generarCartaReclamo(idLote: string, transportista: string): Promise<CartaReclamo> {
  const parametros = new URLSearchParams({ transportista });
  return pedir(`/api/v1/lotes-auditoria/${encodeURIComponent(idLote)}/carta?${parametros}`, {
    method: "POST",
  });
}

/** POST /api/v1/lotes-auditoria/{id}/resumen-ejecutivo: resumen del lote para la gerencia. */
export function generarResumenEjecutivo(idLote: string): Promise<ResumenEjecutivo> {
  return pedir(`/api/v1/lotes-auditoria/${encodeURIComponent(idLote)}/resumen-ejecutivo`, {
    method: "POST",
  });
}
