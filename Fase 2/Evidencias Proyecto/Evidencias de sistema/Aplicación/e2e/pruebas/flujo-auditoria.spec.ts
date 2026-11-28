import path from "node:path";
import { expect, test } from "@playwright/test";

/**
 * Flujo principal de LogiSLA de punta a punta, con la planilla piloto
 * (60 guías). Las cifras esperadas son las que calcula el motor de
 * auditoría y que también verifican las pruebas del backend.
 */

const PLANILLA_PILOTO = path.resolve(__dirname, "../../backend/sample_data/envios_piloto.csv");

test("la portada muestra el carrusel y ofrece la planilla de ejemplo", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "Audita a tus transportistas en minutos" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Pausar" })).toBeVisible();

  const descarga = page.waitForEvent("download");
  await page.getByRole("link", { name: /Planilla de ejemplo/ }).click();
  expect((await descarga).suggestedFilename()).toBe("envios_piloto.csv");
});

test("cargar, auditar y reclamar: cifras, resumen ejecutivo y carta", async ({ page }) => {
  // 1. Cargar la planilla
  await page.goto("/cargar");
  await page.locator("#archivo-envios").setInputFiles(PLANILLA_PILOTO);
  await page.getByRole("button", { name: "Cargar envíos" }).click();
  await expect(
    page.getByRole("heading", { name: "60 guías cargadas, listas para auditar" }),
  ).toBeVisible();

  // 2. Auditar
  await page.getByRole("button", { name: "Auditar lote" }).click();
  await expect(page).toHaveURL(/\/lotes\/[0-9a-f-]{36}$/);
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "$170.000 por reclamar en 13 guías fuera de plazo",
    }),
  ).toBeVisible();

  // 3. Desglose por transportista
  const transportistas = page.getByRole("region", { name: "Por transportista", exact: true });
  for (const nombre of ["Starken", "Chilexpress", "Blue Express", "Correos de Chile"]) {
    await expect(transportistas).toContainText(nombre);
  }

  // 3b. Gráficos por transportista (HU-15)
  const graficos = page.getByRole("region", { name: "Gráficos por transportista" });
  await expect(graficos).toContainText("Multa por reclamar");
  await expect(graficos.getByRole("listitem", { name: /^Starken: \$60\.000/ })).toBeVisible();
  await expect(graficos).toContainText("Atraso promedio de las guías fuera de plazo");

  // 4. Resumen ejecutivo (con IA si hay clave; si no, con la plantilla de respaldo)
  await page.getByRole("button", { name: "Generar resumen con IA" }).click();
  const resumen = page.getByTestId("texto-resumen");
  await expect(resumen).toContainText("$170.000");
  await expect(
    page
      .getByText("Redactado con IA")
      .or(page.getByText("Resumen generado con la plantilla (sin IA)")),
  ).toBeVisible();

  // 5. Carta de reclamo para Starken: el anexo lo arma siempre el sistema
  // exact: true, porque el buscador de guías también menciona "transportista"
  await page.getByLabel("Transportista", { exact: true }).selectOption("Starken");
  await page.getByRole("button", { name: "Generar carta con IA" }).click();
  const carta = page.getByLabel("Texto de la carta");
  await expect(carta).toHaveValue(/Señores\nStarken/);
  await expect(carta).toHaveValue(/Total: 5 guías, \$60\.000/);
  await expect(page.getByRole("button", { name: "Descargar (.txt)" })).toBeVisible();
});

test("cada guía justifica su resultado: si llegó, fecha límite y vencidas sin entrega", async ({
  page,
}) => {
  await page.goto("/cargar");
  await page.locator("#archivo-envios").setInputFiles(PLANILLA_PILOTO);
  await page.getByRole("button", { name: "Cargar envíos" }).click();
  await page.getByRole("button", { name: "Auditar lote" }).click();
  await expect(page).toHaveURL(/\/lotes\/[0-9a-f-]{36}$/);

  // Las 11 guías sin entrega ya vencieron a la fecha de corte: alerta sin multa
  await expect(
    page.getByText("11 guías sin registro de entrega con el plazo vencido"),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "Criterios de la auditoría" })).toContainText(
    "18-09-2026 Fiestas Patrias",
  );

  // Cálculo de una guía fuera de plazo: fecha límite, horas usadas y multa
  const guias = page.getByRole("region", { name: "Guías" });
  await guias.getByRole("button", { name: "Ver cálculo de la guía LSA-202600011" }).click();
  await expect(guias).toContainText("después de la fecha límite (29-09-2026 15:00)");
  await expect(guias).toContainText("Usó 72 horas hábiles de 60 permitidas");

  // Filtro de vencidas sin entrega
  await guias.getByRole("button", { name: /Vencida sin entrega/ }).click();
  await guias.getByRole("button", { name: "Ver cálculo de la guía LSA-202600001" }).click();
  await expect(guias).toContainText("No se aplica multa porque no hay registro de entrega");

  // Informe de auditoría imprimible
  await page.getByRole("link", { name: "Informe de auditoría" }).click();
  await expect(page.getByText("Informe de auditoría de SLA")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /4\. Guías entregadas fuera de plazo \(13\)/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /5\. Guías sin registro de entrega.*\(11\)/ }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Imprimir o guardar como PDF" })).toBeVisible();
});

test("un archivo sin las columnas obligatorias se rechaza con un mensaje claro", async ({
  page,
}) => {
  await page.goto("/cargar");
  await page.locator("#archivo-envios").setInputFiles({
    name: "planilla_equivocada.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("producto,cantidad\nmesa,2\nsilla,4\n", "utf-8"),
  });
  await page.getByRole("button", { name: "Cargar envíos" }).click();

  await expect(page.getByText("No se pudo cargar el archivo")).toBeVisible();
  await expect(page.getByText(/columnas obligatorias/)).toBeVisible();
});

test("un archivo que no es planilla se rechaza antes de subirlo", async ({ page }) => {
  await page.goto("/cargar");
  await page.locator("#archivo-envios").setInputFiles({
    name: "notas.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("esto no es una planilla", "utf-8"),
  });

  await expect(
    page.getByText('"notas.txt" no es un archivo CSV ni Excel.', { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Cargar envíos" })).toBeDisabled();
});
