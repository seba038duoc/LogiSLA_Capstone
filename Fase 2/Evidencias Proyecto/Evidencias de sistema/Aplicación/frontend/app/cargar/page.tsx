"use client";

import UploadFlow from "@/components/UploadFlow";
import { ConEmpresa } from "@/components/EstadoEmpresa";

/**
 * Página "Cargar envíos" (ruta /cargar).
 *
 * Solo arma el contenedor de la página: el flujo completo de carga (elegir
 * archivo, revisar columnas y auditar) está en components/UploadFlow.tsx.
 * <ConEmpresa> espera a que haya una empresa elegida antes de mostrarlo.
 */

/** Contenedor de la página con el flujo de carga de la empresa activa. */
export default function PaginaCargar() {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-10">
      <ConEmpresa>{(empresa) => <UploadFlow key={empresa.id} empresa={empresa} />}</ConEmpresa>
    </main>
  );
}
