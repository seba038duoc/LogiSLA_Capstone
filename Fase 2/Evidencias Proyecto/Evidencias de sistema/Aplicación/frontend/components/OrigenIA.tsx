import { clases } from "@/lib/clases";

/**
 * Línea que indica qué IA redactó un texto (carta de reclamo o resumen
 * ejecutivo): la etiqueta "Redactada con IA", el proveedor (Gemini o
 * Claude) y el modelo. Si redactó la IA de respaldo porque la principal no
 * estuvo disponible (por ejemplo, sin cuota), lo explica debajo.
 */
export function OrigenIA({
  etiqueta,
  proveedor,
  modelo,
  avisoRespaldo,
  detalle,
}: {
  etiqueta: string;
  proveedor: string | null;
  modelo: string | null;
  avisoRespaldo: string | null;
  detalle: string;
}) {
  return (
    <div role="status" className="text-sm text-tinta-suave">
      <p>
        <span
          className={clases(
            "inline-block rounded-sm bg-accion/10 px-2 py-0.5",
            "text-xs font-semibold text-tinta",
          )}
        >
          {etiqueta}
          {proveedor && ` · ${proveedor}`}
        </span>{" "}
        Modelo {modelo}. {detalle}
      </p>
      {avisoRespaldo && (
        <p className="mt-1 text-xs">
          Redactó {proveedor}, la IA de respaldo. {avisoRespaldo}
        </p>
      )}
    </div>
  );
}
