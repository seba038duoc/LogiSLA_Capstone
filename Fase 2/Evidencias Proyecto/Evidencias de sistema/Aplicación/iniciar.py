"""
Arranque de LogiSLA en un solo paso y en una sola ventana.

Lo ejecuta iniciar.bat (doble clic). Hace, en orden:
  1. Revisa Node.js y npm.
  2. Backend: crea el entorno .venv si no existe e instala dependencias
     SOLO si requirements.txt cambió desde la última vez.
  3. Carga la empresa y las reglas SLA de prueba (no duplica nada).
  4. Frontend: instala dependencias SOLO si package.json cambió.
  5. Elige puertos libres (8000 y 3000 si se puede; si Windows los
     bloquea, como pasa en algunos PCs de Duoc, usa otros).
  5b. Base de datos: PostgreSQL 16 integrado. iniciar.py crea su propio
     PostgreSQL (en C:\\LogiSLA), lo enciende, aplica las migraciones de
     Alembic y lo apaga al terminar. No requiere instalar nada ni permisos
     de administrador: basta el zip oficial de binarios de PostgreSQL
     descomprimido en C:\\LogiSLA\\pgsql (o un PostgreSQL ya instalado).
  6. Levanta backend y frontend en esta misma ventana, espera a que ambos
     respondan de verdad y abre el navegador.
  7. Al cerrar la ventana o presionar Ctrl+C se detiene todo.

Los mensajes técnicos de cada servidor quedan en backend/servidor.log y
frontend/servidor.log, para que esta ventana muestre solo el estado.

Solo usa la biblioteca estándar de Python (corre antes de crear el .venv).
Opciones:
  --reinstalar   fuerza a reinstalar las dependencias de backend y frontend
  --sin-navegador  no abre el navegador al terminar
  --sqlite       usa SQLite en vez de PostgreSQL (solo para emergencias)
"""

import hashlib
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BACKEND = RAIZ / "backend"
FRONTEND = RAIZ / "frontend"
ES_WINDOWS = os.name == "nt"

PUERTO_BACKEND_PREFERIDO = 8000
PUERTO_FRONTEND_PREFERIDO = 3000
ESPERA_BACKEND_S = 90
ESPERA_FRONTEND_S = 240  # la primera compilación de Next.js puede tardar


class ErrorArranque(Exception):
    """Problema que impide arrancar; el mensaje explica qué hacer."""


# ------------------------------------------------------------------ utilidades


def paso(texto: str) -> None:
    """Imprime el título de un paso del arranque."""
    print(f"\n> {texto}", flush=True)


def info(texto: str) -> None:
    """Imprime una línea de detalle bajo el paso actual."""
    print(f"  {texto}", flush=True)


def huella(*archivos: Path) -> str:
    """Hash del contenido de los archivos: si cambia, hay que reinstalar."""
    h = hashlib.sha256()
    for archivo in archivos:
        if archivo.exists():
            h.update(archivo.name.encode())
            h.update(archivo.read_bytes())
    return h.hexdigest()


def ruta_legible(archivo: Path) -> str:
    """Ruta relativa a la carpeta del proyecto (más corta para mostrar en pantalla)."""
    try:
        return str(archivo.relative_to(RAIZ))
    except ValueError:
        return str(archivo)


def ultimas_lineas(archivo: Path, n: int = 25) -> str:
    """Últimas líneas de un archivo de registro, para mostrar la causa de un error."""
    try:
        lineas = archivo.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(no hay registro)"
    return "\n".join("    " + linea for linea in lineas[-n:])


def puerto_libre(preferido: int) -> int:
    """Devuelve `preferido` si se puede usar; si no, uno libre que asigne el sistema."""
    for candidato in (preferido, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if not ES_WINDOWS:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", candidato))
            except OSError:
                continue  # ocupado o bloqueado por Windows (WinError 10013)
            puerto = s.getsockname()[1]
        if candidato == 0 or _nadie_escucha(puerto):
            return puerto
    raise ErrorArranque("No se encontró ningún puerto libre en este equipo.")


def _nadie_escucha(puerto: int) -> bool:
    """En Windows otro programa puede escuchar en el puerto aunque bind() funcione."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", puerto)) != 0


def responde(url: str) -> bool:
    """True si la URL contesta sin error del servidor (sirve para saber si ya arrancó)."""
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except (urllib.error.URLError, OSError):
        return False


def ejecutar(comando: list[str], cwd: Path, registro: Path, env: dict | None = None) -> None:
    """Corre un comando hasta que termine, con su salida en un archivo de registro."""
    with open(registro, "w", encoding="utf-8", errors="replace") as salida:
        resultado = subprocess.run(
            comando, cwd=cwd, env=env, stdout=salida, stderr=subprocess.STDOUT
        )
    if resultado.returncode != 0:
        raise ErrorArranque(
            f"Falló: {' '.join(comando[:3])}...\n"
            f"  Detalle (final de {ruta_legible(registro)}):\n{ultimas_lineas(registro)}"
        )


# --------------------------------------------------------------------- pasos


def revisar_carpeta() -> None:
    """Evita ejecutar el arranque fuera del proyecto (por ejemplo, dentro del zip descomprimido)."""
    necesarios = [
        BACKEND / "requirements.txt",
        BACKEND / "app" / "main.py",
        FRONTEND / "package.json",
    ]
    if not all(archivo.exists() for archivo in necesarios):
        raise ErrorArranque(
            f"Esta carpeta no es el proyecto LogiSLA completo:\n    {RAIZ}\n"
            "  iniciar.bat debe estar dentro de la carpeta Aplicación del proyecto, junto a las\n"
            "  carpetas backend y frontend completas. Si descomprimiste un zip de actualización,\n"
            "  copia su contenido dentro de Aplicación y ejecuta el iniciar.bat que queda ahí."
        )


def revisar_node() -> str:
    """Verifica que Node.js y npm estén instalados y devuelve la ruta de npm."""
    npm = shutil.which("npm")
    node = shutil.which("node")
    if not node or not npm:
        raise ErrorArranque(
            "No se encontró Node.js o npm. Instala la versión LTS desde https://nodejs.org/ "
            "y vuelve a ejecutar iniciar.bat."
        )
    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
    try:
        mayor, menor = (int(x) for x in version.lstrip("v").split(".")[:2])
    except ValueError:
        mayor, menor = 0, 0
    if (mayor, menor) < (20, 9):
        raise ErrorArranque(
            f"El frontend necesita Node.js 20.9 o superior y este equipo tiene {version}."
        )
    info(f"Node.js {version}")
    return npm


def python_del_venv() -> Path:
    """Ruta del Python del entorno virtual del backend (backend/.venv)."""
    carpeta = "Scripts" if ES_WINDOWS else "bin"
    nombre = "python.exe" if ES_WINDOWS else "python"
    return BACKEND / ".venv" / carpeta / nombre


def preparar_backend(reinstalar: bool) -> Path:
    """Crea el entorno virtual e instala requirements.txt si falta o si cambió."""
    py = python_del_venv()
    if py.exists():
        valido = (
            subprocess.run(
                [
                    str(py),
                    "-c",
                    (
                        "import sys; v=sys.version_info; "
                        "sys.exit(0 if v.releaselevel=='final' and (3,10)<=v[:2]<=(3,14) else 1)"
                    ),
                ],
            ).returncode
            == 0
        )
        if not valido:
            info("El entorno .venv usa una versión de Python no soportada: se vuelve a crear.")
            shutil.rmtree(BACKEND / ".venv")
    if not py.exists():
        info("Creando el entorno de Python (.venv)...")
        ejecutar([sys.executable, "-m", "venv", ".venv"], BACKEND, BACKEND / "install.log")

    marca = BACKEND / ".venv" / ".logisla_requirements"
    actual = huella(BACKEND / "requirements.txt")
    if reinstalar or not marca.exists() or marca.read_text() != actual:
        info("Instalando dependencias del backend (la primera vez tarda un par de minutos)...")
        ejecutar(
            [str(py), "-m", "pip", "install", "-r", "requirements.txt"],
            BACKEND,
            BACKEND / "install.log",
        )
        marca.write_text(actual)
        info("Dependencias del backend instaladas.")
    else:
        info("Dependencias del backend al día.")
    return py


SQLITE = "sqlite:///./logisla.db"
CARPETA_POSTGRES = Path(
    os.environ.get("LOGISLA_PG_DIR")
    or (r"C:\LogiSLA" if ES_WINDOWS else str(Path.home() / ".logisla"))
)
PUERTO_POSTGRES_PREFERIDO = 5433  # no choca con un PostgreSQL instalado (5432)
DRIVER_POSTGRES = os.environ.get("LOGISLA_PG_DRIVER", "psycopg2")
URL_DESCARGA_POSTGRES = "https://www.enterprisedb.com/download-postgresql-binaries"


def url_configurada() -> str | None:
    """
    Una base externa indicada a mano: variable LOGISLA_DATABASE_URL o línea
    DATABASE_URL en backend/.env (por ejemplo, el PostgreSQL de docker compose).
    """
    if os.environ.get("LOGISLA_DATABASE_URL"):
        return os.environ["LOGISLA_DATABASE_URL"]
    archivo = BACKEND / ".env"
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            linea = linea.strip()
            if linea.startswith("DATABASE_URL=") and linea.split("=", 1)[1].strip():
                return linea.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _numero_version(carpeta: Path) -> float:
    """Número de versión de una carpeta de PostgreSQL (para elegir la más nueva)."""
    try:
        return float(carpeta.parent.name)
    except ValueError:
        return 0.0


def buscar_postgres() -> Path | None:
    """Carpeta bin de PostgreSQL: la portable de C:\\LogiSLA, una instalada o la del PATH."""
    exe = ".exe" if ES_WINDOWS else ""
    # "Extraer todo" de Windows suele crear una carpeta extra con el nombre del zip
    candidatos = [CARPETA_POSTGRES / "pgsql" / "bin", *sorted(CARPETA_POSTGRES.glob("*/pgsql/bin"))]
    if ES_WINDOWS:
        programas = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "PostgreSQL"
        candidatos += sorted(programas.glob("*/bin"), key=_numero_version, reverse=True)
    else:
        candidatos += sorted(
            Path("/usr/lib/postgresql").glob("*/bin"), key=_numero_version, reverse=True
        )
    en_path = shutil.which("pg_ctl")
    if en_path:
        candidatos.append(Path(en_path).parent)
    for carpeta in candidatos:
        if (carpeta / f"pg_ctl{exe}").exists() and (carpeta / f"initdb{exe}").exists():
            return carpeta
    return None


class PostgresIntegrado:
    """
    PostgreSQL propio de LogiSLA: los datos quedan en C:\\LogiSLA\\datos, escucha
    solo en 127.0.0.1 (no lo ve la red ni pide permiso al firewall) y no usa
    contraseña porque solo acepta conexiones de este mismo equipo.
    """

    def __init__(self, binarios: Path) -> None:
        """Prepara las rutas; el servidor se enciende en preparar()."""
        self.binarios = binarios
        self.datos = CARPETA_POSTGRES / "datos"
        self.puerto: int | None = None
        self.lo_encendi = False

    def _exe(self, nombre: str) -> str:
        """Ruta de un ejecutable de PostgreSQL (agrega .exe en Windows)."""
        return str(self.binarios / (nombre + (".exe" if ES_WINDOWS else "")))

    def version(self) -> str:
        """'pg_ctl (PostgreSQL) 16.6' -> '16.6'."""
        salida = subprocess.run([self._exe("pg_ctl"), "--version"], capture_output=True, text=True)
        encontrada = re.search(r"\(PostgreSQL\)\s+(\d+(?:\.\d+)*)", salida.stdout)
        return encontrada.group(1) if encontrada else "?"

    def descripcion(self) -> str:
        """Texto para el resumen final: versión, carpeta de datos y puerto."""
        return (
            f"PostgreSQL {self.version()} integrado (datos en {self.datos}, puerto {self.puerto})"
        )

    def preparar(self) -> str:
        """Crea el clúster la primera vez, lo enciende en un puerto libre y crea la base logisla."""
        try:
            CARPETA_POSTGRES.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ErrorArranque(
                f"No se pudo crear la carpeta {CARPETA_POSTGRES} ({exc}).\n"
                "  Usa iniciar.bat --sqlite en este equipo."
            ) from None

        if not (self.datos / "PG_VERSION").exists():
            info("Creando la base de datos PostgreSQL (solo la primera vez)...")
            ejecutar(
                [
                    self._exe("initdb"),
                    "-D",
                    str(self.datos),
                    "-U",
                    "postgres",
                    "-A",
                    "trust",
                    "-E",
                    "UTF8",
                    "--no-locale",
                ],
                CARPETA_POSTGRES,
                CARPETA_POSTGRES / "initdb.log",
            )

        encendido = (
            subprocess.run(
                [self._exe("pg_ctl"), "status", "-D", str(self.datos)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        if encendido:
            self.puerto = int((self.datos / "postmaster.pid").read_text().splitlines()[3])
            info(f"PostgreSQL ya estaba encendido (puerto {self.puerto}).")
        else:
            self.puerto = puerto_libre(PUERTO_POSTGRES_PREFERIDO)
            opciones = f"-p {self.puerto} -c listen_addresses=127.0.0.1"
            if not ES_WINDOWS:
                opciones += f" -k '{self.datos}'"
            info("Encendiendo PostgreSQL...")
            ejecutar(
                [
                    self._exe("pg_ctl"),
                    "start",
                    "-D",
                    str(self.datos),
                    "-l",
                    str(CARPETA_POSTGRES / "postgres.log"),
                    "-w",
                    "-t",
                    "60",
                    "-o",
                    opciones,
                ],
                CARPETA_POSTGRES,
                CARPETA_POSTGRES / "pg_ctl.log",
            )
            self.lo_encendi = True

        self._crear_base_logisla()
        return f"postgresql+{DRIVER_POSTGRES}://postgres@127.0.0.1:{self.puerto}/logisla"

    def _crear_base_logisla(self) -> None:
        """Crea la base de datos logisla si todavía no existe."""
        conexion = ["-h", "127.0.0.1", "-p", str(self.puerto), "-U", "postgres"]
        consulta = subprocess.run(
            [
                self._exe("psql"),
                *conexion,
                "-d",
                "postgres",
                "-tAc",
                "SELECT 1 FROM pg_database WHERE datname = 'logisla'",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if consulta.returncode != 0:
            raise ErrorArranque(
                "PostgreSQL se encendió, pero no respondió a la consulta inicial:\n    "
                + (consulta.stderr.strip() or consulta.stdout.strip())
            )
        if consulta.stdout.strip() != "1":
            ejecutar(
                [self._exe("createdb"), *conexion, "logisla"],
                CARPETA_POSTGRES,
                CARPETA_POSTGRES / "createdb.log",
            )

    def detener(self) -> None:
        """Apaga PostgreSQL solo si lo encendió este arranque."""
        if not self.lo_encendi:
            return
        try:
            subprocess.run(
                [self._exe("pg_ctl"), "stop", "-D", str(self.datos), "-m", "fast", "-w"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
            )
        except Exception:
            pass


def elegir_base(sqlite_forzado: bool) -> tuple[str, str, "PostgresIntegrado | None"]:
    """Devuelve (url, descripción, PostgreSQL integrado o None)."""
    if sqlite_forzado:
        return SQLITE, "SQLite (modo de emergencia, --sqlite)", None
    externa = url_configurada()
    if externa:
        return externa, describir_base(externa), None
    binarios = buscar_postgres()
    if binarios is None:
        raise ErrorArranque(
            "No se encontró PostgreSQL en este equipo. LogiSLA usa PostgreSQL 16.\n  Para dejarlo"
            " listo (sin instalar nada ni permisos de administrador):\n    1. Descarga el zip de"
            f" PostgreSQL 16 para Windows x86-64 en\n       {URL_DESCARGA_POSTGRES}\n    2."
            f" Descomprímelo para que quede {CARPETA_POSTGRES / 'pgsql' / 'bin' / 'pg_ctl.exe'}\n  "
            "  3. Vuelve a ejecutar iniciar.bat.\n  También sirve un PostgreSQL instalado con el"
            " instalador oficial.\n  Solo para una emergencia sin PostgreSQL: iniciar.bat --sqlite"
        )
    pg = PostgresIntegrado(binarios)
    url = pg.preparar()
    return url, pg.descripcion(), pg


def describir_base(url: str) -> str:
    """Nombre legible de la base, sin mostrar la contraseña."""
    if url.startswith("sqlite"):
        return "SQLite (archivo backend/logisla.db)"
    servidor = url.split("@", 1)[-1]
    return f"PostgreSQL ({servidor})"


def migrar_base(py: Path, env: dict) -> None:
    """Aplica las migraciones de Alembic; si fallan, detiene el arranque con el registro."""
    registro = BACKEND / "migracion.log"
    with open(registro, "w", encoding="utf-8", errors="replace") as salida:
        resultado = subprocess.run(
            [str(py), "scripts/migrar.py"],
            cwd=BACKEND,
            env=env,
            stdout=salida,
            stderr=subprocess.STDOUT,
        )
    if resultado.returncode != 0:
        detalle = ultimas_lineas(registro, 12)
        consejo = ""
        if not env["DATABASE_URL"].startswith("sqlite"):
            consejo = (
                "\n  Revisa que PostgreSQL esté encendido y que los datos de DATABASE_URL en"
                "\n  backend/.env sean correctos. Para volver a SQLite, borra esa línea."
            )
        raise ErrorArranque(
            f"No se pudo preparar la base de datos.{consejo}\n"
            f"  Detalle (final de backend/migracion.log):\n{detalle}"
        )
    info(ultimas_lineas(registro, 1).strip())


def entorno_backend(origenes: list[str], url_base: str) -> dict:
    """Variables de entorno con que se inicia el backend (base, orígenes permitidos, UTF-8)."""
    env = dict(os.environ)
    env["DATABASE_URL"] = url_base
    env["PYTHONPATH"] = str(BACKEND)
    env["ALLOWED_ORIGINS"] = ",".join(origenes)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def cargar_datos_prueba(py: Path, env: dict) -> None:
    """Carga transportistas, reglas SLA y la empresa piloto (no duplica si ya existen)."""
    salida = BACKEND / "company_id.txt"
    with (
        open(salida, "w", encoding="utf-8") as f,
        open(BACKEND / "seed_empresa.log", "w", encoding="utf-8") as err,
    ):
        r = subprocess.run(
            [str(py), "scripts/seed_pilot_company.py", "Retail Piloto SpA", "76.987.654-3"],
            cwd=BACKEND,
            env=env,
            stdout=f,
            stderr=err,
        )
    if r.returncode != 0:
        info(
            "[ATENCIÓN] No se pudo crear la empresa de prueba (detalle en"
            " backend/seed_empresa.log)."
        )
    try:
        ejecutar(
            [str(py), "scripts/seed_carriers_and_rules.py"],
            BACKEND,
            BACKEND / "seed_reglas.log",
            env,
        )
    except ErrorArranque:
        info(
            "[ATENCIÓN] No se pudieron cargar las reglas SLA (detalle en backend/seed_reglas.log)."
        )
    else:
        info("Empresa y reglas SLA de prueba listas.")


def preparar_frontend(npm: str, reinstalar: bool) -> None:
    """Instala las dependencias de npm si falta node_modules o si cambió package.json."""
    marca = FRONTEND / "node_modules" / ".logisla_paquetes"
    actual = huella(FRONTEND / "package.json", FRONTEND / "package-lock.json")
    if reinstalar or not marca.exists() or marca.read_text() != actual:
        info("Instalando dependencias del frontend (la primera vez tarda unos minutos)...")
        ejecutar(
            [
                npm,
                "install",
                "--no-audit",
                "--no-fund",
                "--fetch-retries=5",
                "--fetch-timeout=120000",
            ],
            FRONTEND,
            FRONTEND / "install.log",
        )
        marca.write_text(actual)
        info("Dependencias del frontend instaladas.")
    else:
        info("Dependencias del frontend al día.")


def escribir_env_local(url_api: str) -> None:
    """Deja NEXT_PUBLIC_API_URL apuntando al backend, sin borrar otras variables."""
    archivo = FRONTEND / ".env.local"
    lineas = []
    if archivo.exists():
        lineas = [
            l
            for l in archivo.read_text(encoding="utf-8-sig").splitlines()
            if not l.strip().startswith("NEXT_PUBLIC_API_URL=")
        ]
    lineas.append(f"NEXT_PUBLIC_API_URL={url_api}")
    archivo.write_text("\n".join(lineas) + "\n", encoding="utf-8")


# ---------------------------------------------------------- procesos en marcha


class Servidores:
    """Inicia, espera y detiene los procesos del backend y del frontend."""

    def __init__(self) -> None:
        """Lista vacía de procesos y archivos de registro abiertos."""
        self.procesos: list[tuple[str, subprocess.Popen, Path]] = []
        self._archivos = []

    def iniciar(
        self, nombre: str, comando: list[str], cwd: Path, registro: Path, env: dict | None = None
    ) -> None:
        """Inicia un proceso en segundo plano guardando su salida en un archivo de registro."""
        salida = open(registro, "w", encoding="utf-8", errors="replace")
        self._archivos.append(salida)
        extra = {} if ES_WINDOWS else {"start_new_session": True}
        proceso = subprocess.Popen(
            comando, cwd=cwd, env=env, stdout=salida, stderr=subprocess.STDOUT, **extra
        )
        self.procesos.append((nombre, proceso, registro))

    def caido(self):
        """Devuelve (nombre, registro) del primer servidor que se haya detenido solo, o None."""
        for nombre, proceso, registro in self.procesos:
            if proceso.poll() is not None:
                return nombre, registro
        return None

    def esperar(self, nombre: str, url: str, limite_s: int) -> None:
        """Espera a que un servidor responda; si se cae o se pasa el tiempo, muestra su registro."""
        inicio = time.monotonic()
        while time.monotonic() - inicio < limite_s:
            if responde(url):
                return
            caido = self.caido()
            if caido:
                raise ErrorArranque(
                    f"El {caido[0]} se detuvo al arrancar. Final de {ruta_legible(caido[1])}:\n"
                    f"{ultimas_lineas(caido[1])}"
                )
            time.sleep(1)
        registro = next(r for n, _, r in self.procesos if n == nombre)
        raise ErrorArranque(
            f"El {nombre} no respondió en {limite_s} segundos ({url}). "
            f"Final de {ruta_legible(registro)}:\n{ultimas_lineas(registro)}"
        )

    def detener(self) -> None:
        """Cierra los servidores iniciados (en Windows, con sus procesos hijos)."""
        for _, proceso, _ in self.procesos:
            if proceso.poll() is not None:
                continue
            try:
                if ES_WINDOWS:
                    # /T cierra también los procesos hijos (npm -> node)
                    subprocess.run(
                        ["taskkill", "/T", "/F", "/PID", str(proceso.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    os.killpg(proceso.pid, signal.SIGTERM)
                proceso.wait(timeout=10)
            except Exception:
                proceso.kill()
        for archivo in self._archivos:
            archivo.close()


def estado_ia(url_api: str) -> str:
    """Pregunta al backend qué IA tienen clave (Claude y Gemini), para el resumen final."""
    try:
        import json

        with urllib.request.urlopen(f"{url_api}/api/v1/ia/estado", timeout=5) as r:
            datos = json.loads(r.read())
    except Exception:
        return "no se pudo consultar"
    if not datos.get("configurada"):
        return "sin claves: se usará la plantilla de respaldo (ver backend/.env)"
    partes = [
        f"{p['nombre']} ({p['papel']}) " + ("activa" if p["configurado"] else "sin clave")
        for p in datos.get("proveedores", [])
    ]
    return ", ".join(partes)


# ----------------------------------------------------------------------- main


def main() -> int:
    """Arranque completo: revisa, prepara, migra, levanta los servidores y abre el navegador."""
    reinstalar = "--reinstalar" in sys.argv
    abrir = "--sin-navegador" not in sys.argv
    sqlite_forzado = "--sqlite" in sys.argv
    servidores = Servidores()
    postgres = None
    try:
        print("=" * 60)
        print("  LogiSLA - Auditoría de SLA de transporte")
        print("=" * 60)

        paso("Revisando requisitos")
        revisar_carpeta()
        info(f"Python {sys.version.split()[0]}")
        npm = revisar_node()

        paso("Preparando el backend")
        py = preparar_backend(reinstalar)

        paso("Preparando el frontend")
        preparar_frontend(npm, reinstalar)

        paso("Eligiendo puertos")
        puerto_api = puerto_libre(PUERTO_BACKEND_PREFERIDO)
        puerto_web = puerto_libre(PUERTO_FRONTEND_PREFERIDO)
        if puerto_web == puerto_api:
            puerto_web = puerto_libre(0)
        url_api = f"http://127.0.0.1:{puerto_api}"
        url_web = f"http://localhost:{puerto_web}"
        info(f"Backend en el puerto {puerto_api}, frontend en el puerto {puerto_web}")
        origenes = [f"http://localhost:{puerto_web}", f"http://127.0.0.1:{puerto_web}"]

        paso("Preparando la base de datos")
        url_base, descripcion_base, postgres = elegir_base(sqlite_forzado)
        info(descripcion_base)
        env = entorno_backend(origenes, url_base)
        migrar_base(py, env)

        paso("Cargando datos de prueba")
        cargar_datos_prueba(py, env)

        paso("Levantando LogiSLA")
        escribir_env_local(url_api)
        servidores.iniciar(
            "backend",
            [
                str(py),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(puerto_api),
            ],
            BACKEND,
            BACKEND / "servidor.log",
            env,
        )
        servidores.iniciar(
            "frontend",
            [npm, "run", "dev", "--", "--port", str(puerto_web)],
            FRONTEND,
            FRONTEND / "servidor.log",
        )
        info("Esperando al backend...")
        servidores.esperar("backend", f"{url_api}/health", ESPERA_BACKEND_S)
        info("Esperando al frontend (la primera vez compila las páginas)...")
        servidores.esperar("frontend", url_web, ESPERA_FRONTEND_S)
        # Se precargan las otras pantallas para que no tarden la primera vez que se abren.
        for ruta in ("/cargar", "/lotes/precarga"):
            responde(url_web + ruta)

        print()
        print("=" * 60)
        print(f"  LogiSLA está funcionando en {url_web}")
        print(f"  Base de datos: {descripcion_base}")
        print(f"  IA (carta y resumen ejecutivo): {estado_ia(url_api)}")
        print()
        print("  NO cierres esta ventana mientras uses LogiSLA.")
        print("  Para detenerlo: cierra esta ventana o presiona Ctrl+C.")
        print("=" * 60, flush=True)
        if abrir:
            webbrowser.open(url_web)

        while True:
            caido = servidores.caido()
            if caido:
                raise ErrorArranque(
                    f"El {caido[0]} se detuvo. Final de {ruta_legible(caido[1])}:\n"
                    f"{ultimas_lineas(caido[1])}"
                )
            time.sleep(2)

    except KeyboardInterrupt:
        print("\nDeteniendo LogiSLA...", flush=True)
        return 0
    except ErrorArranque as exc:
        print(f"\n[ERROR] {exc}", flush=True)
        return 1
    finally:
        servidores.detener()
        if postgres is not None:
            postgres.detener()


if __name__ == "__main__":
    sys.exit(main())
