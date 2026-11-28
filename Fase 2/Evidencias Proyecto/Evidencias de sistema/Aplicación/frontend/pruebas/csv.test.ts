/**
 * Pruebas de los archivos CSV que se descargan (lib/csv.ts y
 * lib/detalleCsv.ts): que Excel en Chile los abra bien y que no se puedan
 * usar para inyectar fórmulas.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { armarCsv, escapar } from "@/lib/csv";
import { filasDetalleAuditoria } from "@/lib/detalleCsv";
import { guia } from "./datos";

describe("celdas del CSV", () => {
  it("usa coma decimal en los números", () => {
    assert.equal(escapar(10.5), "10,5");
    assert.equal(escapar(15000), "15000");
  });

  it("neutraliza textos que Excel interpretaría como fórmulas", () => {
    assert.equal(escapar('=HYPERLINK("x")'), '"\'=HYPERLINK(""x"")"');
    assert.equal(escapar("+56912345678"), "'+56912345678");
    assert.equal(escapar("-5"), "'-5");
    assert.equal(escapar("@SUMA"), "'@SUMA");
  });

  it("encierra entre comillas los textos con punto y coma o comillas", () => {
    assert.equal(escapar("Fletes; Don Tito"), '"Fletes; Don Tito"');
    assert.equal(escapar('Bodega "Norte"'), '"Bodega ""Norte"""');
    assert.equal(escapar("Temuco"), "Temuco");
  });
});

describe("archivo completo", () => {
  it("parte con BOM UTF-8 y separa con ; y saltos de línea de Windows", () => {
    const contenido = armarCsv([
      ["Guía", "Multa"],
      ["G-1", 15000],
    ]);
    assert.ok(contenido.startsWith("﻿"));
    assert.equal(contenido.slice(1), "Guía;Multa\r\nG-1;15000");
  });

  it("el detalle de auditoría trae una fila por guía con su justificación", () => {
    const filas = filasDetalleAuditoria([
      guia({ numero_guia: "LSA-1", resultado: "INCUMPLIDO", monto_multa: 12000 }),
      guia({ numero_guia: "LSA-2", resultado: "VENCIDA_SIN_ENTREGA", entregada: false }),
    ]);
    assert.equal(filas.length, 3); // encabezados + 2 guías
    assert.equal(filas[0][0], "N° guía");
    assert.equal(filas[0].at(-1), "Justificación");
    assert.deepEqual(
      [filas[1][0], filas[1][4], filas[1][10], filas[1][11]],
      ["LSA-1", "Sí", "Fuera de plazo", 12000],
    );
    assert.deepEqual([filas[2][4], filas[2][10]], ["No", "Vencida sin entrega"]);
  });
});
