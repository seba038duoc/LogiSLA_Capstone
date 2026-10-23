"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { FranjaCumplimiento, LeyendaFranja } from "@/components/Franja";
import {
  Aviso, BOTON_PRIMARIO, BOTON_SECUNDARIO, Cargando, EtiquetaEstadoLote, EtiquetaResultado,
  nombreResultado, Spinner,
} from "@/components/ui";
import {
  auditarLote, Envio, ErrorApi, FilaTransportista, listarEnvios, LoteDetalle, mensajeDeError,
  obtenerDetalleLote, ResultadoEnvio,
} from "@/lib/api";
import { descargarCsv } from "@/lib/csv";
import {
  entero, fechaHoraLocal, fechaSistema, guias, horas, pesos, porcentaje, porcentajeCumplimiento,
} from "@/lib/formato";

type Estado =
  | { tipo: "cargando" }
  | { tipo: "error"; mensaje: string; noExiste: boolean }
  | { tipo: "listo"; lote: LoteDetalle; envios: Envio[] };

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
          })
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
      <Link href="/" className="text-sm font-medium text-tinta-suave underline-offset-2 hover:underline">
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

function DetalleLote({
  lote, envios, auditando, errorAuditoria, onAuditar,
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
      ["N° guía", "Transportista", "Destino", "Fecha despacho", "Fecha entrega", "Horas hábiles de atraso", "Multa (CLP)"],
      ...incumplidos.map((e) => [
        e.numero_guia,
        e.transportista ?? "",
        e.destino ?? "",
        fechaHoraLocal(e.fecha_despacho),
        fechaHoraLocal(e.fecha_entrega),
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
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          {incumplidos.length > 0 && (
            <button onClick={descargarIncumplimientos} className={BOTON_SECUNDARIO}>
              Descargar incumplimientos (CSV)
            </button>
          )}
          <button onClick={onAuditar} disabled={auditando} className={auditado ? BOTON_SECUNDARIO : BOTON_PRIMARIO}>
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
            Cumplimiento de SLA: <span className="cifras font-semibold text-tinta">{porcentaje(cumplimiento)}</span>{" "}
            de las {guias(c.cumplidos + c.incumplidos)} que se pudieron auditar.
          </p>
        )}
        {!auditado && (
          <p className="mt-4 max-w-2xl text-tinta-suave">
            Al auditar, cada entrega se compara con el plazo en horas hábiles acordado con su transportista.
          </p>
        )}
        <FranjaCumplimiento conteos={c} alto="h-6" className="mt-6" />
        <div className="mt-3">
          <LeyendaFranja conteos={c} />
        </div>
      </section>

      {auditado && c.sin_regla > 0 && (
        <div className="mt-6">
          <Aviso tipo="aviso" titulo={`${guias(c.sin_regla)} entregadas no se pudieron auditar`}>
            <p>
              Su transportista no tiene una regla SLA activa (plazo y multa). Cuando la regla exista, usa
              “Volver a auditar” para incluirlas.
            </p>
          </Aviso>
        </div>
      )}

      <TablaTransportistas filas={lote.por_transportista} auditado={auditado} />
      {/* la key reinicia filtro y página cuando el lote se (re)audita */}
      <TablaGuias key={`${lote.estado}-${lote.fecha_procesado}`} envios={envios} auditado={auditado} />
    </>
  );
}

/* --------------------------- Transportistas ---------------------------- */

function TablaTransportistas({ filas, auditado }: { filas: FilaTransportista[]; auditado: boolean }) {
  return (
    <section aria-labelledby="titulo-transportistas" className="mt-12">
      <h2 id="titulo-transportistas" className="text-lg font-semibold">
        Por transportista
      </h2>
      <div className="mt-4 overflow-x-auto rounded-lg border border-linea bg-superficie">
        <table className="w-full min-w-[760px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-linea text-tinta-suave">
              <th scope="col" className="px-4 py-3 font-medium">Transportista</th>
              <th scope="col" className="px-4 py-3 font-medium">Plazo acordado</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Guías</th>
              <th scope="col" className="w-[26%] px-4 py-3 font-medium">Cumplimiento</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Fuera de plazo</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Multa</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((fila) => {
              const cumplimiento = porcentajeCumplimiento(fila.conteos);
              return (
                <tr key={fila.nombre} className="border-b border-linea last:border-b-0">
                  <th scope="row" className="px-4 py-3 font-semibold">{fila.nombre}</th>
                  <td className="cifras px-4 py-3 text-tinta-suave">
                    {fila.horas_habiles_maximas == null ? (
                      "Sin regla SLA"
                    ) : (
                      <>
                        {entero(fila.horas_habiles_maximas)} h hábiles
                        {fila.multa_por_incumplimiento != null && `, multa ${pesos(fila.multa_por_incumplimiento)}`}
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
                  <td className="cifras px-4 py-3 text-right">{auditado ? entero(fila.conteos.incumplidos) : ""}</td>
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

const POR_PAGINA = 50;
type Filtro = "TODAS" | ResultadoEnvio;
const ORDEN_FILTROS: ResultadoEnvio[] = ["INCUMPLIDO", "CUMPLIDO", "EN_TRANSITO", "SIN_REGLA", "PENDIENTE"];

function TablaGuias({ envios, auditado }: { envios: Envio[]; auditado: boolean }) {
  const hayIncumplidos = envios.some((e) => e.resultado === "INCUMPLIDO");
  // Si hay guías fuera de plazo, se parte mostrando esas: es a lo que se viene.
  const [filtro, setFiltro] = useState<Filtro>(hayIncumplidos ? "INCUMPLIDO" : "TODAS");
  const [busqueda, setBusqueda] = useState("");
  const [pagina, setPagina] = useState(1);

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
      return [e.numero_guia, e.transportista, e.destino].some((v) => v?.toLowerCase().includes(texto));
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
        <div role="group" aria-label="Filtrar guías por resultado" className="flex flex-wrap gap-1.5">
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
            className="w-72 max-w-full rounded-md border border-linea bg-superficie px-3 py-2 text-sm text-tinta placeholder:text-tinta-suave"
          />
        </div>
      </div>

      <div className="mt-3 overflow-x-auto rounded-lg border border-linea bg-superficie">
        <table className="w-full min-w-[880px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-linea text-tinta-suave">
              <th scope="col" className="px-4 py-3 font-medium">N° guía</th>
              <th scope="col" className="px-4 py-3 font-medium">Transportista</th>
              <th scope="col" className="px-4 py-3 font-medium">Destino</th>
              <th scope="col" className="px-4 py-3 font-medium">Despacho</th>
              <th scope="col" className="px-4 py-3 font-medium">Entrega</th>
              <th scope="col" className="px-4 py-3 font-medium">Resultado</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Atraso</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Multa</th>
            </tr>
          </thead>
          <tbody>
            {visibles.map((e) => {
              const incumplio = e.resultado === "INCUMPLIDO";
              return (
                <tr key={e.id} className="border-b border-linea last:border-b-0">
                  <th scope="row" className="cifras whitespace-nowrap px-4 py-2.5 font-semibold">{e.numero_guia}</th>
                  <td className="px-4 py-2.5">{e.transportista ?? ""}</td>
                  <td className="px-4 py-2.5">{e.destino ?? ""}</td>
                  <td className="cifras whitespace-nowrap px-4 py-2.5 text-tinta-suave">{fechaHoraLocal(e.fecha_despacho)}</td>
                  <td className="cifras whitespace-nowrap px-4 py-2.5 text-tinta-suave">{fechaHoraLocal(e.fecha_entrega)}</td>
                  <td className="px-4 py-2.5">
                    <EtiquetaResultado resultado={e.resultado} />
                  </td>
                  <td className="cifras whitespace-nowrap px-4 py-2.5 text-right">
                    {incumplio ? horas(e.horas_atraso) : ""}
                  </td>
                  <td className={`cifras whitespace-nowrap px-4 py-2.5 text-right ${incumplio ? "font-semibold text-incumplido" : ""}`}>
                    {incumplio ? pesos(e.monto_multa) : ""}
                  </td>
                </tr>
              );
            })}
            {visibles.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-tinta-suave">
                  {busqueda.trim()
                    ? `Ninguna guía coincide con “${busqueda.trim()}”.`
                    : "No hay guías con este resultado."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-tinta-suave">
        <p role="status" className="cifras">
          {filtrados.length === 0
            ? "0 guías"
            : `${entero((paginaActual - 1) * POR_PAGINA + 1)} a ${entero(
                Math.min(paginaActual * POR_PAGINA, filtrados.length)
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
