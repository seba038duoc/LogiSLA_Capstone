import { defineConfig, devices } from "@playwright/test";

/**
 * Pruebas E2E de LogiSLA (HU-24): un navegador real recorre la aplicación
 * como lo haría un usuario.
 *
 * Requiere LogiSLA corriendo (backend y frontend). Por defecto apunta a
 * http://localhost:3000; si iniciar.bat eligió otro puerto, definir E2E_URL.
 *   Local:  iniciar.bat  ->  en esta carpeta: npm install, npx playwright install chromium, npm test
 *   CI:     .github/workflows/ci-cd.yml levanta todo y corre estas pruebas.
 */
export default defineConfig({
  testDir: "./pruebas",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: process.env.E2E_URL ?? "http://localhost:3000",
    locale: "es-CL",
    timezoneId: "America/Santiago",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
