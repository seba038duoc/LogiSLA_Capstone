import type { Conteos } from "@/lib/api";
import { entero } from "@/lib/formato";

/**
 * La franja de cumplimiento es EL elemento visual de LogiSLA: una barra
 * que muestra de un vistazo cómo se reparte un conjunto de guías.
 * Se usa igual en el listado de lotes, en el detalle y por transportista,
 * siempre con los mismos colores y el mismo orden.
 */

export const CATEGORIAS = [
  { clave: "cumplidos", clase: "seg-cumplido", nombre: "En plazo" },
  { clave: "incumplidos", clase: "seg-incumplido", nombre: "Fuera de plazo" },
  { clave: "en_transito", clase: "seg-transito", nombre: "En tránsito" },
  { clave: "sin_regla", clase: "seg-sin-regla", nombre: "Sin regla SLA" },
  { clave: "pendientes", clase: "seg-pendiente", nombre: "Sin auditar" },
] as const;

function descripcion(conteos: Conteos): string {
  const partes = CATEGORIAS.filter((c) => conteos[c.clave] > 0).map(
    (c) => `${entero(conteos[c.clave])} ${c.nombre.toLowerCase()}`
  );
  return partes.length ? partes.join(", ") : "Sin guías";
}

export function FranjaCumplimiento({
  conteos,
  alto = "h-2.5",
  className = "",
}: {
  conteos: Conteos;
  alto?: string;
  className?: string;
}) {
  const segmentos = CATEGORIAS.filter((c) => conteos[c.clave] > 0);
  return (
    <div
      role="img"
      aria-label={descripcion(conteos)}
      title={descripcion(conteos)}
      className={`flex w-full gap-px overflow-hidden rounded-xs ${alto} ${className}`}
    >
      {segmentos.length === 0 ? (
        <div className="seg-pendiente flex-1" />
      ) : (
        segmentos.map((c) => (
          <div
            key={c.clave}
            className={c.clase}
            style={{ flexGrow: conteos[c.clave], flexBasis: 0, minWidth: 4 }}
          />
        ))
      )}
    </div>
  );
}

/** Leyenda con la cantidad de guías de cada categoría presente. */
export function LeyendaFranja({ conteos }: { conteos: Conteos }) {
  return (
    <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
      {CATEGORIAS.filter((c) => conteos[c.clave] > 0).map((c) => (
        <li key={c.clave} className="flex items-center gap-2">
          <span aria-hidden="true" className={`inline-block h-3 w-3 rounded-xs ${c.clase}`} />
          <span className="cifras font-semibold">{entero(conteos[c.clave])}</span>
          <span className="text-tinta-suave">{c.nombre.toLowerCase()}</span>
        </li>
      ))}
    </ul>
  );
}
