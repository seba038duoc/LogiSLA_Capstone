import type { Envio } from "@/lib/api";
import { fechaHoraCorta, horas } from "@/lib/formato";
import { fechaCorta } from "@/components/CriteriosAuditoria";

/**
 * Detalle desplegable de una guía en la tabla de guías: la justificación en
 * palabras de su resultado y el desglose del cálculo (si llegó, fecha
 * límite, horas hábiles usadas y permitidas, días que no se contaron).
 */
export function DetalleGuia({ envio }: { envio: Envio }) {
  const auditada = envio.resultado !== "PENDIENTE";
  return (
    <div className="grid gap-4 text-sm md:grid-cols-[2fr_1fr]">
      <div>
        <p className="font-semibold">Justificación</p>
        <p className="mt-1 max-w-3xl leading-relaxed text-tinta-suave">{envio.justificacion}</p>
      </div>
      {auditada && (
        <dl className="cifras grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="text-tinta-suave">Destino</dt>
          <dd className="font-medium">{envio.destino || "Sin dato"}</dd>
          <dt className="text-tinta-suave">¿Llegó?</dt>
          <dd className="font-medium">
            {envio.entregada ? `Sí, ${fechaHoraCorta(envio.fecha_entrega)}` : "No registra entrega"}
          </dd>
          <dt className="text-tinta-suave">Fecha límite</dt>
          <dd className="font-medium">{fechaHoraCorta(envio.fecha_limite) || "No aplica"}</dd>
          <dt className="text-tinta-suave">Horas hábiles</dt>
          <dd className="font-medium">
            {envio.horas_habiles_transcurridas == null
              ? "No aplica"
              : `${horas(envio.horas_habiles_transcurridas)} de ${
                  envio.horas_habiles_permitidas ?? "?"
                } h permitidas`}
          </dd>
          <dt className="text-tinta-suave">No se contaron</dt>
          <dd className="font-medium">
            {envio.dias_fin_de_semana} día{envio.dias_fin_de_semana === 1 ? "" : "s"} de fin de
            semana
            {envio.feriados.length > 0 &&
              `, ${envio.feriados.map((f) => `${fechaCorta(f.fecha)} ${f.nombre}`).join(", ")}`}
          </dd>
        </dl>
      )}
    </div>
  );
}
