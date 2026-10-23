/**
 * Logo de LogiSLA: una "L" cuya base es la franja de cumplimiento
 * (verde = en plazo, ámbar = en tránsito, rojo = fuera de plazo), la
 * misma franja que se usa en todas las pantallas.
 *
 * SVG en línea, sin dependencias. El trazo de la L usa currentColor, así
 * que toma el color del texto donde se ponga (blanco en la cabecera).
 * Los tres colores de la franja son fijos: son parte de la marca.
 *
 * Los archivos equivalentes para usar fuera de la app (informe,
 * presentación) están en public/: logo-logisla.svg, logo-logisla-claro.svg
 * y logo-logisla-icono.svg. El ícono de la pestaña es app/icon.svg.
 */
export function LogoMark({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg viewBox="18 14 64 68" className={className} aria-hidden="true">
      <rect x="24" y="20" width="14" height="56" rx="2" fill="currentColor" />
      <rect x="42" y="62" width="16" height="14" rx="2" fill="#4ccfa3" />
      <rect x="61" y="62" width="6" height="14" rx="2" fill="#f2b552" />
      <rect x="70" y="62" width="6" height="14" rx="2" fill="#ff8d80" />
    </svg>
  );
}

export function LogoWordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <LogoMark />
      <span className="text-lg tracking-tight" style={{ fontStretch: "112%" }}>
        <span className="font-medium">Logi</span>
        <span className="font-extrabold">SLA</span>
      </span>
    </span>
  );
}
