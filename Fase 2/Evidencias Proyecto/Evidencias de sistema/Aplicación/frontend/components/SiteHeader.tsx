"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEmpresa } from "@/components/EmpresaContext";
import { LogoWordmark } from "@/components/Logo";

const ENLACES = [
  { href: "/", texto: "Lotes" },
  { href: "/cargar", texto: "Cargar envíos" },
];

function estaActivo(ruta: string, href: string): boolean {
  if (href === "/") return ruta === "/" || ruta.startsWith("/lotes");
  return ruta.startsWith(href);
}

/**
 * Cabecera del sitio: marca, navegación y empresa activa. Es azul marino
 * tanto en modo claro como oscuro (es el color de la marca).
 */
export function SiteHeader() {
  const ruta = usePathname() ?? "/";
  const { empresas, empresa, elegirEmpresa } = useEmpresa();

  return (
    <header className="bg-brand-950 text-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-2 px-5 py-3">
        <Link href="/" className="rounded-sm" aria-label="LogiSLA, ir a Lotes">
          <LogoWordmark />
        </Link>

        <nav aria-label="Principal" className="flex items-center gap-1">
          {ENLACES.map((enlace) => {
            const activo = estaActivo(ruta, enlace.href);
            return (
              <Link
                key={enlace.href}
                href={enlace.href}
                aria-current={activo ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  activo ? "bg-white/12 text-white" : "text-brand-200 hover:bg-white/8 hover:text-white"
                }`}
              >
                {enlace.texto}
              </Link>
            );
          })}
        </nav>

        {empresa && (
          <div className="ml-auto flex min-w-0 items-center gap-2 text-sm">
            <label htmlFor="empresa-activa" className="shrink-0 text-brand-300">
              Empresa
            </label>
            {empresas.length > 1 ? (
              <select
                id="empresa-activa"
                value={empresa.id}
                onChange={(e) => elegirEmpresa(e.target.value)}
                className="max-w-56 truncate rounded-md border border-white/20 bg-brand-900 px-2.5 py-1.5 font-medium text-white"
              >
                {empresas.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.nombre}
                  </option>
                ))}
              </select>
            ) : (
              <span id="empresa-activa" className="truncate font-medium">
                {empresa.nombre}
              </span>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
