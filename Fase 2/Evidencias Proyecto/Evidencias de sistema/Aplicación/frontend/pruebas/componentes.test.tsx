/**
 * Pruebas de componentes del frontend: se dibujan a HTML con React (sin
 * navegador) y se revisa que muestren lo que el usuario necesita ver.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { CriteriosAuditoria } from "@/components/CriteriosAuditoria";
import { DetalleGuia } from "@/components/DetalleGuia";
import { FranjaCumplimiento, LeyendaFranja } from "@/components/Franja";
import { GraficosTransportistas } from "@/components/GraficosTransportistas";
import { OrigenIA } from "@/components/OrigenIA";
import { EtiquetaResultado, nombreResultado } from "@/components/ui";
import type { Conteos, ResultadoEnvio } from "@/lib/api";
import { clases } from "@/lib/clases";
import { fila, guia } from "./datos";

/** HTML del componente, con los espacios especiales normalizados. */
const html = (elemento: React.ReactElement) => renderToStaticMarkup(elemento).replace(/[  ]/g, " ");

describe("etiquetas de resultado", () => {
  it("cada resultado tiene un nombre claro para el usuario", () => {
    const esperados: Record<ResultadoEnvio, string> = {
      CUMPLIDO: "En plazo",
      INCUMPLIDO: "Fuera de plazo",
      EN_TRANSITO: "En tránsito",
      VENCIDA_SIN_ENTREGA: "Vencida sin entrega",
      SIN_REGLA: "Sin regla SLA",
      DATOS_INVALIDOS: "Datos a revisar",
      PENDIENTE: "Sin auditar",
    };
    for (const [resultado, texto] of Object.entries(esperados)) {
      assert.equal(nombreResultado(resultado as ResultadoEnvio), texto);
      assert.match(
        html(<EtiquetaResultado resultado={resultado as ResultadoEnvio} />),
        new RegExp(texto),
      );
    }
  });
});

describe("franja de cumplimiento", () => {
  const c: Conteos = {
    total: 60,
    cumplidos: 36,
    incumplidos: 13,
    en_transito: 0,
    vencidas_sin_entrega: 11,
    sin_regla: 0,
    datos_invalidos: 0,
    pendientes: 0,
    monto_multa_total: 170000,
  };

  it("se describe en palabras para lectores de pantalla", () => {
    assert.match(
      html(<FranjaCumplimiento conteos={c} />),
      /aria-label="36 en plazo, 13 fuera de plazo, 11 vencidas sin entrega"/,
    );
  });

  it("la leyenda muestra solo las categorías con guías", () => {
    const leyenda = html(<LeyendaFranja conteos={c} />);
    assert.match(leyenda, /vencidas sin entrega/);
    assert.doesNotMatch(leyenda, /en tránsito|sin regla/);
  });
});

describe("detalle del cálculo de una guía", () => {
  it("muestra la justificación, si llegó, la fecha límite y los feriados", () => {
    const texto = html(<DetalleGuia envio={guia()} />);
    assert.match(texto, /después de la fecha límite \(29-09-2026 15:00\)/);
    assert.match(texto, /Sí, 30-09-2026 18:00/);
    assert.match(texto, /72 h de 60 h permitidas/);
    assert.match(texto, /4 días de fin de semana, 18-09-2026 Fiestas Patrias/);
  });

  it("una guía sin entrega dice que no registra entrega", () => {
    const texto = html(
      <DetalleGuia
        envio={guia({ entregada: false, fecha_entrega: null, resultado: "VENCIDA_SIN_ENTREGA" })}
      />,
    );
    assert.match(texto, /No registra entrega/);
  });
});

describe("criterios de la auditoría", () => {
  it("muestra fecha de corte, jornada, feriados y reglas", () => {
    const texto = html(
      <CriteriosAuditoria
        fechaCorte="2026-11-15T19:00:00"
        criterios={{
          jornada: "09:00 a 18:00, de lunes a viernes",
          calendario: "Feriados legales de Chile",
          despacho_desde: "2026-09-08T10:00:00",
          despacho_hasta: "2026-09-20T16:45:00",
          feriados: [{ fecha: "2026-09-18", nombre: "Fiestas Patrias" }],
          reglas: ["Regla de ejemplo"],
        }}
      />,
    );
    assert.match(texto, /Criterios de la auditoría/);
    assert.match(texto, /15 nov 2026/);
    assert.match(texto, /09:00 a 18:00, de lunes a viernes/);
    assert.match(texto, /18-09-2026 Fiestas Patrias/);
    assert.match(texto, /<li>Regla de ejemplo<\/li>/);
  });
});

describe("gráficos por transportista", () => {
  it("ordena la multa de mayor a menor y calcula el atraso promedio", () => {
    const texto = html(
      <GraficosTransportistas
        filas={[fila("Correos de Chile", 2, 10000, 20000), fila("Starken", 5, 12000, 60000)]}
        envios={[
          guia({ transportista: "Starken", horas_atraso: 10 }),
          guia({ transportista: "Starken", horas_atraso: 20 }),
          guia({ transportista: "Correos de Chile", horas_atraso: 30 }),
          guia({ transportista: "Correos de Chile", resultado: "CUMPLIDO", horas_atraso: 0 }),
        ]}
      />,
    );
    // Starken ($60.000) aparece antes que Correos ($20.000) en el gráfico de multas
    assert.ok(texto.indexOf("Starken: $60.000") < texto.indexOf("Correos de Chile: $20.000"));
    assert.match(texto, /5 guías fuera de plazo × \$12\.000/);
    // Atraso promedio: Starken (10 + 20) / 2 = 15 h; Correos solo cuenta la guía fuera de plazo
    assert.match(texto, /Starken: 15 h/);
    assert.match(texto, /Correos de Chile: 30 h/);
  });

  it("no se muestran si ningún transportista tiene multa", () => {
    assert.equal(
      html(<GraficosTransportistas filas={[fila("Starken", 0, 12000, 0)]} envios={[]} />),
      "",
    );
  });
});

describe("origen del texto de la IA", () => {
  it("indica qué IA redactó y, si fue la de respaldo, por qué", () => {
    const texto = html(
      <OrigenIA
        etiqueta="Redactada con IA"
        proveedor="Claude"
        modelo="claude-haiku-5-5"
        avisoRespaldo="Se alcanzó el límite gratuito de Gemini."
        detalle="Cifras calculadas por LogiSLA."
      />,
    );
    assert.match(texto, /Redactada con IA · Claude/);
    assert.match(texto, /Modelo claude-haiku-5-5/);
    assert.match(
      texto,
      /Redactó Claude, la IA de respaldo\. Se alcanzó el límite gratuito de Gemini\./,
    );
  });
});

describe("clases", () => {
  it("une las clases y descarta las condiciones falsas", () => {
    assert.equal(clases("a", false, null, undefined, "b"), "a b");
  });
});
