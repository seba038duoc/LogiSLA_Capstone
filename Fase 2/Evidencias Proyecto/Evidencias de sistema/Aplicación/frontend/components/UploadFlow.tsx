"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Aviso, BOTON_PRIMARIO, BOTON_SECUNDARIO, Spinner } from "@/components/ui";
import { auditarLote, cargarLoteAuditoria, Empresa, mensajeDeError, RespuestaCarga } from "@/lib/api";
import { guias } from "@/lib/formato";

/**
 * Carga de envíos:
 *   1. Se elige (o se arrastra) un CSV/Excel            -> POST /cargar
 *   2. Se muestra qué columna del archivo se usó para cada dato.
 *   3. "Auditar lote" corre el motor                     -> POST /auditar
 *      y lleva al detalle del lote con los resultados.
 *
 * Si el backend no reconoce alguna columna obligatoria rechaza la carga
 * (400) y aquí se muestra el motivo junto con los nombres de columna que
 * sí se aceptan. No hay mapeo manual: se corrige el archivo y se vuelve a
 * subir.
 */

const EXTENSIONES = [".csv", ".xlsx", ".xls"];

/** Nombre legible de cada campo interno + ejemplos de encabezados válidos. */
const CAMPOS: { clave: string; nombre: string; obligatorio: boolean; ejemplos: string }[] = [
  { clave: "numero_guia", nombre: "N° de guía", obligatorio: true, ejemplos: "N° Guía, Tracking, Código Envío" },
  { clave: "nombre_transportista", nombre: "Transportista", obligatorio: true, ejemplos: "Transportista, Courier, Operador" },
  { clave: "fecha_despacho", nombre: "Fecha de despacho", obligatorio: true, ejemplos: "Fecha Despacho, Fecha Envío, Fecha Salida" },
  { clave: "fecha_entrega", nombre: "Fecha de entrega", obligatorio: false, ejemplos: "Fecha Entrega, Fecha Recepción" },
  { clave: "destino", nombre: "Destino", obligatorio: false, ejemplos: "Destino, Comuna Destino, Ciudad Destino" },
  { clave: "valor_declarado", nombre: "Valor declarado", obligatorio: false, ejemplos: "Valor Declarado, Monto Envío" },
];

type Paso =
  | { tipo: "eligiendo"; error?: string }
  | { tipo: "subiendo" }
  | { tipo: "cargado"; resultado: RespuestaCarga; auditando: boolean; error?: string };

function extensionValida(nombre: string): boolean {
  return EXTENSIONES.some((ext) => nombre.toLowerCase().endsWith(ext));
}

export default function UploadFlow({ empresa }: { empresa: Empresa }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [arrastrando, setArrastrando] = useState(false);
  const [paso, setPaso] = useState<Paso>({ tipo: "eligiendo" });

  function elegirArchivo(nuevo: File | null | undefined) {
    if (!nuevo) return;
    if (!extensionValida(nuevo.name)) {
      setArchivo(null);
      setPaso({
        tipo: "eligiendo",
        error: `"${nuevo.name}" no es un archivo CSV ni Excel. Usa un archivo .csv, .xlsx o .xls.`,
      });
      return;
    }
    setArchivo(nuevo);
    setPaso({ tipo: "eligiendo" });
  }

  async function subir() {
    if (!archivo) return;
    setPaso({ tipo: "subiendo" });
    try {
      const resultado = await cargarLoteAuditoria(empresa.id, archivo);
      setPaso({ tipo: "cargado", resultado, auditando: false });
    } catch (error) {
      setPaso({ tipo: "eligiendo", error: mensajeDeError(error) });
    }
  }

  async function auditar(resultado: RespuestaCarga) {
    setPaso({ tipo: "cargado", resultado, auditando: true });
    try {
      await auditarLote(resultado.lote_id);
      router.push(`/lotes/${resultado.lote_id}`);
    } catch (error) {
      setPaso({ tipo: "cargado", resultado, auditando: false, error: mensajeDeError(error) });
    }
  }

  function reiniciar() {
    setArchivo(null);
    setPaso({ tipo: "eligiendo" });
  }

  /* ----------------------------- Cargado ------------------------------ */

  if (paso.tipo === "cargado") {
    const { resultado } = paso;
    const ambiguas = Object.entries(resultado.advertencias_ambiguas ?? {});
    return (
      <div className="max-w-3xl">
        <h1 className="titular text-3xl sm:text-4xl">{guias(resultado.total_filas)} cargadas, listas para auditar</h1>
        <p className="mt-3 text-tinta-suave">
          Archivo <span className="font-medium text-tinta">{resultado.nombre_archivo}</span>, empresa{" "}
          {empresa.nombre}. Revisa que cada dato se haya leído de la columna correcta antes de auditar.
        </p>

        <div className="mt-6 overflow-x-auto rounded-lg border border-linea bg-superficie">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-linea text-tinta-suave">
                <th scope="col" className="px-4 py-3 font-medium">Dato</th>
                <th scope="col" className="px-4 py-3 font-medium">Columna de tu archivo</th>
              </tr>
            </thead>
            <tbody>
              {CAMPOS.map((campo) => {
                const columna = resultado.mapeo_columnas?.[campo.clave];
                return (
                  <tr key={campo.clave} className="border-b border-linea last:border-b-0">
                    <th scope="row" className="px-4 py-2.5 font-medium">{campo.nombre}</th>
                    <td className={`px-4 py-2.5 ${columna ? "" : "text-tinta-suave"}`}>
                      {columna ?? "No viene en el archivo (opcional)"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {!resultado.mapeo_columnas?.fecha_entrega && (
          <div className="mt-4">
            <Aviso tipo="aviso" titulo="El archivo no trae fecha de entrega">
              <p>
                Sin fecha de entrega no se puede calcular el atraso: todas las guías quedarán como
                “en tránsito”.
              </p>
            </Aviso>
          </div>
        )}

        {ambiguas.length > 0 && (
          <div className="mt-4">
            <Aviso tipo="aviso" titulo="Hay columnas que se parecen entre sí">
              <ul className="list-disc space-y-1 pl-5">
                {ambiguas.map(([campo, columnas]) => (
                  <li key={campo}>
                    {CAMPOS.find((c) => c.clave === campo)?.nombre ?? campo}: también podrían ser{" "}
                    {columnas.join(", ")}.
                  </li>
                ))}
              </ul>
            </Aviso>
          </div>
        )}

        {paso.error && (
          <div className="mt-4">
            <Aviso titulo="No se pudo auditar el lote">
              <p>{paso.error}</p>
            </Aviso>
          </div>
        )}

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button onClick={() => auditar(resultado)} disabled={paso.auditando} className={BOTON_PRIMARIO}>
            {paso.auditando && <Spinner />}
            {paso.auditando ? "Auditando…" : "Auditar lote"}
          </button>
          <Link href={`/lotes/${resultado.lote_id}`} className={BOTON_SECUNDARIO}>
            Ver lote sin auditar
          </Link>
          <button onClick={reiniciar} disabled={paso.auditando} className={BOTON_SECUNDARIO}>
            Cargar otro archivo
          </button>
        </div>
      </div>
    );
  }

  /* ----------------------- Eligiendo / subiendo ----------------------- */

  const subiendo = paso.tipo === "subiendo";
  const error = paso.tipo === "eligiendo" ? paso.error : undefined;

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <section>
        <h1 className="titular text-3xl sm:text-4xl">Cargar envíos</h1>
        <p className="mt-3 max-w-xl text-tinta-suave">
          Sube la planilla de guías del período para {empresa.nombre}. Las columnas se reconocen
          automáticamente por su nombre.
        </p>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            if (!subiendo) setArrastrando(true);
          }}
          onDragLeave={() => setArrastrando(false)}
          onDrop={(e) => {
            e.preventDefault();
            setArrastrando(false);
            if (!subiendo) elegirArchivo(e.dataTransfer.files?.[0]);
          }}
          className={`mt-6 rounded-lg border-2 border-dashed px-5 py-10 text-center transition-colors ${
            arrastrando ? "border-foco bg-foco/8" : "border-linea bg-superficie"
          }`}
        >
          {archivo ? (
            <>
              <p className="break-all font-semibold">{archivo.name}</p>
              <p className="mt-1 text-sm text-tinta-suave">
                {(archivo.size / 1024).toLocaleString("es-CL", { maximumFractionDigits: 0 })} KB
              </p>
            </>
          ) : (
            <>
              <p className="font-semibold">Arrastra el archivo aquí</p>
              <p className="mt-1 text-sm text-tinta-suave">CSV, XLSX o XLS</p>
            </>
          )}
          <input
            ref={inputRef}
            id="archivo-envios"
            type="file"
            accept={EXTENSIONES.join(",")}
            disabled={subiendo}
            onChange={(e) => {
              elegirArchivo(e.target.files?.[0]);
              e.target.value = ""; // permite volver a elegir el mismo archivo tras corregirlo
            }}
            className="peer sr-only"
          />
          <label
            htmlFor="archivo-envios"
            className={`${BOTON_SECUNDARIO} mt-4 ${subiendo ? "pointer-events-none opacity-60" : "cursor-pointer"} peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-foco`}
          >
            {archivo ? "Elegir otro archivo" : "Elegir archivo"}
          </label>
        </div>

        {error && (
          <div className="mt-4">
            <Aviso titulo="No se pudo cargar el archivo">
              <p className="break-words">{error}</p>
            </Aviso>
          </div>
        )}

        <button onClick={subir} disabled={!archivo || subiendo} className={`${BOTON_PRIMARIO} mt-6`}>
          {subiendo && <Spinner />}
          {subiendo ? "Cargando envíos…" : "Cargar envíos"}
        </button>
      </section>

      <aside aria-labelledby="titulo-columnas" className="lg:pt-2">
        <h2 id="titulo-columnas" className="font-semibold">
          Columnas que debe traer el archivo
        </h2>
        <p className="mt-1 text-sm text-tinta-suave">
          No importan las mayúsculas ni los acentos. Estos son algunos nombres que se reconocen:
        </p>
        <dl className="mt-4 divide-y divide-linea border-y border-linea text-sm">
          {CAMPOS.map((campo) => (
            <div key={campo.clave} className="py-2.5">
              <dt className="font-medium">
                {campo.nombre}
                {!campo.obligatorio && <span className="font-normal text-tinta-suave"> (opcional)</span>}
              </dt>
              <dd className="text-tinta-suave">{campo.ejemplos}</dd>
            </div>
          ))}
        </dl>
      </aside>
    </div>
  );
}
