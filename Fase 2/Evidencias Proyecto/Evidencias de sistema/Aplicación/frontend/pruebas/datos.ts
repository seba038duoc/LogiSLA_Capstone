/**
 * Datos de ejemplo para las pruebas del frontend: una guía y una fila de
 * transportista con valores razonables, que cada prueba ajusta a su caso.
 */
import type { Envio, FilaTransportista } from "@/lib/api";

/** Una guía de ejemplo (entregada fuera de plazo); `cambios` reemplaza campos. */
export function guia(cambios: Partial<Envio> = {}): Envio {
  return {
    id: cambios.numero_guia ?? "id-1",
    numero_guia: "LSA-202600011",
    transportista: "Starken",
    fecha_despacho: "2026-09-18T11:30:00",
    fecha_entrega: "2026-09-30T18:00:00",
    destino: "La Serena",
    valor_declarado: 50000,
    resultado: "INCUMPLIDO",
    horas_atraso: 12,
    monto_multa: 12000,
    entregada: true,
    fecha_limite: "2026-09-29T15:00:00",
    horas_habiles_permitidas: 60,
    horas_habiles_transcurridas: 72,
    dias_fin_de_semana: 4,
    feriados: [{ fecha: "2026-09-18", nombre: "Fiestas Patrias" }],
    justificacion: "Entregada el 30-09-2026 18:00, después de la fecha límite (29-09-2026 15:00).",
    ...cambios,
  };
}

/** Una fila de "Por transportista" de ejemplo; `cambios` reemplaza campos. */
export function fila(
  nombre: string,
  incumplidos: number,
  multa: number,
  monto: number,
): FilaTransportista {
  return {
    nombre,
    horas_habiles_maximas: 48,
    multa_por_incumplimiento: multa,
    conteos: {
      total: incumplidos + 5,
      cumplidos: 5,
      incumplidos,
      en_transito: 0,
      vencidas_sin_entrega: 0,
      sin_regla: 0,
      datos_invalidos: 0,
      pendientes: 0,
      monto_multa_total: monto,
    },
  };
}
