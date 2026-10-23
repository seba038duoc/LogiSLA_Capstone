/** Formateo de cifras y fechas para Chile (es-CL), en un solo lugar. */

import type { Conteos } from "@/lib/api";

const fmtPesos = new Intl.NumberFormat("es-CL", {
  style: "currency",
  currency: "CLP",
  maximumFractionDigits: 0,
});
const fmtEntero = new Intl.NumberFormat("es-CL");
const fmtHoras = new Intl.NumberFormat("es-CL", { maximumFractionDigits: 1 });
const fmtFecha = new Intl.DateTimeFormat("es-CL", { day: "2-digit", month: "short", year: "numeric" });
const fmtFechaHora = new Intl.DateTimeFormat("es-CL", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function pesos(monto: number | null | undefined): string {
  return monto == null ? "" : fmtPesos.format(monto);
}

export function entero(n: number): string {
  return fmtEntero.format(n);
}

export function horas(n: number | null | undefined): string {
  return n == null ? "" : `${fmtHoras.format(n)} h`;
}

/** "1 guía" / "60 guías" */
export function guias(n: number): string {
  return `${entero(n)} ${n === 1 ? "guía" : "guías"}`;
}

/**
 * Fechas del archivo (despacho, entrega): vienen sin zona horaria y son
 * hora local de quien armó la planilla, así que se muestran tal cual.
 */
export function fechaHoraLocal(iso: string | null | undefined): string {
  if (!iso) return "";
  const fecha = new Date(iso);
  return Number.isNaN(fecha.getTime()) ? iso : fmtFechaHora.format(fecha);
}

/**
 * Fechas que genera el sistema (creación del lote, auditoría): el backend
 * las guarda en UTC. Con SQLite llegan sin sufijo de zona, y el navegador
 * las tomaría como hora local (quedarían corridas 3-4 horas), así que si
 * no traen zona se les agrega la "Z".
 */
function comoUtc(iso: string): Date {
  const tieneZona = /(Z|[+-]\d{2}:?\d{2})$/i.test(iso);
  return new Date(tieneZona ? iso : `${iso}Z`);
}

export function fechaSistema(iso: string | null | undefined, conHora = true): string {
  if (!iso) return "";
  const fecha = comoUtc(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  return (conHora ? fmtFechaHora : fmtFecha).format(fecha);
}

/**
 * % de cumplimiento sobre las guías que sí se pudieron auditar
 * (cumplidas + incumplidas). null si todavía no hay ninguna auditada.
 */
export function porcentajeCumplimiento(c: Conteos): number | null {
  const auditadas = c.cumplidos + c.incumplidos;
  return auditadas === 0 ? null : (c.cumplidos / auditadas) * 100;
}

export function porcentaje(valor: number | null): string {
  if (valor == null) return "";
  // 99,6 % no debe redondearse a "100 %" si hubo incumplimientos
  const redondeado = valor > 99 && valor < 100 ? Math.floor(valor * 10) / 10 : Math.round(valor);
  return `${fmtHoras.format(redondeado)} %`;
}
