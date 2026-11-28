/**
 * Une clases de Tailwind escritas en varias líneas o con condiciones.
 *
 * Permite ordenar listas largas de clases en forma vertical, una línea por
 * grupo (tamaño, color, bordes...), y agregar clases solo si se cumple una
 * condición. Los valores falsos (false, null, undefined o "") se ignoran.
 *
 * Ejemplo:
 *   clases(
 *     "rounded-md border px-3 py-2",
 *     "text-sm text-tinta",
 *     activo && "font-semibold",
 *   )
 *   // -> "rounded-md border px-3 py-2 text-sm text-tinta font-semibold" (si activo es true)
 */
export function clases(...partes: Array<string | false | null | undefined>): string {
  return partes.filter(Boolean).join(" ");
}
