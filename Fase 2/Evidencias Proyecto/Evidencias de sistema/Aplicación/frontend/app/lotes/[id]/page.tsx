"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Fragment, useEffect, useMemo, useState } from "react";
import { CartaReclamo } from "@/components/CartaReclamo";
import { CriteriosAuditoria } from "@/components/CriteriosAuditoria";
import { DetalleGuia } from "@/components/DetalleGuia";
import { GraficosTransportistas } from "@/components/GraficosTransportistas";
import { ResumenEjecutivo } from "@/components/ResumenEjecutivo";
import { FranjaCumplimiento, LeyendaFranja } from "@/components/Franja";
import {
  Aviso,
  BOTON_PRIMARIO,
  BOTON_SECUNDARIO,
  Cargando,
  EtiquetaEstadoLote,
  EtiquetaResultado,
  nombreResultado,
  Spinner,
} from "@/components/ui";
import {
  auditarLote,
  Envio,
  ErrorApi,
  FilaTransportista,
  listarEnvios,
  LoteDetalle,
  mensajeDeError,
  obtenerDetalleLote,
  ResultadoEnvio,
} from "@/lib/api";
import { descargarCsv } from "@/lib/csv";
import { descargarDetalleAuditoria } from "@/lib/detalleCsv";
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
import { clases } from "@/lib/clases";

/**
 * Detalle de un lote (ruta /lotes/[id]).
 *
 * Muestra el resultado de la auditoría de un archivo cargado: monto por
 * reclamar, franja de cumplimiento, desglose por transportista, tabla de
 * guías con filtros y búsqueda, y las secciones de IA generativa (resumen
 * ejecutivo y carta de reclamo). Si el lote aún no se audita, ofrece el
 * botón para auditarlo.
 */

/** Estados de la página mientras se piden el lote y sus guías al backend. */
type Estado =
  | { tipo: "cargando" }
  | { tipo: "error"; mensaje: string; noExiste: boolean }
  | { tipo: "listo"; lote: LoteDetalle; envios: Envio[] };

/**
 * Página del lote: lee el id desde la URL, pide en paralelo el detalle del
 * lote y sus guías, y permite volver a auditarlo (al terminar, recarga los
 * datos cambiando `version`).
 */
export default function PaginaLote() {
  const { id } = useParams<{ id: string }>();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [version, setVersion] = useState(0);
  const [auditando, setAuditando] = useState(false);
  const [errorAuditoria, setErrorAuditoria] = useState<string | null>(null);

  useEffect(() => {
    let vigente = true;
    Promise.all([obtenerDetalleLote(id), listarEnvios(id)])
      .then(([lote, envios]) => vigente && setEstado({ tipo: "listo", lote, envios }))
      .catch(
        (e) =>
          vigente &&
          setEstado({
            tipo: "error",
            mensaje: mensajeDeError(e),
            noExiste: e instanceof ErrorApi && e.estado === 404,
          }),
      );
    return () => {
      vigente = false;
    };
  }, [id, version]);

  async function auditar() {
    setAuditando(true);
    setErrorAuditoria(null);
    try {
      await auditarLote(id);
      setVersion((n) => n + 1); // vuelve a pedir resumen y guías ya auditados
    } catch (e) {
      setErrorAuditoria(mensajeDeError(e));
    } finally {
      setAuditando(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-8">
      <Link
        href="/"
        className="text-sm font-medium text-tinta-suave underline-offset-2 hover:underline"
      >
        Volver a Lotes
      </Link>

      {estado.tipo === "cargando" && <Cargando texto="Cargando lote…" />}

      {estado.tipo === "error" && (
        <div className="mt-6">
          <Aviso titulo={estado.noExiste ? "Este lote no existe" : "No se pudo cargar el lote"}>
            <p>
              {estado.noExiste
                ? "Puede que el enlace esté incompleto o que el lote sea de otra base de datos."
                : estado.mensaje}
            </p>
            {!estado.noExiste && (
              <button
                className={BOTON_SECUNDARIO}
                onClick={() => {
                  setEstado({ tipo: "cargando" });
                  setVersion((n) => n + 1);
                }}
              >
                Reintentar
              </button>
            )}
          </Aviso>
        </div>
      )}

      {estado.tipo === "listo" && (
        <DetalleLote
          lote={estado.lote}
          envios={estado.envios}
          auditando={auditando}
          errorAuditoria={errorAuditoria}
          onAuditar={auditar}
        />
      )}
    </main>
  );
}

/* ---------------------------------------------------------------------- */

/** Frase principal del lote: monto por reclamar, "todo en plazo" o "esperando auditoría". */
function titularDelLote(lote: LoteDetalle): string {
  const c = lote.conteos;
  const auditadas = c.cumplidos + c.incumplidos;
  if (lote.estado !== "COMPLETADO") return `${guias(c.total)} esperando auditoría`;
  if (c.incumplidos > 0) {
    return `${pesos(c.monto_multa_total)} por reclamar en ${guias(c.incumplidos)} fuera de plazo`;
  }
  if (auditadas > 0) return `Las ${guias(auditadas)} auditadas llegaron en plazo`;
  return "Ninguna guía de este lote se pudo auditar";
}

/** Contenido del lote ya cargado: encabezado, resumen, tablas y secciones de IA. */
function DetalleLote({
  lote,
  envios,
  auditando,
  errorAuditoria,
  onAuditar,
}: {
  lote: LoteDetalle;
  envios: Envio[];
  auditando: boolean;
  errorAuditoria: string | null;
  onAuditar: () => void;
}) {
  const auditado = lote.estado === "COMPLETADO";
  const c = lote.conteos;
  const cumplimiento = porcentajeCumplimiento(c);
  const incumplidos = useMemo(() => envios.filter((e) => e.resultado === "INCUMPLIDO"), [envios]);

  function descargarIncumplimientos() {
    const base = lote.nombre_archivo.replace(/\.[^.]+$/, "");
    descargarCsv(`incumplimientos_${base}.csv`, [
      [
        "N° guía",
        "Transportista",
        "Destino",
        "Fecha despacho",
        "Fecha límite",
        "Fecha entrega",
        "Horas hábiles de atraso",
        "Multa (CLP)",
      ],
      ...incumplidos.map((e) => [
        e.numero_guia,
        e.transportista ?? "",
        e.destino ?? "",
        fechaHoraCorta(e.fecha_despacho),
        fechaHoraCorta(e.fecha_limite),
        fechaHoraCorta(e.fecha_entrega),
        e.horas_atraso ?? "",
        e.monto_multa ?? "",
      ]),
    ]);
  }

  return (
    <>
      <header className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-tinta-suave">
            <span className="break-all font-semibold text-tinta">{lote.nombre_archivo}</span>
            <EtiquetaEstadoLote estado={lote.estado} />
          </p>
          <p className="mt-1 text-sm text-tinta-suave">
            Cargado el {fechaSistema(lote.fecha_creacion)}
            {lote.fecha_procesado && `, auditado el ${fechaSistema(lote.fecha_procesado)}`}
            {lote.fecha_corte && ` (fecha de corte: ${fechaHoraLocal(lote.fecha_corte)})`}
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          {auditado && (
            <Link href={`/lotes/${lote.id}/informe`} className={BOTON_SECUNDARIO}>
              Informe de auditoría
            </Link>
          )}
          {auditado && (
            <button
              onClick={() => descargarDetalleAuditoria(lote, envios)}
              className={BOTON_SECUNDARIO}
            >
              Detalle completo (CSV)
            </button>
          )}
          {incumplidos.length > 0 && (
            <button onClick={descargarIncumplimientos} className={BOTON_SECUNDARIO}>
              Incumplimientos (CSV)
            </button>
          )}
          <button
            onClick={onAuditar}
            disabled={auditando}
            className={auditado ? BOTON_SECUNDARIO : BOTON_PRIMARIO}
          >
            {auditando && <Spinner />}
            {auditando ? "Auditando…" : auditado ? "Volver a auditar" : "Auditar lote"}
          </button>
        </div>
      </header>

      {errorAuditoria && (
        <div className="mt-5">
          <Aviso titulo="No se pudo auditar el lote">
            <p>{errorAuditoria}</p>
          </Aviso>
        </div>
      )}

      <section aria-label="Resultado del lote" className="mt-8">
        <h1 className="titular cifras max-w-4xl text-3xl sm:text-5xl">{titularDelLote(lote)}</h1>
        {cumplimiento != null && (
          <p className="mt-4 text-tinta-suave">
            Cumplimiento de SLA:{" "}
            <span className="cifras font-semibold text-tinta">{porcentaje(cumplimiento)}</span> de
            las {guias(c.cumplidos + c.incumplidos)} que se pudieron auditar.
          </p>
        )}
        {!auditado && (
          <p className="mt-4 max-w-2xl text-tinta-suave">
            Al auditar, cada entrega se compara con el plazo en horas hábiles acordado con su
            transportista.
          </p>
        )}
        <FranjaCumplimiento conteos={c} alto="h-6" className="mt-6" />
        <div className="mt-3">
          <LeyendaFranja conteos={c} />
        </div>
      </section>

      {auditado && !lote.fecha_corte && (
        <div className="mt-6">
          <Aviso tipo="aviso" titulo="Este lote se auditó con una versión anterior de LogiSLA">
            <p>
              Usa “Volver a auditar” para calcular la fecha límite de cada guía, revisar las que no
              registran entrega y ver la justificación completa.
            </p>
          </Aviso>
        </div>
      )}

      {auditado && c.vencidas_sin_entrega > 0 && (
        <div className="mt-6">
          <Aviso
            tipo="aviso"
            titulo={`${guias(c.vencidas_sin_entrega)} sin registro de entrega con el plazo vencido`}
          >
            <p>
              A la fecha de corte, el archivo no registra que estas encomiendas hayan llegado y su
              plazo ya venció. No llevan multa, porque no hay prueba de cuándo (ni si) se
              entregaron: corresponde pedir al transportista el comprobante de entrega. Están en el
              filtro “Vencida sin entrega” de la tabla de guías.
            </p>
          </Aviso>
        </div>
      )}

      {auditado && c.datos_invalidos > 0 && (
        <div className="mt-6">
          <Aviso tipo="aviso" titulo={`${guias(c.datos_invalidos)} con datos a revisar`}>
            <p>
              Sus fechas no son consistentes o el número de guía está repetido, así que no se
              auditaron ni se multaron. El motivo de cada una está en el filtro “Datos a revisar”.
              Corrige el archivo y vuelve a cargarlo para incluirlas.
            </p>
          </Aviso>
        </div>
      )}

      {auditado && c.sin_regla > 0 && (
        <div className="mt-6">
          <Aviso tipo="aviso" titulo={`${guias(c.sin_regla)} no se pudieron auditar`}>
            <p>
              Su transportista no tiene una regla SLA activa (plazo y multa). Cuando la regla
              exista, usa “Volver a auditar” para incluirlas.
            </p>
          </Aviso>
        </div>
      )}

      <TablaTransportistas filas={lote.por_transportista} auditado={auditado} />
      {auditado && <GraficosTransportistas filas={lote.por_transportista} envios={envios} />}
      {auditado && <CriteriosAuditoria criterios={lote.criterios} fechaCorte={lote.fecha_corte} />}
      {auditado && <ResumenEjecutivo key={`resumen-${lote.fecha_procesado}`} idLote={lote.id} />}
      {auditado && c.incumplidos > 0 && (
        // la key reinicia la carta cuando el lote se vuelve a auditar
        <CartaReclamo
          key={`carta-${lote.fecha_procesado}`}
          idLote={lote.id}
          transportistas={lote.por_transportista.filter((f) => f.conteos.incumplidos > 0)}
        />
      )}
      {/* la key reinicia filtro y página cuando el lote se (re)audita */}
      <TablaGuias
        key={`${lote.estado}-${lote.fecha_procesado}`}
        envios={envios}
        auditado={auditado}
      />
    </>
  );
}

/* --------------------------- Transportistas ---------------------------- */

/** Tabla "Por transportista": plazo acordado, guías, cumplimiento, atrasos y multa de cada uno. */
function TablaTransportistas({
  filas,
  auditado,
}: {
  filas: FilaTransportista[];
  auditado: boolean;
}) {
  return (
    <section aria-labelledby="titulo-transportistas" className="mt-12">
      <h2 id="titulo-transportistas" className="text-lg font-semibold">
        Por transportista
      </h2>
      <div className="mt-4 overflow-x-auto rounded-lg border border-linea bg-superficie">
        <table className="w-full min-w-[860px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-linea text-tinta-suave">
              <th scope="col" className="px-4 py-3 font-medium">
                Transportista
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                Plazo acordado
              </th>
              <th scope="col" className="px-4 py-3 text-right font-medium">
                Guías
              </th>
              <th scope="col" className="w-[26%] px-4 py-3 font-medium">
                Cumplimiento
              </th>
              <th scope="col" className="px-4 py-3 text-right font-medium">
                Fuera de plazo
              </th>
              <th scope="col" className="px-4 py-3 text-right font-medium">
                Vencidas sin entrega
              </th>
              <th scope="col" className="px-4 py-3 text-right font-medium">
                Multa
              </th>
            </tr>
          </thead>
          <tbody>
            {filas.map((fila) => {
              const cumplimiento = porcentajeCumplimiento(fila.conteos);
              return (
                <tr key={fila.nombre} className="border-b border-linea last:border-b-0">
                  <th scope="row" className="px-4 py-3 font-semibold">
                    {fila.nombre}
                  </th>
                  <td className="cifras px-4 py-3 text-tinta-suave">
                    {fila.horas_habiles_maximas == null ? (
                      "Sin regla SLA"
                    ) : (
                      <>
                        {entero(fila.horas_habiles_maximas)} h hábiles
                        {fila.multa_por_incumplimiento != null &&
                          `, multa ${pesos(fila.multa_por_incumplimiento)}`}
                      </>
                    )}
                  </td>
                  <td className="cifras px-4 py-3 text-right">{entero(fila.conteos.total)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <FranjaCumplimiento conteos={fila.conteos} />
                      <span className="cifras w-14 shrink-0 text-right text-tinta-suave">
                        {cumplimiento == null ? "" : porcentaje(cumplimiento)}
                      </span>
                    </div>
                  </td>
                  <td className="cifras px-4 py-3 text-right">
                    {auditado ? entero(fila.conteos.incumplidos) : ""}
                  </td>
                  <td
                    className={clases(
                      "cifras px-4 py-3 text-right",
                      fila.conteos.vencidas_sin_entrega > 0 && "font-semibold text-vencida",
                    )}
                  >
                    {auditado ? entero(fila.conteos.vencidas_sin_entrega) : ""}
                  </td>
                  <td
                    className={`cifras px-4 py-3 text-right font-semibold ${
                      fila.conteos.monto_multa_total > 0 ? "text-incumplido" : "text-tinta-suave"
                    }`}
                  >
                    {auditado ? pesos(fila.conteos.monto_multa_total) : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* -------------------------------- Guías -------------------------------- */

/** Cantidad de guías por página en la tabla de guías. */
const POR_PAGINA = 50;
/** Columnas de la tabla de guías (para las filas que ocupan todo el ancho). */
const COLUMNAS_GUIAS = 9;
/** Filtro elegido en la tabla de guías: todas o un resultado específico. */
type Filtro = "TODAS" | ResultadoEnvio;
/** Orden en que aparecen los botones de filtro (primero lo que interesa: fuera de plazo). */
const ORDEN_FILTROS: ResultadoEnvio[] = [
  "INCUMPLIDO",
  "VENCIDA_SIN_ENTREGA",
  "CUMPLIDO",
  "EN_TRANSITO",
  "DATOS_INVALIDOS",
  "SIN_REGLA",
  "PENDIENTE",
];

/**
 * Tabla de guías del lote con filtros por resultado, búsqueda por guía,
 * transportista o destino, paginación y descarga de incumplimientos en CSV.
 */
function TablaGuias({ envios, auditado }: { envios: Envio[]; auditado: boolean }) {
  const hayIncumplidos = envios.some((e) => e.resultado === "INCUMPLIDO");
  // Si hay guías fuera de plazo, se parte mostrando esas: es a lo que se viene.
  const [filtro, setFiltro] = useState<Filtro>(hayIncumplidos ? "INCUMPLIDO" : "TODAS");
  const [busqueda, setBusqueda] = useState("");
  const [pagina, setPagina] = useState(1);
  // Guías con el detalle de su cálculo desplegado.
  const [abiertas, setAbiertas] = useState<Set<string>>(new Set());

  function alternar(id: string) {
    setAbiertas((previas) => {
      const nuevas = new Set(previas);
      if (nuevas.has(id)) nuevas.delete(id);
      else nuevas.add(id);
      return nuevas;
    });
  }

  const cantidades = useMemo(() => {
    const mapa = new Map<ResultadoEnvio, number>();
    for (const e of envios) mapa.set(e.resultado, (mapa.get(e.resultado) ?? 0) + 1);
    return mapa;
  }, [envios]);

  const filtrados = useMemo(() => {
    const texto = busqueda.trim().toLowerCase();
    return envios.filter((e) => {
      if (filtro !== "TODAS" && e.resultado !== filtro) return false;
      if (!texto) return true;
      return [e.numero_guia, e.transportista, e.destino].some((v) =>
        v?.toLowerCase().includes(texto),
      );
    });
  }, [envios, filtro, busqueda]);

  const totalPaginas = Math.max(1, Math.ceil(filtrados.length / POR_PAGINA));
  const paginaActual = Math.min(pagina, totalPaginas);
  const visibles = filtrados.slice((paginaActual - 1) * POR_PAGINA, paginaActual * POR_PAGINA);

  const filtros: { valor: Filtro; texto: string; cantidad: number }[] = [
    { valor: "TODAS", texto: "Todas", cantidad: envios.length },
    ...ORDEN_FILTROS.filter((r) => cantidades.has(r)).map((r) => ({
      valor: r as Filtro,
      texto: nombreResultado(r),
      cantidad: cantidades.get(r) ?? 0,
    })),
  ];

  return (
    <section aria-labelledby="titulo-guias" className="mt-12">
      <h2 id="titulo-guias" className="text-lg font-semibold">
        Guías
      </h2>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div
          role="group"
          aria-label="Filtrar guías por resultado"
          className="flex flex-wrap gap-1.5"
        >
          {filtros.map((f) => {
            const activo = f.valor === filtro;
            return (
              <button
                key={f.valor}
                aria-pressed={activo}
                onClick={() => {
                  setFiltro(f.valor);
                  setPagina(1);
                }}
                className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
                  activo
                    ? "border-accion bg-accion text-sobre-accion"
                    : "border-linea bg-superficie text-tinta hover:bg-hundido"
                }`}
              >
                {f.texto} <span className="cifras opacity-75">{entero(f.cantidad)}</span>
              </button>
            );
          })}
        </div>
        <div>
          <label htmlFor="buscar-guia" className="sr-only">
            Buscar por guía, transportista o destino
          </label>
          <input
            id="buscar-guia"
            type="search"
            value={busqueda}
            onChange={(e) => {
              setBusqueda(e.target.value);
              setPagina(1);
            }}
            placeholder="Buscar guía, transportista o destino"
            className={clases(
              "w-72 max-w-full rounded-md border border-linea bg-superficie px-3 py-2",
              "text-sm text-tinta placeholder:text-tinta-suave",
            )}
          />
        </div>
      </div>

      <div className="mt-3 overflow-x-auto rounded-lg border border-linea bg-superficie">
        <table className="w-full min-w-[980px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-linea text-tinta-suave">
              <th scope="col" className="px-4 py-3 font-medium">
                N° guía
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                Transportista
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                Despacho
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                Entrega
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                Fecha límite
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                Resultado
              </th>
              <th scope="col" className="px-4 py-3 text-right font-medium">
                Atraso
              </th>
              <th scope="col" className="px-4 py-3 text-right font-medium">
                Multa
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                <span className="sr-only">Detalle del cálculo</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {visibles.map((e) => {
              const incumplio = e.resultado === "INCUMPLIDO";
              const vencida = e.resultado === "VENCIDA_SIN_ENTREGA";
              const abierta = abiertas.has(e.id);
              return (
                <Fragment key={e.id}>
                  <tr className={clases("border-b border-linea", abierta && "bg-hundido")}>
                    <th scope="row" className="cifras whitespace-nowrap px-4 py-2.5 font-semibold">
                      {e.numero_guia}
                    </th>
                    <td className="whitespace-nowrap px-4 py-2.5">{e.transportista ?? ""}</td>
                    <td className="cifras whitespace-nowrap px-4 py-2.5 text-tinta-suave">
                      {fechaHoraCorta(e.fecha_despacho)}
                    </td>
                    <td className="cifras whitespace-nowrap px-4 py-2.5 text-tinta-suave">
                      {e.entregada ? (
                        fechaHoraCorta(e.fecha_entrega)
                      ) : (
                        <span className={vencida ? "font-semibold text-vencida" : ""}>
                          Sin entrega
                        </span>
                      )}
                    </td>
                    <td className="cifras whitespace-nowrap px-4 py-2.5 text-tinta-suave">
                      {fechaHoraCorta(e.fecha_limite)}
                    </td>
                    <td className="px-4 py-2.5">
                      <EtiquetaResultado resultado={e.resultado} />
                    </td>
                    <td
                      className={clases(
                        "cifras whitespace-nowrap px-4 py-2.5 text-right",
                        vencida && "text-vencida",
                      )}
                    >
                      {incumplio || vencida ? horas(e.horas_atraso) : ""}
                    </td>
                    <td
                      className={clases(
                        "cifras whitespace-nowrap px-4 py-2.5 text-right",
                        incumplio && "font-semibold text-incumplido",
                      )}
                    >
                      {incumplio ? pesos(e.monto_multa) : ""}
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      <button
                        onClick={() => alternar(e.id)}
                        aria-expanded={abierta}
                        aria-controls={`detalle-${e.id}`}
                        className={clases(
                          "whitespace-nowrap rounded-md px-2 py-1 text-xs font-semibold",
                          "text-tinta underline-offset-2 hover:underline",
                        )}
                      >
                        {abierta ? "Ocultar" : "Ver cálculo"}
                        <span className="sr-only"> de la guía {e.numero_guia}</span>
                      </button>
                    </td>
                  </tr>
                  {abierta && (
                    <tr id={`detalle-${e.id}`} className="border-b border-linea bg-hundido">
                      <td colSpan={COLUMNAS_GUIAS} className="px-4 pb-4 pt-1">
                        <DetalleGuia envio={e} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {visibles.length === 0 && (
              <tr>
                <td colSpan={COLUMNAS_GUIAS} className="px-4 py-8 text-center text-tinta-suave">
                  {busqueda.trim()
                    ? `Ninguna guía coincide con “${busqueda.trim()}”.`
                    : "No hay guías con este resultado."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div
        className={clases(
          "mt-3 flex flex-wrap items-center justify-between gap-3",
          "text-sm text-tinta-suave",
        )}
      >
        <p role="status" className="cifras">
          {filtrados.length === 0
            ? "0 guías"
            : `${entero((paginaActual - 1) * POR_PAGINA + 1)} a ${entero(
                Math.min(paginaActual * POR_PAGINA, filtrados.length),
              )} de ${guias(filtrados.length)}`}
          {auditado ? "" : " (lote sin auditar)"}
        </p>
        {totalPaginas > 1 && (
          <div className="flex items-center gap-2">
            <button
              className={BOTON_SECUNDARIO}
              disabled={paginaActual <= 1}
              onClick={() => setPagina(paginaActual - 1)}
            >
              Anterior
            </button>
            <span className="cifras">
              Página {entero(paginaActual)} de {entero(totalPaginas)}
            </span>
            <button
              className={BOTON_SECUNDARIO}
              disabled={paginaActual >= totalPaginas}
              onClick={() => setPagina(paginaActual + 1)}
            >
              Siguiente
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
