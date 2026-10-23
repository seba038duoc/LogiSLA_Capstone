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
 */

const URL_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/* ------------------------------- Tipos -------------------------------- */

export type Empresa = { id: string; nombre: string; rut: string | null };

export type EstadoLote = "PENDIENTE" | "PROCESANDO" | "COMPLETADO" | "FALLIDO";

/** Cada guía cae en exactamente una categoría; la suma da `total`. */
export type Conteos = {
  total: number;
  cumplidos: number;
  incumplidos: number;
  en_transito: number;
  sin_regla: number;
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
  conteos: Conteos;
};

export type FilaTransportista = {
  nombre: string;
  horas_habiles_maximas: number | null;
  multa_por_incumplimiento: number | null;
  conteos: Conteos;
};

export type LoteDetalle = LoteResumen & { por_transportista: FilaTransportista[] };

export type ResultadoEnvio = "CUMPLIDO" | "INCUMPLIDO" | "EN_TRANSITO" | "SIN_REGLA" | "PENDIENTE";

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
  monto_multa_total: number;
  mensaje: string;
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

function detalleLegible(cuerpo: unknown, porDefecto: string): string {
  if (cuerpo && typeof cuerpo === "object" && "detail" in cuerpo) {
    const detalle = (cuerpo as { detail: unknown }).detail;
    if (typeof detalle === "string") return detalle;
    // Errores de validación de FastAPI (422): lista de {loc, msg}
    if (Array.isArray(detalle)) {
      return detalle
        .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
        .join(". ");
    }
  }
  return porDefecto;
}

async function pedir<T>(ruta: string, opciones?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${URL_API}${ruta}`, opciones);
  } catch {
    throw new ErrorApi(
      0,
      `No hay conexión con el servidor de LogiSLA (${URL_API}). Revisa que el backend esté encendido y vuelve a intentarlo.`
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
      detalleLegible(cuerpo, response.statusText || `Error ${response.status}`)
    );
  }
  return response.json() as Promise<T>;
}

/* ----------------------------- Endpoints ------------------------------ */

export function listarEmpresas(): Promise<Empresa[]> {
  return pedir("/api/v1/empresas");
}

export function listarLotes(idEmpresa: string): Promise<LoteResumen[]> {
  return pedir(`/api/v1/lotes-auditoria?empresa_id=${encodeURIComponent(idEmpresa)}`);
}

export function obtenerDetalleLote(idLote: string): Promise<LoteDetalle> {
  return pedir(`/api/v1/lotes-auditoria/${encodeURIComponent(idLote)}/resumen`);
}

export function listarEnvios(idLote: string): Promise<Envio[]> {
  return pedir(`/api/v1/lotes-auditoria/${encodeURIComponent(idLote)}/envios`);
}

export function auditarLote(idLote: string): Promise<ResultadoAuditoria> {
  return pedir(`/api/v1/lotes-auditoria/${encodeURIComponent(idLote)}/auditar`, { method: "POST" });
}

export function cargarLoteAuditoria(idEmpresa: string, archivo: File): Promise<RespuestaCarga> {
  const datosFormulario = new FormData();
  datosFormulario.append("file", archivo);
  return pedir(`/api/v1/lotes-auditoria/cargar?empresa_id=${encodeURIComponent(idEmpresa)}`, {
    method: "POST",
    body: datosFormulario,
  });
}
