"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CriteriosAuditoria } from "@/components/CriteriosAuditoria";
import { GraficosTransportistas } from "@/components/GraficosTransportistas";
import { clases } from "@/lib/clases";
import { Aviso, BOTON_PRIMARIO, Cargando, nombreResultado } from "@/components/ui";
import {
  Conteos,
  Envio,
  listarEnvios,
  LoteDetalle,
  mensajeDeError,
  obtenerDetalleLote,
  ResultadoEnvio,
} from "@/lib/api";
import {
  entero,
  fechaHoraCorta,
  fechaHoraLocal,
  fechaSistema,
  guias,
  horas,
  pesos,
  porcentaje,
  porcentajeCumplimiento,
} from "@/lib/formato";

/**
 * Informe de auditoría de un lote (ruta /lotes/[id]/informe).
 *
 * Documento formal para entregar o archivar: encabezado con la empresa y el
 * archivo, resumen de resultados, criterios de la auditoría, resultado por
 * transportista y el detalle de las guías fuera de plazo, vencidas sin
 * entrega y con datos a revisar, cada una con su justificación. Está
 * pensado para imprimirse o guardarse como PDF desde el navegador (la
 * cabecera y el pie del sitio se ocultan al imprimir).
 */

/** Estados de la página mientras se piden el lote y sus guías. */
type Estado =
  | { tipo: "cargando" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "listo"; lote: LoteDetalle; envios: Envio[] };

/** Página del informe: pide el lote y sus guías y arma el documento. */
export default function PaginaInforme() {
  const { id } = useParams<{ id: string }>();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });

  useEffect(() => {
    let vigente = true;
    Promise.all([obtenerDetalleLote(id), listarEnvios(id)])
      .then(([lote, envios]) => vigente && setEstado({ tipo: "listo", lote, envios }))
      .catch((e) => vigente && setEstado({ tipo: "error", mensaje: mensajeDeError(e) }));
    return () => {
      vigente = false;
    };
  }, [id]);

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-5 py-8 print:max-w-none print:px-0 print:py-0">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link
          href={`/lotes/${id}`}
          className="text-sm font-medium text-tinta-suave underline-offset-2 hover:underline"
        >
          Volver al lote
        </Link>
        {estado.tipo === "listo" && (
          <button onClick={() => window.print()} className={BOTON_PRIMARIO}>
            Imprimir o guardar como PDF
          </button>
        )}
      </div>

      {estado.tipo === "cargando" && <Cargando texto="Preparando el informe…" />}
      {estado.tipo === "error" && (
        <div className="mt-6">
          <Aviso titulo="No se pudo preparar el informe">
            <p>{estado.mensaje}</p>
          </Aviso>
        </div>
      )}
      {estado.tipo === "listo" &&
        (estado.lote.estado === "COMPLETADO" ? (
          <Informe lote={estado.lote} envios={estado.envios} />
        ) : (
          <div className="mt-6">
            <Aviso tipo="aviso" titulo="El lote todavía no se audita">
              <p>Audita el lote para generar su informe.</p>
            </Aviso>
          </div>
        ))}
    </main>
  );
}

/** Filas del cuadro de resultados: categoría, cantidad y qué significa. */
const FILAS_RESUMEN: { clave: keyof Conteos; nombre: string; detalle: string }[] = [
  { clave: "cumplidos", nombre: "En plazo", detalle: "Entregadas antes de su fecha límite." },
  {
    clave: "incumplidos",
    nombre: "Fuera de plazo",
    detalle: "Entregadas después de su fecha límite. Llevan multa.",
  },
  {
    clave: "vencidas_sin_entrega",
    nombre: "Vencidas sin entrega",
    detalle: "Sin registro de entrega y con el plazo vencido a la fecha de corte. Sin multa.",
  },
  {
    clave: "en_transito",
    nombre: "En tránsito",
    detalle: "Sin registro de entrega, pero su plazo aún no vence.",
  },
  {
    clave: "datos_invalidos",
    nombre: "Datos a revisar",
    detalle: "Fechas inconsistentes o guía repetida. No se auditaron.",
  },
  {
    clave: "sin_regla",
    nombre: "Sin regla SLA",
    detalle: "Su transportista no tiene plazo y multa definidos. No se auditaron.",
  },
];

/** El documento del informe, con sus secciones numeradas. */
function Informe({ lote, envios }: { lote: LoteDetalle; envios: Envio[] }) {
  const c = lote.conteos;
  const cumplimiento = porcentajeCumplimiento(c);
  const de = (resultado: ResultadoEnvio) => envios.filter((e) => e.resultado === resultado);
  const fueraDePlazo = de("INCUMPLIDO");
  const vencidas = de("VENCIDA_SIN_ENTREGA");
  const noAuditadas = [...de("DATOS_INVALIDOS"), ...de("SIN_REGLA")];

  return (
    <article className="mt-6 rounded-lg border border-linea bg-superficie p-8 print:mt-0 print:border-0 print:p-0">
      <header className="border-b border-linea pb-5">
        <p className="text-sm font-semibold uppercase tracking-widest text-tinta-suave">
          LogiSLA · Informe de auditoría de SLA
        </p>
        <h1 className="mt-2 text-2xl font-semibold">{lote.empresa_nombre}</h1>
        {lote.empresa_rut && <p className="text-tinta-suave">RUT {lote.empresa_rut}</p>}
        <dl className="cifras mt-4 grid gap-x-8 gap-y-1 text-sm sm:grid-cols-2">
          <Par termino="Archivo auditado" valor={lote.nombre_archivo} />
          <Par termino="Guías en el archivo" valor={entero(c.total)} />
          <Par termino="Cargado el" valor={fechaSistema(lote.fecha_creacion)} />
          <Par termino="Fecha de corte" valor={fechaHoraLocal(lote.fecha_corte)} />
        </dl>
      </header>

      <Seccion numero={1} titulo="Resultado">
        <p className="cifras text-lg">
          Multas por reclamar: <strong>{pesos(c.monto_multa_total)}</strong> por{" "}
          {guias(c.incumplidos)} entregadas fuera de plazo.
          {cumplimiento != null &&
            ` Cumplimiento del SLA: ${porcentaje(cumplimiento)} de las ${guias(
              c.cumplidos + c.incumplidos,
            )} entregadas que se pudieron auditar.`}
        </p>
        <Tabla
          encabezados={["Resultado", "Guías", "Qué significa"]}
          derecha={[1]}
          ajustar={[2]}
          filas={FILAS_RESUMEN.filter((f) => c[f.clave] > 0).map((f) => [
            f.nombre,
            entero(c[f.clave]),
            f.detalle,
          ])}
          pie={["Total", entero(c.total), ""]}
        />
      </Seccion>

      <CriteriosAuditoria
        criterios={lote.criterios}
        fechaCorte={lote.fecha_corte}
        idTitulo="informe-criterios"
        titulo="2. Criterios de la auditoría"
      />

      <Seccion numero={3} titulo="Resultado por transportista">
        <Tabla
          encabezados={[
            "Transportista",
            "Plazo y multa",
            "Guías",
            "En plazo",
            "Fuera de plazo",
            "Vencidas sin entrega",
            "Cumplimiento",
            "Multa",
          ]}
          derecha={[2, 3, 4, 5, 6, 7]}
          filas={lote.por_transportista.map((f) => {
            const pct = porcentajeCumplimiento(f.conteos);
            return [
              f.nombre,
              f.horas_habiles_maximas == null
                ? "Sin regla SLA"
                : `${f.horas_habiles_maximas} h hábiles, ${pesos(f.multa_por_incumplimiento)}`,
              entero(f.conteos.total),
              entero(f.conteos.cumplidos),
              entero(f.conteos.incumplidos),
              entero(f.conteos.vencidas_sin_entrega),
              pct == null ? "" : porcentaje(pct),
              pesos(f.conteos.monto_multa_total),
            ];
          })}
        />
      </Seccion>

      <GraficosTransportistas filas={lote.por_transportista} envios={envios} />

      <Seccion
        numero={4}
        titulo={`Guías entregadas fuera de plazo (${entero(fueraDePlazo.length)})`}
      >
        {fueraDePlazo.length === 0 ? (
          <p className="text-tinta-suave">Ninguna.</p>
        ) : (
          <Tabla
            encabezados={[
              "Guía",
              "Transportista",
              "Despacho",
              "Fecha límite",
              "Entrega",
              "Horas hábiles (usadas / plazo)",
              "Atraso",
              "Multa",
            ]}
            derecha={[5, 6, 7]}
            filas={fueraDePlazo.map((e) => [
              e.numero_guia,
              e.transportista ?? "",
              fechaHoraCorta(e.fecha_despacho),
              fechaHoraCorta(e.fecha_limite),
              fechaHoraCorta(e.fecha_entrega),
              `${horas(e.horas_habiles_transcurridas)} / ${e.horas_habiles_permitidas ?? "?"} h`,
              horas(e.horas_atraso),
              pesos(e.monto_multa),
            ])}
            pie={["Total", "", "", "", "", "", "", pesos(c.monto_multa_total)]}
          />
        )}
      </Seccion>

      <Seccion
        numero={5}
        titulo={`Guías sin registro de entrega con el plazo vencido (${entero(vencidas.length)})`}
      >
        {vencidas.length === 0 ? (
          <p className="text-tinta-suave">Ninguna.</p>
        ) : (
          <>
            <p className="text-sm text-tinta-suave">
              No llevan multa porque no hay registro de entrega. Se recomienda pedir a cada
              transportista el comprobante de entrega de estas guías.
            </p>
            <Tabla
              encabezados={[
                "Guía",
                "Transportista",
                "Despacho",
                "Fecha límite",
                "Horas hábiles al corte",
                "Vencida hace",
              ]}
              derecha={[4, 5]}
              filas={vencidas.map((e) => [
                e.numero_guia,
                e.transportista ?? "",
                fechaHoraCorta(e.fecha_despacho),
                fechaHoraCorta(e.fecha_limite),
                horas(e.horas_habiles_transcurridas),
                horas(e.horas_atraso),
              ])}
            />
          </>
        )}
      </Seccion>

      {noAuditadas.length > 0 && (
        <Seccion numero={6} titulo={`Guías no auditadas (${entero(noAuditadas.length)})`}>
          <Tabla
            encabezados={["Guía", "Transportista", "Motivo", "Justificación"]}
            ajustar={[3]}
            filas={noAuditadas.map((e) => [
              e.numero_guia,
              e.transportista ?? "",
              nombreResultado(e.resultado),
              e.justificacion,
            ])}
          />
        </Seccion>
      )}

      <footer className="mt-10 border-t border-linea pt-4 text-xs text-tinta-suave">
        Informe generado por LogiSLA. Las cifras las calcula el motor de auditoría (horas hábiles,
        feriados chilenos y reglas SLA), no la IA. La justificación de cada guía está en el detalle
        del lote y en el archivo «Detalle completo (CSV)».
      </footer>
    </article>
  );
}

/** Sección numerada del informe. */
function Seccion({
  numero,
  titulo,
  children,
}: {
  numero: number;
  titulo: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-10 print:mt-6">
      <h2 className="text-lg font-semibold break-after-avoid">
        {numero}. {titulo}
      </h2>
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  );
}

/** Un dato del encabezado del informe. */
function Par({ termino, valor }: { termino: string; valor: string }) {
  return (
    <div className="flex gap-2">
      <dt className="text-tinta-suave">{termino}:</dt>
      <dd className="font-medium">{valor}</dd>
    </div>
  );
}

/**
 * Tabla simple del informe. `derecha` indica las columnas numéricas
 * (alineadas a la derecha) y `ajustar` las de texto largo, que pueden
 * ocupar varias líneas; el resto no se corta, para que fechas y montos se
 * lean en una sola línea también al imprimir.
 */
function Tabla({
  encabezados,
  filas,
  pie,
  derecha = [],
  ajustar = [],
}: {
  encabezados: string[];
  filas: (string | number)[][];
  pie?: string[];
  derecha?: number[];
  ajustar?: number[];
}) {
  const alinear = (i: number) =>
    clases(
      derecha.includes(i) ? "text-right" : "text-left",
      !ajustar.includes(i) && "whitespace-nowrap",
    );
  return (
    <div className="overflow-x-auto">
      <table className="cifras w-full border-collapse text-sm print:text-[8.5pt]">
        <thead>
          <tr className="border-b-2 border-tinta/30">
            {encabezados.map((e, i) => (
              <th
                key={e}
                scope="col"
                className={clases(
                  "px-2 py-2 align-bottom font-semibold print:px-1",
                  derecha.includes(i) ? "text-right" : "text-left",
                )}
              >
                {e}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filas.map((fila, f) => (
            <tr key={f} className="break-inside-avoid border-b border-linea">
              {fila.map((celda, i) => (
                <td key={i} className={`px-2 py-1.5 align-top print:px-1 ${alinear(i)}`}>
                  {celda}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {pie && (
          <tfoot>
            <tr className="border-t-2 border-tinta/30 font-semibold">
              {pie.map((celda, i) => (
                <td key={i} className={`px-2 py-2 print:px-1 ${alinear(i)}`}>
                  {celda}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
