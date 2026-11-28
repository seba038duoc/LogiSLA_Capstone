"use client";

import { useRef, useState } from "react";
import { Aviso, BOTON_PRIMARIO, BOTON_SECUNDARIO, Spinner } from "@/components/ui";
import { OrigenIA } from "@/components/OrigenIA";
import {
  CartaReclamo as Carta,
  FilaTransportista,
  generarCartaReclamo,
  mensajeDeError,
} from "@/lib/api";
import { guias, pesos } from "@/lib/formato";
import { clases } from "@/lib/clases";

/**
 * Carta de reclamo al transportista (IA generativa, Sprint 5).
 *
 * El backend le pide a Gemini (o, si no está disponible, a Claude) que
 * redacte el cuerpo de la carta con los resultados de la auditoría. Si
 * ninguna IA responde, usa una plantilla y lo informa en `motivo_plantilla`. Montos, encabezado y
 * anexo guía por guía siempre los pone LogiSLA, no la IA.
 */

type Estado =
  | { tipo: "inactivo" }
  | { tipo: "generando" }
  | { tipo: "error"; mensaje: string }
  | { tipo: "listo"; carta: Carta };

/**
 * Sección "Carta de reclamo": elegir transportista, generar la carta,
 * mostrar si la redactó la IA o la plantilla, y copiarla o descargarla.
 */
export function CartaReclamo({
  idLote,
  transportistas,
}: {
  idLote: string;
  transportistas: FilaTransportista[]; // solo los que tienen guías fuera de plazo
}) {
  const [seleccionado, setSeleccionado] = useState(transportistas[0]?.nombre ?? "");
  const [estado, setEstado] = useState<Estado>({ tipo: "inactivo" });
  const [copiado, setCopiado] = useState(false);
  const areaTexto = useRef<HTMLTextAreaElement>(null);

  if (transportistas.length === 0) return null;
  const fila = transportistas.find((t) => t.nombre === seleccionado) ?? transportistas[0];

  async function generar() {
    setEstado({ tipo: "generando" });
    setCopiado(false);
    try {
      const carta = await generarCartaReclamo(idLote, fila.nombre);
      setEstado({ tipo: "listo", carta });
    } catch (e) {
      setEstado({ tipo: "error", mensaje: mensajeDeError(e) });
    }
  }

  async function copiar(texto: string) {
    try {
      await navigator.clipboard.writeText(texto);
    } catch {
      // Respaldo si el navegador no permite el portapapeles: seleccionar y copiar.
      areaTexto.current?.select();
      document.execCommand("copy");
    }
    setCopiado(true);
  }

  function descargar(carta: Carta) {
    const nombre = `carta_reclamo_${carta.transportista}`
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "") // quita tildes: "Peñaflor" -> "Penaflor"
      .replace(/[^A-Za-z0-9_-]+/g, "_");
    // BOM y saltos de línea de Windows para que el Bloc de notas lo abra bien.
    const contenido = "﻿" + carta.texto.replace(/\r?\n/g, "\r\n");
    const url = URL.createObjectURL(new Blob([contenido], { type: "text/plain;charset=utf-8" }));
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = `${nombre}.txt`;
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <section aria-labelledby="titulo-carta" className="mt-12">
      <h2 id="titulo-carta" className="text-lg font-semibold">
        Carta de reclamo
      </h2>
      <p className="mt-1 max-w-3xl text-sm text-tinta-suave">
        La IA (Gemini o Claude) redacta la carta con los resultados de esta auditoría. Los montos,
        las fechas y el anexo guía por guía los pone LogiSLA, no la IA. Revisa la carta antes de
        enviarla.
      </p>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="carta-transportista" className="block text-sm font-medium">
            Transportista
          </label>
          <select
            id="carta-transportista"
            value={fila.nombre}
            onChange={(e) => {
              setSeleccionado(e.target.value);
              setEstado({ tipo: "inactivo" });
              setCopiado(false);
            }}
            disabled={estado.tipo === "generando"}
            className={clases(
              "mt-1 rounded-md border border-linea bg-superficie px-3 py-2.5 text-sm",
              "text-tinta",
            )}
          >
            {transportistas.map((t) => (
              <option key={t.nombre} value={t.nombre}>
                {t.nombre}: {guias(t.conteos.incumplidos)}, {pesos(t.conteos.monto_multa_total)}
              </option>
            ))}
          </select>
        </div>
        <button onClick={generar} disabled={estado.tipo === "generando"} className={BOTON_PRIMARIO}>
          {estado.tipo === "generando" && <Spinner />}
          {estado.tipo === "generando"
            ? "Redactando…"
            : estado.tipo === "listo"
              ? "Generar de nuevo"
              : "Generar carta con IA"}
        </button>
      </div>

      {estado.tipo === "error" && (
        <div className="mt-5">
          <Aviso titulo="No se pudo generar la carta">
            <p>{estado.mensaje}</p>
          </Aviso>
        </div>
      )}

      {estado.tipo === "listo" && (
        <div className="mt-5">
          {estado.carta.origen === "IA" ? (
            <OrigenIA
              etiqueta="Redactada con IA"
              proveedor={estado.carta.proveedor}
              modelo={estado.carta.modelo}
              avisoRespaldo={estado.carta.aviso_respaldo}
              detalle="Cifras y anexo calculados por LogiSLA."
            />
          ) : (
            <Aviso tipo="aviso" titulo="Carta generada con la plantilla (sin IA)">
              <p>{estado.carta.motivo_plantilla}</p>
              <p>Las cifras y el anexo son los mismos: la carta se puede usar igual.</p>
            </Aviso>
          )}

          <label htmlFor="carta-texto" className="sr-only">
            Texto de la carta
          </label>
          <textarea
            id="carta-texto"
            ref={areaTexto}
            readOnly
            value={estado.carta.texto}
            rows={28}
            className={clases(
              "mt-3 w-full rounded-lg border border-linea bg-superficie p-4 font-mono",
              "text-xs leading-relaxed text-tinta sm:text-sm",
            )}
          />

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button onClick={() => copiar(estado.carta.texto)} className={BOTON_SECUNDARIO}>
              {copiado ? "Copiado" : "Copiar texto"}
            </button>
            <button onClick={() => descargar(estado.carta)} className={BOTON_SECUNDARIO}>
              Descargar (.txt)
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
