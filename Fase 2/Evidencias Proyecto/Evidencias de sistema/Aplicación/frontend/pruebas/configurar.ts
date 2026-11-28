/**
 * Configuración común de las pruebas unitarias del frontend (HU-27).
 * Se carga antes que cualquier prueba (ver el script "test" de package.json).
 *
 * Las fechas se muestran en la hora local del navegador; para que las
 * pruebas den lo mismo en cualquier computador (y en GitHub Actions, que
 * usa UTC), se fija la zona horaria de Chile.
 */
process.env.TZ = "America/Santiago";
