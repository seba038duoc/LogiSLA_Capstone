import type { Metadata } from "next";
import { ProveedorEmpresa } from "@/components/EmpresaContext";
import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

/**
 * Diseño raíz de la aplicación: lo comparten todas las páginas.
 *
 * Define el idioma (español de Chile), carga las fuentes, envuelve todo en
 * el proveedor de la empresa activa y pone la cabecera y el pie de página.
 * Cada página (app/page.tsx, app/cargar, app/lotes/[id]) se dibuja en
 * {children}.
 */

/** Título y descripción de la pestaña del navegador. */
export const metadata: Metadata = {
  title: "LogiSLA",
  description: "Auditoría de SLA de transporte: guías fuera de plazo y multas por reclamar",
};

/** Estructura HTML común: <head> con las fuentes y <body> con cabecera, página y pie. */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-CL" className="h-full antialiased">
      <head>
        {/* Fuentes locales del proyecto (Archivo, Inter y Carade):
            ver public/fonts/LEEME.txt. Funcionan sin internet. */}
        <link rel="stylesheet" href="/fonts/fuentes.css" />
        {/* Respaldo: Archivo desde Google Fonts, si falta el archivo local. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..125,400..800&display=swap"
        />
      </head>
      <body className="flex min-h-full flex-col font-sans">
        <ProveedorEmpresa>
          <SiteHeader />
          <div className="flex flex-1 flex-col">{children}</div>
          <footer className="border-t border-linea px-5 py-5 text-center text-xs text-tinta-suave print:hidden">
            LogiSLA, proyecto de título de Ingeniería en Informática, Duoc UC
          </footer>
        </ProveedorEmpresa>
      </body>
    </html>
  );
}
