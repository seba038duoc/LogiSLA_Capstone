import type { CriteriosAuditoria as Criterios } from "@/lib/api";
import { fechaHoraLocal } from "@/lib/formato";

/**
 * Sección "Criterios de la auditoría": la metodología con que se calcularon
 * los resultados del lote (jornada hábil, feriados, fecha de corte y reglas
 * de clasificación). Se muestra en el detalle del lote y en el informe
 * imprimible, para que cada cifra se pueda justificar.
 */
export function CriteriosAuditoria({
  criterios,
  fechaCorte,
  idTitulo = "titulo-criterios",
  titulo = "Criterios de la auditoría",
}: {
  criterios: Criterios;
  fechaCorte: string | null;
  idTitulo?: string;
  titulo?: string;
}) {
  const periodo =
    criterios.despacho_desde && criterios.despacho_hasta
      ? `${fechaHoraLocal(criterios.despacho_desde)} a ${fechaHoraLocal(criterios.despacho_hasta)}`
      : "Sin guías";

  return (
    <section aria-labelledby={idTitulo} className="mt-12 print:mt-6">
      <h2 id={idTitulo} className="text-lg font-semibold break-after-avoid">
        {titulo}
      </h2>
      <div className="mt-4 rounded-lg border border-linea bg-superficie p-5 text-sm">
        <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
          <Dato termino="Fecha de corte">
            {fechaCorte ? fechaHoraLocal(fechaCorte) : "El lote aún no se audita"}
          </Dato>
          <Dato termino="Despachos del archivo">{periodo}</Dato>
          <Dato termino="Jornada hábil">{criterios.jornada}</Dato>
          <Dato termino="Calendario">{criterios.calendario}</Dato>
          <Dato termino="Feriados en el período (no se contaron)">
            {criterios.feriados.length === 0
              ? "Ninguno"
              : criterios.feriados.map((f) => `${fechaCorta(f.fecha)} ${f.nombre}`).join(" · ")}
          </Dato>
        </dl>
        <h3 className="mt-5 font-semibold">Cómo se clasificó cada guía</h3>
        <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-tinta-suave">
          {criterios.reglas.map((regla) => (
            <li key={regla}>{regla}</li>
          ))}
        </ol>
      </div>
    </section>
  );
}

/** Un par "término: valor" de la lista de criterios. */
function Dato({ termino, children }: { termino: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-tinta-suave">{termino}</dt>
      <dd className="cifras mt-0.5 font-medium">{children}</dd>
    </div>
  );
}

/** Fecha "aaaa-mm-dd" en formato "dd-mm-aaaa", sin pasar por zonas horarias. */
export function fechaCorta(iso: string): string {
  const [anio, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}-${mes}-${anio}`;
}
