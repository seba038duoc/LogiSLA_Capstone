"use client";

import { useState } from "react";
import { Aviso, BOTON_PRIMARIO, BOTON_SECUNDARIO, Spinner } from "@/components/ui";
import { OrigenIA } from "@/components/OrigenIA";
import { generarResumenEjecutivo, mensajeDeError, ResumenEjecutivo as Resumen } from "@/lib/api";
import { clases } from "@/lib/clases";

/**
 * Resumen ejecutivo del lote para la gerencia (IA generativa, HU-17).
 *
 * Igual que la carta de reclamo: Gemini (o Claude de respaldo) redacta a
 * partir de las cifras del motor de auditoría; si ninguna IA responde, el
 * backend usa una plantilla y lo informa en `motivo_plantilla`.
 */

type Estado =
  | { tipo: "inactivo" }
  | { tipo: "generando" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "listo"; resumen: Resumen };

/** Sección "Resumen ejecutivo": botón para generarlo y el texto resultante con opción de copiar. */
export function ResumenEjecutivo({ idLote }: { idLote: string }) {
  const [estado, setEstado] = useState<Estado>({ tipo: "inactivo" });
  const [copiado, setCopiado] = useState(false);

  async function generar() {
    setEstado({ tipo: "generando" });
    setCopiado(false);
    try {
      setEstado({ tipo: "listo", resumen: await generarResumenEjecutivo(idLote) });
    } catch (e) {
      setEstado({ tipo: "error", mensaje: mensajeDeError(e) });
    }
  }

  async function copiar(texto: string) {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
    } catch {
      setCopiado(false);
    }
  }

  return (
    <section aria-labelledby="titulo-resumen" className="mt-12">
      <h2 id="titulo-resumen" className="text-lg font-semibold">
        Resumen ejecutivo
      </h2>
      <p className="mt-1 max-w-3xl text-sm text-tinta-suave">
        Un resumen del lote para la gerencia: resultado general, qué transportistas concentran las
        multas y una recomendación. Lo redacta la IA con las cifras calculadas por LogiSLA.
      </p>

      <button
        onClick={generar}
        disabled={estado.tipo === "generando"}
        className={`${BOTON_PRIMARIO} mt-4`}
      >
        {estado.tipo === "generando" && <Spinner />}
        {estado.tipo === "generando"
          ? "Redactando…"
          : estado.tipo === "listo"
            ? "Generar de nuevo"
            : "Generar resumen con IA"}
      </button>

      {estado.tipo === "error" && (
        <div className="mt-5">
          <Aviso titulo="No se pudo generar el resumen">
            <p>{estado.mensaje}</p>
          </Aviso>
        </div>
      )}

      {estado.tipo === "listo" && (
        <div className="mt-5">
          {estado.resumen.origen === "IA" ? (
            <OrigenIA
              etiqueta="Redactado con IA"
              proveedor={estado.resumen.proveedor}
              modelo={estado.resumen.modelo}
              avisoRespaldo={estado.resumen.aviso_respaldo}
              detalle="Cifras calculadas por LogiSLA."
            />
          ) : (
            <Aviso tipo="aviso" titulo="Resumen generado con la plantilla (sin IA)">
              <p>{estado.resumen.motivo_plantilla}</p>
            </Aviso>
          )}

          <div
            data-testid="texto-resumen"
            className={clases(
              "mt-3 max-w-3xl space-y-3 rounded-lg border border-linea bg-superficie",
              "p-5 text-sm leading-relaxed text-tinta sm:text-base",
            )}
          >
            {estado.resumen.texto.split(/\n{2,}/).map((parrafo, i) => (
              <p key={i}>{parrafo}</p>
            ))}
          </div>

          <button
            onClick={() => copiar(estado.resumen.texto)}
            className={`${BOTON_SECUNDARIO} mt-3`}
          >
            {copiado ? "Copiado" : "Copiar texto"}
          </button>
        </div>
      )}
    </section>
  );
}
