import type { Envio, FilaTransportista } from "@/lib/api";
import { guias, horas, pesos } from "@/lib/formato";
import { clases } from "@/lib/clases";

/**
 * Gráficos por transportista (HU-15): dos gráficos de barras horizontales,
 * uno con la multa por reclamar y otro con el atraso promedio de las guías
 * entregadas fuera de plazo (en horas hábiles). Responden de un vistazo
 * "¿quién nos debe más?" y "¿quién se atrasa más?".
 *
 * Se dibujan con HTML y CSS (sin bibliotecas de gráficos). Cada barra tiene
 * su valor escrito al final y un detalle al pasar el mouse o con el teclado;
 * los mismos datos están en la tabla "Por transportista".
 */
export function GraficosTransportistas({
  filas,
  envios,
}: {
  filas: FilaTransportista[];
  envios: Envio[];
}) {
  // Multa por transportista: solo los que tienen multa, de mayor a menor.
  const multas = filas
    .filter((f) => f.conteos.monto_multa_total > 0)
    .map((f) => ({
      nombre: f.nombre,
      valor: f.conteos.monto_multa_total,
      texto: pesos(f.conteos.monto_multa_total),
      detalle: `${guias(f.conteos.incumplidos)} fuera de plazo × ${pesos(
        f.multa_por_incumplimiento,
      )}`,
    }))
    .sort((a, b) => b.valor - a.valor);

  // Atraso promedio y máximo de las guías entregadas fuera de plazo.
  const atrasos = new Map<string, number[]>();
  for (const e of envios) {
    if (e.resultado !== "INCUMPLIDO" || e.horas_atraso == null) continue;
    const nombre = e.transportista ?? "Sin transportista";
    atrasos.set(nombre, [...(atrasos.get(nombre) ?? []), e.horas_atraso]);
  }
  const promedios = [...atrasos.entries()]
    .map(([nombre, lista]) => {
      const promedio = lista.reduce((suma, h) => suma + h, 0) / lista.length;
      return {
        nombre,
        valor: promedio,
        texto: horas(Math.round(promedio * 10) / 10),
        detalle: `${guias(lista.length)} fuera de plazo; la más atrasada, ${horas(
          Math.max(...lista),
        )}`,
      };
    })
    .sort((a, b) => b.valor - a.valor);

  if (multas.length === 0) return null;

  return (
    <section aria-labelledby="titulo-graficos" className="mt-12 break-inside-avoid-page">
      <h2 id="titulo-graficos" className="text-lg font-semibold">
        Gráficos por transportista
      </h2>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <GraficoBarras
          titulo="Multa por reclamar"
          subtitulo="Pesos chilenos, según la multa fija de cada regla SLA"
          barras={multas}
          claseBarra="bg-incumplido"
        />
        <GraficoBarras
          titulo="Atraso promedio de las guías fuera de plazo"
          subtitulo="Horas hábiles por sobre el plazo acordado"
          barras={promedios}
          claseBarra="bg-accion"
        />
      </div>
    </section>
  );
}

/** Una barra del gráfico: nombre, valor numérico, valor escrito y detalle para el tooltip. */
type Barra = { nombre: string; valor: number; texto: string; detalle: string };

/**
 * Gráfico de barras horizontales de una sola serie. Las barras parten de la
 * misma línea base, miden a lo más 20 px de alto y tienen la punta redondeada.
 */
function GraficoBarras({
  titulo,
  subtitulo,
  barras,
  claseBarra,
}: {
  titulo: string;
  subtitulo: string;
  barras: Barra[];
  claseBarra: string;
}) {
  const maximo = Math.max(...barras.map((b) => b.valor), 0);
  return (
    <figure className="rounded-lg border border-linea bg-superficie p-5">
      <figcaption>
        <p className="font-semibold">{titulo}</p>
        <p className="text-sm text-tinta-suave">{subtitulo}</p>
      </figcaption>
      <ul className="mt-4 space-y-2" aria-label={titulo}>
        {barras.map((b) => {
          const ancho = maximo > 0 ? Math.max((b.valor / maximo) * 100, 1) : 0;
          return (
            <li
              key={b.nombre}
              tabIndex={0}
              aria-label={`${b.nombre}: ${b.texto}. ${b.detalle}.`}
              className={clases(
                "group relative grid grid-cols-[8.5rem_1fr] items-center gap-3 rounded-md",
                "py-1 outline-none focus-visible:ring-2 focus-visible:ring-foco",
              )}
            >
              <span className="truncate text-sm">{b.nombre}</span>
              <span className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className={clases(
                    "block h-5 rounded-r-[4px] transition-opacity group-hover:opacity-85",
                    claseBarra,
                  )}
                  style={{ width: `calc((100% - 6rem) * ${ancho / 100})` }}
                />
                <span className="cifras whitespace-nowrap text-sm font-semibold">{b.texto}</span>
              </span>
              {/* Detalle al pasar el mouse o al enfocar con el teclado */}
              <span
                role="tooltip"
                className={clases(
                  "pointer-events-none absolute -top-9 left-36 z-10 hidden whitespace-nowrap",
                  "rounded-md bg-accion-fuerte px-2.5 py-1.5 text-xs text-sobre-accion shadow",
                  "group-hover:block group-focus-visible:block print:hidden",
                )}
              >
                {b.nombre}: {b.texto} · {b.detalle}
              </span>
            </li>
          );
        })}
      </ul>
    </figure>
  );
}
