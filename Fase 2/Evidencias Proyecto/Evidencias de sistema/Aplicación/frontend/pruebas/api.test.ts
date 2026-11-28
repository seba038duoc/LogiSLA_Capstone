/**
 * Pruebas del cliente de la API (lib/api.ts): direcciones que se llaman y
 * mensajes de error que ve el usuario. fetch se reemplaza por una
 * simulación, así que no hace falta el backend encendido.
 */
import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  auditarLote,
  ErrorApi,
  generarCartaReclamo,
  listarEmpresas,
  listarLotes,
  mensajeDeError,
} from "@/lib/api";

const fetchOriginal = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = fetchOriginal;
});

/** Reemplaza fetch: guarda cada llamada y responde con `respuesta`. */
function simular(respuesta: () => Response | Promise<Response>) {
  const llamadas: { url: string; opciones?: RequestInit }[] = [];
  globalThis.fetch = (async (url: string, opciones?: RequestInit) => {
    llamadas.push({ url: String(url), opciones });
    return respuesta();
  }) as typeof fetch;
  return llamadas;
}

/** Respuesta JSON con el código HTTP indicado. */
const json = (cuerpo: unknown, estado = 200) =>
  new Response(JSON.stringify(cuerpo), {
    status: estado,
    headers: { "Content-Type": "application/json" },
  });

describe("direcciones del backend", () => {
  it("lista las empresas y devuelve el JSON", async () => {
    const llamadas = simular(() => json([{ id: "e1", nombre: "Retail", rut: null }]));
    const empresas = await listarEmpresas();
    assert.equal(empresas[0].nombre, "Retail");
    assert.match(llamadas[0].url, /\/api\/v1\/empresas$/);
  });

  it("codifica los parámetros en la URL", async () => {
    const llamadas = simular(() => json([]));
    await listarLotes("empresa con espacios");
    await generarCartaReclamo("lote-1", "Fletes & Cía");
    assert.match(llamadas[0].url, /empresa_id=empresa%20con%20espacios$/);
    assert.match(
      llamadas[1].url,
      /\/lote-1\/carta\?transportista=Fletes(\+|%20)%26(\+|%20)C%C3%ADa/,
    );
    assert.equal(llamadas[1].opciones?.method, "POST");
  });

  it("auditar es un POST", async () => {
    const llamadas = simular(() => json({ lote_id: "l1" }));
    await auditarLote("l1");
    assert.match(llamadas[0].url, /\/lotes-auditoria\/l1\/auditar$/);
    assert.equal(llamadas[0].opciones?.method, "POST");
  });
});

describe("mensajes de error", () => {
  it("usa el detalle que envía FastAPI y conserva el código HTTP", async () => {
    simular(() => json({ detail: "Lote no encontrado" }, 404));
    await assert.rejects(listarEmpresas(), (error: unknown) => {
      assert.ok(error instanceof ErrorApi);
      assert.equal(error.estado, 404);
      assert.equal(error.message, "Lote no encontrado");
      return true;
    });
  });

  it("une los errores de validación (422) en una sola frase", async () => {
    simular(() => json({ detail: [{ msg: "Falta la empresa" }, { msg: "Archivo vacío" }] }, 422));
    await assert.rejects(listarEmpresas(), /Falta la empresa\. Archivo vacío/);
  });

  it("si la respuesta no es JSON, usa el texto de estado", async () => {
    simular(() => new Response("<html>", { status: 502, statusText: "Bad Gateway" }));
    await assert.rejects(listarEmpresas(), /Bad Gateway/);
  });

  it("sin conexión explica que el backend no responde", async () => {
    simular(() => {
      throw new TypeError("fetch failed");
    });
    await assert.rejects(listarEmpresas(), (error: unknown) => {
      assert.ok(error instanceof ErrorApi);
      assert.equal(error.estado, 0);
      assert.match(error.message, /No hay conexión con el servidor de LogiSLA/);
      return true;
    });
  });

  it("mensajeDeError convierte cualquier error en texto", () => {
    assert.equal(mensajeDeError(new ErrorApi(500, "falló")), "falló");
    assert.equal(mensajeDeError(new Error("otro")), "otro");
    assert.equal(mensajeDeError("texto"), "texto");
  });
});
