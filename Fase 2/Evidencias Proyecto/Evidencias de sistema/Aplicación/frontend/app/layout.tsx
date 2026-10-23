import type { Metadata } from "next";
import { ProveedorEmpresa } from "@/components/EmpresaContext";
import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

export const metadata: Metadata = {
  title: "LogiSLA",
  description: "Auditoría de SLA de transporte: guías fuera de plazo y multas por reclamar",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-CL" className="h-full antialiased">
      <head>
        {/* Tipografía Archivo (variable: peso y ancho). Si no hay internet
            el sitio funciona igual con la fuente del sistema. */}
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
          <footer className="border-t border-linea px-5 py-5 text-center text-xs text-tinta-suave">
            LogiSLA, proyecto de título de Ingeniería en Informática, Duoc UC
          </footer>
        </ProveedorEmpresa>
      </body>
    </html>
  );
}
