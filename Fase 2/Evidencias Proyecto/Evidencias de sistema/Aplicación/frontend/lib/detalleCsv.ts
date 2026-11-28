import type { Envio, LoteDetalle } from "@/lib/api";
import { type Celda, descargarCsv } from "@/lib/csv";
import { fechaHoraCorta } from "@/lib/formato";
import { nombreResultado } from "@/components/ui";

/**
 * Descarga el detalle completo de la auditoría de un lote en CSV: una fila
 * por guía con su resultado, fecha límite, horas hábiles, atraso, multa y la
 * justificación en palabras. Sirve como respaldo del informe de auditoría.
 */
export function descargarDetalleAuditoria(lote: LoteDetalle, envios: Envio[]): void {
  const base = lote.nombre_archivo.replace(/\.[^.]+$/, "");
  descargarCsv(`auditoria_${base}.csv`, filasDetalleAuditoria(envios));
}

/** Filas del CSV de detalle: encabezados y una fila por guía. */
export function filasDetalleAuditoria(envios: Envio[]): Celda[][] {
  return [
    [
      "N° guía",
      "Transportista",
      "Destino",
      "Fecha despacho",
      "¿Llegó?",
      "Fecha entrega",
      "Fecha límite",
      "Horas hábiles permitidas",
      "Horas hábiles transcurridas",
      "Horas hábiles de atraso",
      "Resultado",
      "Multa (CLP)",
      "Justificación",
    ],
    ...envios.map((e) => [
      e.numero_guia,
      e.transportista ?? "",
      e.destino ?? "",
      fechaHoraCorta(e.fecha_despacho),
      e.entregada ? "Sí" : "No",
      fechaHoraCorta(e.fecha_entrega),
      fechaHoraCorta(e.fecha_limite),
      e.horas_habiles_permitidas ?? "",
      e.horas_habiles_transcurridas ?? "",
      e.horas_atraso ?? "",
      nombreResultado(e.resultado),
      e.monto_multa ?? "",
      e.justificacion,
    ]),
  ];
}
