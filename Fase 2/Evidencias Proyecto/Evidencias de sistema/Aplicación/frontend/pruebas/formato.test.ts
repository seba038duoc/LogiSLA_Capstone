/**
 * Pruebas de lib/formato.ts: cómo se muestran montos, cantidades, horas,
 * porcentajes y fechas en toda la aplicación.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  entero,
  fechaHoraCorta,
  fechaSistema,
  guias,
  horas,
  pesos,
  porcentaje,
  porcentajeCumplimiento,
} from "@/lib/formato";
import type { Conteos } from "@/lib/api";

/** Normaliza los espacios especiales que usa Intl (no separables) para comparar. */
const limpio = (texto: string) => texto.replace(/[  ]/g, " ");

/** Conteos con todo en cero, para armar casos de prueba. */
function conteos(cambios: Partial<Conteos>): Conteos {
  return {
    total: 0,
    cumplidos: 0,
    incumplidos: 0,
    en_transito: 0,
    vencidas_sin_entrega: 0,
    sin_regla: 0,
    datos_invalidos: 0,
    pendientes: 0,
    monto_multa_total: 0,
    ...cambios,
  };
}

describe("montos y cantidades", () => {
  it("muestra pesos chilenos con punto de miles y sin decimales", () => {
    assert.equal(limpio(pesos(170000)), "$170.000");
    assert.equal(limpio(pesos(15000.4)), "$15.000");
    assert.equal(pesos(null), "");
  });

  it("muestra enteros con punto de miles", () => {
    assert.equal(entero(1500), "1.500");
    assert.equal(entero(60), "60");
  });

  it("usa singular y plural en las guías", () => {
    assert.equal(guias(1), "1 guía");
    assert.equal(guias(13), "13 guías");
    assert.equal(guias(1200), "1.200 guías");
  });

  it("muestra las horas con coma decimal", () => {
    assert.equal(horas(10.5), "10,5 h");
    assert.equal(horas(12), "12 h");
    assert.equal(horas(null), "");
  });
});

describe("porcentajes de cumplimiento", () => {
  it("calcula el cumplimiento solo sobre las guías auditadas", () => {
    // 36 en plazo y 13 fuera de plazo (las sin entrega no cuentan)
    const c = conteos({ cumplidos: 36, incumplidos: 13, vencidas_sin_entrega: 11 });
    assert.equal(Math.round(porcentajeCumplimiento(c)! * 10) / 10, 73.5);
  });

  it("no inventa un porcentaje si no hay guías auditadas", () => {
    assert.equal(porcentajeCumplimiento(conteos({ pendientes: 5 })), null);
  });

  it("no redondea a 100 % si hubo algún incumplimiento", () => {
    assert.equal(limpio(porcentaje(99.6)), "99,6 %");
    assert.equal(limpio(porcentaje(73.47)), "73 %");
    assert.equal(porcentaje(null), "");
  });
});

describe("fechas", () => {
  it("formato compacto de las tablas: dd-mm-aaaa hh:mm de 24 horas", () => {
    assert.equal(fechaHoraCorta("2026-09-18T16:30:00"), "18-09-2026 16:30");
    assert.equal(fechaHoraCorta(null), "");
  });

  it("las fechas del sistema llegan en UTC y se muestran en hora de Chile", () => {
    // 18:00 UTC = 15:00 en Chile (horario de verano, UTC-3)
    const texto = limpio(fechaSistema("2026-11-15T18:00:00"));
    assert.match(texto, /15 nov 2026/);
    assert.match(texto, /03:00 p\. ?m\.|15:00/);
  });
});
