/**
 * Descarga de un CSV generado en el navegador.
 *
 * - Separador ";" y BOM UTF-8: así Excel con configuración regional de
 *   Chile lo abre directo en columnas y con los acentos bien.
 * - Los textos que parten con = + - @ se anteponen con un apóstrofo para
 *   que Excel no los interprete como fórmulas (los datos vienen de un
 *   archivo subido por un tercero).
 */

type Celda = string | number;

function escapar(celda: Celda): string {
  if (typeof celda === "number") return String(celda).replace(".", ",");
  let texto = celda;
  if (/^[=+\-@\t\r]/.test(texto)) texto = `'${texto}`;
  return /[";\r\n]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
}

export function descargarCsv(nombreArchivo: string, filas: Celda[][]): void {
  const contenido = "\uFEFF" + filas.map((fila) => fila.map(escapar).join(";")).join("\r\n");
  const url = URL.createObjectURL(new Blob([contenido], { type: "text/csv;charset=utf-8" }));
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreArchivo;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}
