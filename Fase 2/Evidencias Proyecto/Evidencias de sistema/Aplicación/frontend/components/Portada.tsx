"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { clases } from "@/lib/clases";

/**
 * Portada de la página de inicio: carrusel con fotos y accesos rápidos.
 *
 * Fotos: van en frontend/public/portada/ con los nombres de DIAPOSITIVAS
 * (portada-1.jpg, portada-2.jpg, portada-3.jpg). Si una foto falta, la
 * diapositiva se muestra igual con el fondo azul de la marca.
 *
 * Accesibilidad: avanza sola cada 7 segundos, pero se detiene al pasar el
 * mouse o el teclado por encima, tiene botón de pausa, flechas y puntos, y
 * no avanza sola si el sistema pide reducir animaciones.
 */

type Diapositiva = {
  foto: string;
  descripcionFoto: string; // texto alternativo de la foto
  posicionFoto: string; // qué parte de la foto se prioriza al recortar (CSS object-position)
  antetitulo: string;
  titulo: string;
  texto: string;
  accion: { texto: string; href: string };
};

const DIAPOSITIVAS: Diapositiva[] = [
  {
    foto: "/portada/portada-1.jpg",
    descripcionFoto: "Equipo de bodega revisando envíos en un notebook",
    posicionFoto: "50% 22%",
    antetitulo: "Auditoría de SLA",
    titulo: "Audita a tus transportistas en minutos",
    texto:
      "Sube la planilla de guías del período y LogiSLA revisa cada entrega en horas hábiles, " +
      "con feriados chilenos incluidos.",
    accion: { texto: "Cargar envíos", href: "/cargar" },
  },
  {
    foto: "/portada/portada-2.jpg",
    descripcionFoto: "Supervisora de bodega revisando indicadores en un notebook",
    posicionFoto: "50% 30%",
    antetitulo: "Multas calculadas",
    titulo: "Cada atraso, con su multa",
    texto:
      "Ve por transportista cuántas guías llegaron fuera de plazo y cuánto corresponde reclamar.",
    accion: { texto: "Ver lotes", href: "#lotes" },
  },
  {
    foto: "/portada/portada-3.jpg",
    descripcionFoto:
      "Encargada de logística escribiendo en su notebook mientras " +
      "un compañero revisa cajas con un escáner",
    posicionFoto: "50% 5%",
    antetitulo: "IA generativa",
    titulo: "Reclama con una carta lista para enviar",
    texto:
      "La IA redacta la carta de reclamo y LogiSLA adjunta el detalle guía por guía con los " +
      "montos exactos.",
    accion: { texto: "Ver lotes", href: "#lotes" },
  },
];

const INTERVALO_MS = 7000;

/**
 * Carrusel de la portada: muestra una diapositiva a la vez, avanza solo
 * cada 7 segundos y se controla con flechas, puntos, teclado y "Pausar".
 */
export function Portada() {
  const [actual, setActual] = useState(0);
  const [pausadoPorUsuario, setPausadoPorUsuario] = useState(false);
  const [encima, setEncima] = useState(false); // mouse o foco dentro del carrusel
  const [reducirMovimiento, setReducirMovimiento] = useState(false);
  const [fotosConError, setFotosConError] = useState<Set<number>>(new Set());

  const total = DIAPOSITIVAS.length;
  const ir = useCallback((indice: number) => setActual((indice + total) % total), [total]);

  useEffect(() => {
    const consulta = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReducirMovimiento(consulta.matches);
    const alCambiar = (e: MediaQueryListEvent) => setReducirMovimiento(e.matches);
    consulta.addEventListener("change", alCambiar);
    return () => consulta.removeEventListener("change", alCambiar);
  }, []);

  const avanzaSola = !pausadoPorUsuario && !encima && !reducirMovimiento;
  useEffect(() => {
    if (!avanzaSola) return;
    const temporizador = window.setTimeout(() => setActual((n) => (n + 1) % total), INTERVALO_MS);
    return () => window.clearTimeout(temporizador);
  }, [avanzaSola, actual, total]);

  return (
    <section
      aria-roledescription="carrusel"
      aria-label="Qué hace LogiSLA"
      className="portada"
      onMouseEnter={() => setEncima(true)}
      onMouseLeave={() => setEncima(false)}
      onFocus={() => setEncima(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setEncima(false);
      }}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight") ir(actual + 1);
        if (e.key === "ArrowLeft") ir(actual - 1);
      }}
    >
      <div className="portada-escenario">
        {DIAPOSITIVAS.map((d, i) => {
          const visible = i === actual;
          return (
            <div
              key={d.foto}
              role="group"
              aria-roledescription="diapositiva"
              aria-label={`${i + 1} de ${total}: ${d.titulo}`}
              aria-hidden={!visible}
              className={`portada-diapositiva ${visible ? "es-visible" : ""}`}
            >
              <div className="portada-foto">
                {!fotosConError.has(i) && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={d.foto}
                    alt={d.descripcionFoto}
                    style={{ objectPosition: d.posicionFoto }}
                    loading={i === 0 ? "eager" : "lazy"}
                    onError={() => setFotosConError((previo) => new Set(previo).add(i))}
                  />
                )}
              </div>

              <div className="portada-panel">
                <div className="portada-texto">
                  <p className="portada-antetitulo text-brand-300">{d.antetitulo}</p>
                  <h2 className="portada-titulo mt-3 text-white">{d.titulo}</h2>
                  <p className="mt-4 max-w-md text-base text-brand-100 sm:text-lg">{d.texto}</p>
                  <Link
                    href={d.accion.href}
                    tabIndex={visible ? 0 : -1}
                    className={clases(
                      "mt-7 inline-flex items-center gap-2 rounded-full bg-white px-6 py-3",
                      "text-sm font-bold text-brand-950 shadow-lg transition-transform",
                      "hover:-translate-y-0.5",
                    )}
                  >
                    {d.accion.texto}
                    <span aria-hidden="true">→</span>
                  </Link>
                </div>
              </div>
            </div>
          );
        })}

        <button
          type="button"
          onClick={() => ir(actual - 1)}
          className="portada-flecha left-4"
          aria-label="Diapositiva anterior"
        >
          <Flecha direccion="izquierda" />
        </button>
        <button
          type="button"
          onClick={() => ir(actual + 1)}
          className="portada-flecha right-4"
          aria-label="Diapositiva siguiente"
        >
          <Flecha direccion="derecha" />
        </button>

        <div className="portada-controles">
          {DIAPOSITIVAS.map((d, i) => (
            <button
              key={d.foto}
              type="button"
              onClick={() => ir(i)}
              aria-label={`Ir a la diapositiva ${i + 1}`}
              aria-current={i === actual ? "true" : undefined}
              className={`portada-punto ${i === actual ? "es-actual" : ""}`}
            />
          ))}
          <button
            type="button"
            onClick={() => setPausadoPorUsuario((p) => !p)}
            className={clases(
              "ml-2 rounded-full px-2 py-0.5 text-xs font-semibold text-brand-100",
              "hover:bg-white/10",
            )}
          >
            {pausadoPorUsuario ? "Reanudar" : "Pausar"}
          </button>
        </div>
      </div>

      <AccesosRapidos />
    </section>
  );
}

/** Barra de accesos rápidos bajo el carrusel: cargar envíos, ver lotes y planilla de ejemplo. */
function AccesosRapidos() {
  const accesos = [
    { texto: "Cargar envíos", detalle: "CSV o Excel", href: "/cargar", icono: <IconoSubir /> },
    { texto: "Ver lotes", detalle: "Resultados y multas", href: "#lotes", icono: <IconoLista /> },
    {
      texto: "Planilla de ejemplo",
      detalle: "Descargar CSV de prueba",
      href: "/ejemplos/envios_piloto.csv",
      icono: <IconoDescargar />,
      descarga: true,
    },
  ];
  return (
    <nav aria-label="Accesos rápidos" className="portada-accesos">
      {accesos.map((a) => {
        const contenido = (
          <>
            <span className="text-brand-500 dark:text-brand-300">{a.icono}</span>
            <span>
              <span className="block font-semibold text-tinta">{a.texto}</span>
              <span className="block text-xs text-tinta-suave">{a.detalle}</span>
            </span>
          </>
        );
        const clase = "portada-acceso";
        return a.descarga ? (
          <a key={a.texto} href={a.href} download className={clase}>
            {contenido}
          </a>
        ) : (
          <Link key={a.texto} href={a.href} className={clase}>
            {contenido}
          </Link>
        );
      })}
    </nav>
  );
}

/* --------------------------------- Íconos -------------------------------- */

/** Ícono de flecha para los botones anterior/siguiente del carrusel. */
function Flecha({ direccion }: { direccion: "izquierda" | "derecha" }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden="true">
      <path
        d={direccion === "izquierda" ? "M15 5l-7 7 7 7" : "M9 5l7 7-7 7"}
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Propiedades comunes de los íconos de línea de los accesos rápidos. */
const PROPS_ICONO = {
  viewBox: "0 0 24 24",
  className: "h-7 w-7",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

/** Ícono "subir archivo". */
function IconoSubir() {
  return (
    <svg {...PROPS_ICONO}>
      <path d="M12 16V4M7 9l5-5 5 5" />
      <path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
    </svg>
  );
}

/** Ícono "lista de lotes". */
function IconoLista() {
  return (
    <svg {...PROPS_ICONO}>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </svg>
  );
}

/** Ícono "descargar". */
function IconoDescargar() {
  return (
    <svg {...PROPS_ICONO}>
      <path d="M12 4v12M7 11l5 5 5-5" />
      <path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
    </svg>
  );
}
