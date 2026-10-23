"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ConEmpresa } from "@/components/EstadoEmpresa";
import { FranjaCumplimiento } from "@/components/Franja";
import { Aviso, BOTON_PRIMARIO, BOTON_SECUNDARIO, Cargando, EtiquetaEstadoLote } from "@/components/ui";
import { Conteos, Empresa, listarLotes, LoteResumen, mensajeDeError } from "@/lib/api";
import { entero, fechaSistema, guias, pesos, porcentaje, porcentajeCumplimiento } from "@/lib/formato";

export default function PaginaLotes() {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-10">
      <ConEmpresa>{(empresa) => <PanelLotes key={empresa.id} empresa={empresa} />}</ConEmpresa>
    </main>
  );
}

type Estado =
  | { tipo: "cargando" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "listo"; lotes: LoteResumen[] };

function PanelLotes({ empresa }: { empresa: Empresa }) {
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    let vigente = true;
    listarLotes(empresa.id)
      .then((lotes) => vigente && setEstado({ tipo: "listo", lotes }))
      .catch((e) => vigente && setEstado({ tipo: "error", mensaje: mensajeDeError(e) }));
    return () => {
      vigente = false;
    };
  }, [empresa.id, intento]);

  if (estado.tipo === "cargando") return <Cargando texto="Cargando lotes…" />;

  if (estado.tipo === "error") {
    return (
      <Aviso titulo="No se pudieron cargar los lotes">
        <p>{estado.mensaje}</p>
        <button
          className={BOTON_SECUNDARIO}
          onClick={() => {
            setEstado({ tipo: "cargando" });
            setIntento((n) => n + 1);
          }}
        >
          Reintentar
        </button>
      </Aviso>
    );
  }

  const { lotes } = estado;

  if (lotes.length === 0) {
    return (
      <section className="max-w-2xl py-6">
        <h1 className="titular text-3xl sm:text-4xl">{empresa.nombre} todavía no tiene envíos cargados</h1>
        <p className="mt-4 text-tinta-suave">
          Sube la planilla de guías del período (CSV o Excel). LogiSLA compara cada entrega con el plazo
          acordado con el transportista y calcula la multa de las que llegaron tarde.
        </p>
        <Link href="/cargar" className={`${BOTON_PRIMARIO} mt-6`}>
          Cargar envíos
        </Link>
      </section>
    );
  }

  return (
    <>
      <ResumenEmpresa lotes={lotes} />

      <section aria-labelledby="titulo-lotes" className="mt-10">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 id="titulo-lotes" className="text-lg font-semibold">
            Lotes cargados
          </h2>
          <Link href="/cargar" className={BOTON_PRIMARIO}>
            Cargar envíos
          </Link>
        </div>

        <div className="mt-4 overflow-x-auto rounded-lg border border-linea bg-superficie">
          <table className="w-full min-w-[720px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-linea text-tinta-suave">
                <th scope="col" className="px-4 py-3 font-medium">Archivo</th>
                <th scope="col" className="px-4 py-3 text-right font-medium">Guías</th>
                <th scope="col" className="w-[30%] px-4 py-3 font-medium">Cumplimiento</th>
                <th scope="col" className="px-4 py-3 text-right font-medium">Multas por reclamar</th>
                <th scope="col" className="px-4 py-3 font-medium">Estado</th>
              </tr>
            </thead>
            <tbody>
              {lotes.map((lote) => (
                <FilaLote key={lote.id} lote={lote} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function sumar(lotes: LoteResumen[]): Conteos {
  const total: Conteos = {
    total: 0, cumplidos: 0, incumplidos: 0, en_transito: 0, sin_regla: 0, pendientes: 0, monto_multa_total: 0,
  };
  for (const { conteos } of lotes) {
    total.total += conteos.total;
    total.cumplidos += conteos.cumplidos;
    total.incumplidos += conteos.incumplidos;
    total.en_transito += conteos.en_transito;
    total.sin_regla += conteos.sin_regla;
    total.pendientes += conteos.pendientes;
    total.monto_multa_total += conteos.monto_multa_total;
  }
  return total;
}

/** El titular de la página es la respuesta a "¿cuánto puedo reclamar?". */
function ResumenEmpresa({ lotes }: { lotes: LoteResumen[] }) {
  const total = sumar(lotes);
  const sinAuditar = lotes.filter((l) => l.estado !== "COMPLETADO").length;
  const cumplimiento = porcentajeCumplimiento(total);
  const auditadas = total.cumplidos + total.incumplidos;

  let titular: string;
  if (auditadas === 0) {
    titular =
      sinAuditar > 0
        ? `${guias(total.total)} cargadas, ninguna auditada todavía`
        : "Ninguna guía se pudo auditar todavía";
  } else if (total.incumplidos === 0) {
    titular = `Las ${guias(auditadas)} auditadas llegaron en plazo`;
  } else {
    titular = `${pesos(total.monto_multa_total)} por reclamar en ${guias(total.incumplidos)} fuera de plazo`;
  }

  return (
    <section aria-label="Resumen de la empresa">
      <h1 className="titular cifras max-w-4xl text-3xl sm:text-5xl">{titular}</h1>
      <p className="mt-4 max-w-3xl text-tinta-suave">
        {entero(lotes.length)} {lotes.length === 1 ? "lote cargado" : "lotes cargados"} con {guias(total.total)}.
        {cumplimiento != null && ` Cumplimiento de SLA: ${porcentaje(cumplimiento)} de las guías auditadas.`}
        {sinAuditar > 0 &&
          ` ${sinAuditar === 1 ? "Queda 1 lote" : `Quedan ${entero(sinAuditar)} lotes`} sin auditar.`}
      </p>
    </section>
  );
}

function FilaLote({ lote }: { lote: LoteResumen }) {
  const auditado = lote.estado === "COMPLETADO";
  const cumplimiento = porcentajeCumplimiento(lote.conteos);
  return (
    <tr className="border-b border-linea last:border-b-0 hover:bg-hundido">
      <th scope="row" className="px-4 py-3.5 text-left font-normal">
        <Link href={`/lotes/${lote.id}`} className="font-semibold underline-offset-2 hover:underline">
          {lote.nombre_archivo}
        </Link>
        <div className="mt-0.5 text-xs text-tinta-suave">Cargado el {fechaSistema(lote.fecha_creacion)}</div>
      </th>
      <td className="cifras px-4 py-3.5 text-right">{entero(lote.conteos.total)}</td>
      <td className="px-4 py-3.5">
        <div className="flex items-center gap-3">
          <FranjaCumplimiento conteos={lote.conteos} />
          <span className="cifras w-14 shrink-0 text-right text-tinta-suave">
            {cumplimiento == null ? "" : porcentaje(cumplimiento)}
          </span>
        </div>
      </td>
      <td
        className={`cifras px-4 py-3.5 text-right font-semibold ${
          lote.conteos.monto_multa_total > 0 ? "text-incumplido" : "text-tinta-suave"
        }`}
      >
        {auditado ? pesos(lote.conteos.monto_multa_total) : ""}
      </td>
      <td className="px-4 py-3.5">
        <EtiquetaEstadoLote estado={lote.estado} />
      </td>
    </tr>
  );
}
