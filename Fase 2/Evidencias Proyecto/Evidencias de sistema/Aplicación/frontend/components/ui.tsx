import type { EstadoLote, ResultadoEnvio } from "@/lib/api";

/* Piezas pequeñas de interfaz que se repiten en todas las pantallas. */

const BASE_BOTON =
  "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60";

export const BOTON_PRIMARIO = `${BASE_BOTON} bg-accion text-sobre-accion hover:bg-accion-fuerte`;
export const BOTON_SECUNDARIO = `${BASE_BOTON} border border-linea bg-superficie text-tinta hover:bg-hundido`;

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={`animate-spin ${className}`} aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" opacity="0.25" />
      <path d="M21 12a9 9 0 00-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

export function Cargando({ texto }: { texto: string }) {
  return (
    <p role="status" className="flex items-center gap-2.5 py-10 text-sm text-tinta-suave">
      <Spinner />
      {texto}
    </p>
  );
}

/**
 * Mensaje destacado. "error" para algo que falló (dice qué pasó y cómo
 * seguir); "aviso" para algo que el usuario debería saber.
 */
export function Aviso({
  tipo = "error",
  titulo,
  children,
}: {
  tipo?: "error" | "aviso";
  titulo: string;
  children?: React.ReactNode;
}) {
  const color = tipo === "error" ? "border-l-incumplido" : "border-l-transito";
  return (
    <div
      role={tipo === "error" ? "alert" : "status"}
      className={`rounded-md border border-linea border-l-4 ${color} bg-superficie px-4 py-3.5`}
    >
      <p className="font-semibold">{titulo}</p>
      {children && <div className="mt-1.5 space-y-3 text-sm text-tinta-suave">{children}</div>}
    </div>
  );
}

const ESTILO_RESULTADO: Record<ResultadoEnvio, { texto: string; clase: string }> = {
  CUMPLIDO: { texto: "En plazo", clase: "bg-cumplido/12 text-cumplido" },
  INCUMPLIDO: { texto: "Fuera de plazo", clase: "bg-incumplido/12 text-incumplido" },
  EN_TRANSITO: { texto: "En tránsito", clase: "bg-transito/12 text-transito" },
  SIN_REGLA: { texto: "Sin regla SLA", clase: "bg-sin-regla/15 text-tinta-suave" },
  PENDIENTE: { texto: "Sin auditar", clase: "border border-linea text-tinta-suave" },
};

export function nombreResultado(resultado: ResultadoEnvio): string {
  return ESTILO_RESULTADO[resultado].texto;
}

export function EtiquetaResultado({ resultado }: { resultado: ResultadoEnvio }) {
  const estilo = ESTILO_RESULTADO[resultado];
  return (
    <span className={`inline-block whitespace-nowrap rounded-sm px-2 py-0.5 text-xs font-semibold ${estilo.clase}`}>
      {estilo.texto}
    </span>
  );
}

const ESTILO_ESTADO: Record<EstadoLote, { texto: string; clase: string }> = {
  PENDIENTE: { texto: "Sin auditar", clase: "border border-linea text-tinta-suave" },
  PROCESANDO: { texto: "Auditando", clase: "bg-transito/12 text-transito" },
  COMPLETADO: { texto: "Auditado", clase: "bg-accion/10 text-tinta" },
  FALLIDO: { texto: "Falló", clase: "bg-incumplido/12 text-incumplido" },
};

export function EtiquetaEstadoLote({ estado }: { estado: EstadoLote }) {
  const estilo = ESTILO_ESTADO[estado] ?? ESTILO_ESTADO.PENDIENTE;
  return (
    <span className={`inline-block whitespace-nowrap rounded-sm px-2 py-0.5 text-xs font-semibold ${estilo.clase}`}>
      {estilo.texto}
    </span>
  );
}
