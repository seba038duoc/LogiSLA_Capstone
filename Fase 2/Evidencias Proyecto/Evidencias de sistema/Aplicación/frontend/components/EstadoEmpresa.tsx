"use client";

import { useEmpresa } from "@/components/EmpresaContext";
import { Aviso, BOTON_SECUNDARIO, Cargando } from "@/components/ui";
import type { Empresa } from "@/lib/api";

/**
 * Envuelve una pantalla que necesita una empresa activa. Resuelve en un
 * solo lugar los tres casos en que todavía no la hay: se está cargando,
 * el backend no responde, o no existe ninguna empresa creada.
 */
export function ConEmpresa({ children }: { children: (empresa: Empresa) => React.ReactNode }) {
  const { empresa, cargando, error, reintentar } = useEmpresa();

  if (cargando) return <Cargando texto="Conectando con LogiSLA…" />;

  if (error) {
    return (
      <Aviso titulo="No se pudo conectar con LogiSLA">
        <p>{error}</p>
        <button onClick={reintentar} className={BOTON_SECUNDARIO}>
          Reintentar
        </button>
      </Aviso>
    );
  }

  if (!empresa) {
    return (
      <Aviso tipo="aviso" titulo="Todavía no hay ninguna empresa creada">
        <p>
          Crea una desde la carpeta <code>backend</code> con{" "}
          <code>python scripts/seed_pilot_company.py &quot;Nombre de la empresa&quot;</code> y luego recarga
          esta página. Si usas <code>iniciar.bat</code>, la empresa de prueba se crea sola.
        </p>
        <button onClick={reintentar} className={BOTON_SECUNDARIO}>
          Volver a buscar
        </button>
      </Aviso>
    );
  }

  return <>{children(empresa)}</>;
}
