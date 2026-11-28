"""
Prueba rápida de la IA: revisa qué claves hay en backend/.env y hace UNA
llamada real a cada proveedor configurado (Gemini y Claude), en el orden en
que los usa LogiSLA (el principal primero).

Gasta muy poco: 1 de las solicitudes gratuitas del día en Gemini y, si Claude
tiene clave, una respuesta de una palabra (una fracción de centavo de dólar).

Uso (desde la carpeta backend, con el entorno .venv):
    .venv\\Scripts\\python.exe scripts\\probar_ia.py

Nunca imprime una clave completa, solo sus últimos 4 caracteres.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para poder importar app/

from app import ia_proveedores  # noqa: E402

PRUEBA = "Responde únicamente con la palabra: FUNCIONA"


def probar(proveedor: ia_proveedores.ConfiguracionProveedor, papel: str) -> bool:
    """Hace una llamada real a un proveedor e informa el resultado. True si respondió."""
    print(f"\n{proveedor.nombre} ({papel})")
    if not proveedor.configurada:
        print("  Sin clave: se omite.")
        return False
    print(f"  Clave encontrada (termina en ...{proveedor.api_key[-4:]}), modelo {proveedor.modelo}")
    try:
        respuesta = ia_proveedores.LLAMADAS[proveedor.nombre](PRUEBA, proveedor)
    except ia_proveedores.ErrorIA as exc:
        print(f"  [ERROR] {exc}")
        return False
    print(f"  Respuesta: {respuesta}")
    print("  [OK] Responde.")
    return True


if __name__ == "__main__":
    print(f"Archivo de configuración: {ia_proveedores.RUTA_ENV}")
    print(f"  ¿Existe?: {'sí' if ia_proveedores.RUTA_ENV.exists() else 'NO'}")
    config = ia_proveedores.obtener_configuracion()
    principal, respaldo = config.en_orden
    resultados = [probar(principal, "principal"), probar(respaldo, "respaldo")]
    print()
    if all(resultados):
        print(
            f"[OK] Las dos IA están listas: {principal.nombre} redacta y "
            f"{respaldo.nombre} queda de respaldo."
        )
    elif any(resultados):
        print("[OK] Hay una IA lista. La carta y el resumen se redactarán con ella.")
    else:
        print("[AVISO] Ninguna IA respondió: se usará la plantilla de respaldo.")
        sys.exit(1)
