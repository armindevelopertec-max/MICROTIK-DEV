#!/usr/bin/env python3
"""
ticket_qr.py — Tickets QR para el hotspot MikroTik del laboratorio.

Crea usuarios hotspot vía RouterOS API y genera:

  * QR WiFi   -> WIFI:T:WPA;S:MIKROTIK-LAB;P:...
  * QR acceso -> http://<portal>/login?username=...&password=...
  * Tarjeta   -> PNG con los dos QR, usuario, clave y vigencia
  * Lote      -> CSV + HTML imprimible

El login por URL funciona porque el perfil del hotspot acepta ``http-pap``
(HTTP PAP). El QR de acceso debe escanearse **después** de estar conectado a
la WiFi del laboratorio.

Uso rápido:
  ./scripts/ticket_qr.py setup
  ./scripts/ticket_qr.py crear -n 10 -t 1h
  ./scripts/ticket_qr.py listar
  ./scripts/ticket_qr.py activos
  ./scripts/ticket_qr.py eliminar --lote 20261023-153000

Requisitos:
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
import csv
import getpass
import io
import os
import re
import secrets
import sys
import traceback
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

# ---------------------------------------------------------------------------
# Rutas y constantes
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
DIR_TICKETS = BASE_DIR / "tickets"

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin I, O, 0, 1
MARCA_COMENTARIO = "QR|"
PERFIL_POR_DEFECTO = "qr-ticket"
PREFIJO_POR_DEFECTO = "QR"

AZUL = "#102743"
AZUL_CLARO = "#eaf1f9"
GRIS = "#5c6b7f"
GRIS_CLARO = "#f4f6f9"
VERDE = "#1f7a4d"
ROJO = "#b3261e"

# ---------------------------------------------------------------------------
# Dependencias opcionales (mensaje claro si falta algo)
# ---------------------------------------------------------------------------

FALTAN: list[str] = []

try:
    import routeros_api  # type: ignore
except ImportError:  # pragma: no cover
    routeros_api = None  # type: ignore
    FALTAN.append("routeros-api")

try:
    import segno  # type: ignore
except ImportError:  # pragma: no cover
    segno = None  # type: ignore
    FALTAN.append("segno")

try:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore
except ImportError:  # pragma: no cover
    Image = ImageDraw = ImageFont = None  # type: ignore
    FALTAN.append("Pillow")


def requerir_dependencias() -> None:
    if not FALTAN:
        return
    print(
        "Faltan dependencias de Python: " + ", ".join(FALTAN) + "\n\n"
        "Instálalas con:\n"
        "  python3 -m venv .venv\n"
        "  .venv/bin/pip install -r requirements.txt\n"
        "  .venv/bin/python scripts/ticket_qr.py --help\n",
        file=sys.stderr,
    )
    raise SystemExit(2)


# ---------------------------------------------------------------------------
# Configuración (.env + variables de entorno + argumentos)
# ---------------------------------------------------------------------------


def cargar_env(ruta: Path = ENV_FILE) -> None:
    """Carga un .env sencillo sin dependencias externas."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip()
        valor = valor.strip().strip("'\"")
        if clave and clave not in os.environ:
            os.environ[clave] = valor


def env(nombre: str, defecto: str = "") -> str:
    return os.environ.get(nombre, defecto)


def normalizar_portal(portal: str) -> str:
    portal = (portal or "").strip()
    if not portal:
        return ""
    if not re.match(r"^https?://", portal, re.IGNORECASE):
        portal = "http://" + portal
    return portal.rstrip("/")


def sanitizar_nombre(texto: str, defecto: str = "lote") -> str:
    limpio = re.sub(r"[^A-Za-z0-9._-]+", "-", texto.strip())
    limpio = limpio.strip("-._")
    return limpio or defecto


@dataclass
class Config:
    host: str = "127.0.0.1"
    puerto: int = 8728
    usuario: str = "admin"
    password: str = ""
    ssid: str = "MIKROTIK-LAB"
    wifi_password: str = "mikrotik123"
    portal: str = ""
    perfil: str = PERFIL_POR_DEFECTO
    prefijo: str = PREFIJO_POR_DEFECTO
    rate_limit: str = ""
    dir_tickets: Path = DIR_TICKETS
    color: bool = True
    debug: bool = False

    @classmethod
    def desde_args(cls, args: argparse.Namespace) -> Config:
        color = not getattr(args, "sin_color", False) and sys.stdout.isatty()
        dir_tickets = Path(
            getattr(
                args,
                "dir_tickets",
                env("MIKROTIK_TICKETS_DIR", str(DIR_TICKETS)),
            )
        ).expanduser()
        if not dir_tickets.is_absolute():
            dir_tickets = BASE_DIR / dir_tickets
        return cls(
            host=getattr(args, "host", env("MIKROTIK_HOST", "127.0.0.1")),
            puerto=int(getattr(args, "puerto", env("MIKROTIK_PORT", "8728"))),
            usuario=getattr(args, "api_usuario", env("MIKROTIK_USER", "admin")),
            password=getattr(
                args, "api_password", env("MIKROTIK_PASSWORD", "Dahua2026")
            ),
            ssid=getattr(args, "ssid", env("MIKROTIK_SSID", "MIKROTIK-LAB")),
            wifi_password=getattr(
                args,
                "wifi_password",
                env("MIKROTIK_WIFI_PASSWORD", "mikrotik123"),
            ),
            portal=normalizar_portal(
                getattr(args, "portal", env("MIKROTIK_PORTAL", ""))
            ),
            perfil=getattr(
                args, "perfil", env("MIKROTIK_PROFILE", PERFIL_POR_DEFECTO)
            ),
            prefijo=getattr(
                args, "prefijo", env("MIKROTIK_PREFIX", PREFIJO_POR_DEFECTO)
            ),
            rate_limit=getattr(
                args, "rate_limit", env("MIKROTIK_RATE_LIMIT", "")
            ),
            dir_tickets=dir_tickets,
            color=color,
            debug=getattr(args, "debug", False),
        )


# ---------------------------------------------------------------------------
# Salida por consola
# ---------------------------------------------------------------------------


class Color:
    def __init__(self, activo: bool):
        self.activo = activo

    def _c(self, codigo: str, texto: str) -> str:
        return f"\033[{codigo}m{texto}\033[0m" if self.activo else texto

    def ok(self, t: str) -> str:
        return self._c("32", t)

    def error(self, t: str) -> str:
        return self._c("31", t)

    def aviso(self, t: str) -> str:
        return self._c("33", t)

    def info(self, t: str) -> str:
        return self._c("36", t)

    def negrita(self, t: str) -> str:
        return self._c("1", t)


def titulo(texto: str) -> None:
    print()
    print("=" * 74)
    print(texto)
    print("=" * 74)


def tabla(cabeceras: Sequence[str], filas: Iterable[Sequence[Any]]) -> None:
    filas_txt = [[str(c) if c is not None else "" for c in fila] for fila in filas]
    anchos = [len(h) for h in cabeceras]
    for fila in filas_txt:
        for i, valor in enumerate(fila):
            if i < len(anchos):
                anchos[i] = max(anchos[i], len(valor))

    print("  ".join(h.ljust(anchos[i]) for i, h in enumerate(cabeceras)))
    print("  ".join("-" * ancho for ancho in anchos))
    for fila in filas_txt:
        print("  ".join(fila[i].ljust(anchos[i]) for i in range(len(anchos))))


def formatear_bytes(valor: Any) -> str:
    try:
        n = float(str(valor).replace(",", ""))
    except (TypeError, ValueError):
        return "0 B"
    for unidad in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or unidad == "TiB":
            if unidad == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unidad}"
        n /= 1024
    return f"{n:.1f} TiB"


def duracion_a_segundos(texto: str) -> int:
    """Convierte '1h30m', '5m', '1d' o 'HH:MM:SS' a segundos."""
    if not texto or texto in ("none", "0s", "0"):
        return 0
    if ":" in texto:
        partes = [int(p) for p in texto.split(":") if p.isdigit()]
        while len(partes) < 3:
            partes.insert(0, 0)
        h, m, s = partes[-3:]
        return h * 3600 + m * 60 + s
    total = 0
    for numero, unidad in re.findall(r"(\d+)([smhdw])", texto):
        total += int(numero) * {
            "s": 1,
            "m": 60,
            "h": 3600,
            "d": 86400,
            "w": 604800,
        }[unidad]
    return total


def formatear_duracion(segundos: int) -> str:
    if segundos <= 0:
        return "—"
    dias, resto = divmod(segundos, 86400)
    horas, resto = divmod(resto, 3600)
    minutos, seg = divmod(resto, 60)
    partes = []
    if dias:
        partes.append(f"{dias}d")
    if horas:
        partes.append(f"{horas}h")
    if minutos and not dias:
        partes.append(f"{minutos}m")
    if seg and not dias and not horas:
        partes.append(f"{seg}s")
    return " ".join(partes) or "—"


def validar_duracion(texto: str) -> str:
    texto = (texto or "").strip().lower()
    if not texto:
        texto = "1h"
    if not re.fullmatch(r"(?:\d+[smhdw])+", texto):
        raise ErrorApp(
            f"Duración inválida: {texto!r}. Usa formatos como 30m, 1h, 1h30m o 1d."
        )
    if duracion_a_segundos(texto) <= 0:
        raise ErrorApp("La duración debe ser mayor que cero.")
    return texto


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------


class ErrorApp(Exception):
    pass


# ---------------------------------------------------------------------------
# Cliente RouterOS API
# ---------------------------------------------------------------------------


class MikroTik:
    def __init__(self, cfg: Config):
        if routeros_api is None:  # pragma: no cover
            raise ErrorApp("Falta la dependencia routeros-api.")
        self.cfg = cfg
        try:
            pool = routeros_api.RouterOsApiPool(
                cfg.host,
                username=cfg.usuario,
                password=cfg.password,
                port=cfg.puerto,
                plaintext_login=True,
            )
            pool.socket_timeout = 8.0
            self.pool = pool
            self.api = pool.get_api()
        except Exception as exc:
            raise ErrorApp(self.mensaje_conexion(exc)) from exc

    def mensaje_conexion(self, exc: Exception) -> str:
        return (
            f"No se pudo conectar a la API de MikroTik en "
            f"{self.cfg.host}:{self.cfg.puerto}.\n\n"
            "Comprueba:\n"
            "  1. Que el laboratorio esté arriba:  ./scripts/iniciar-lab.sh\n"
            "  2. Que el puerto 8728 esté reenviado:  ss -tlnp | grep 8728\n"
            "     (si el CHR llevaba arrancado desde antes, reinícialo para\n"
            "      aplicar el hostfwd que ahora incluye iniciar-lab.sh)\n"
            "  3. Usuario/clave de RouterOS en .env (MIKROTIK_USER/PASSWORD).\n\n"
            f"Detalle: {type(exc).__name__}: {exc}"
        )

    def _r(self, ruta: str):
        return self.api.get_resource(ruta)

    def cerrar(self) -> None:
        with suppress(Exception):
            self.pool.disconnect()

    # -- información -------------------------------------------------------
    def identidad(self) -> str:
        datos = self._r("/system/identity").get()
        return datos[0].get("name", "?") if datos else "?"

    def version(self) -> str:
        datos = self._r("/system/resource").get()
        return datos[0].get("version", "?") if datos else "?"

    # -- hotspot -----------------------------------------------------------
    def servidores_hotspot(self) -> list[dict[str, Any]]:
        return self._r("/ip/hotspot").get()

    def perfiles_hotspot(self) -> list[dict[str, Any]]:
        return self._r("/ip/hotspot/profile").get()

    def perfiles_usuario(self) -> list[dict[str, Any]]:
        return self._r("/ip/hotspot/user/profile").get()

    def usuarios(self) -> list[dict[str, Any]]:
        return self._r("/ip/hotspot/user").get()

    def activos(self) -> list[dict[str, Any]]:
        return self._r("/ip/hotspot/active").get()

    def cookies(self) -> list[dict[str, Any]]:
        return self._r("/ip/hotspot/cookie").get()

    def detectar_portal(self) -> str:
        perfiles = {p.get("name"): p for p in self.perfiles_hotspot()}
        for servidor in self.servidores_hotspot():
            perfil = perfiles.get(servidor.get("profile"), {})
            direccion = (perfil.get("hotspot-address") or "").strip()
            if direccion and direccion != "0.0.0.0":
                return normalizar_portal(direccion)
        return ""

    def perfiles_hotspot_usados(self) -> list[str]:
        usados = []
        for servidor in self.servidores_hotspot():
            nombre = servidor.get("profile")
            if nombre and nombre not in usados:
                usados.append(nombre)
        return usados

    def asegurar_http_pap(self) -> list[str]:
        """Añade http-pap a login-by en los perfiles de hotspot usados."""
        cambios: list[str] = []
        usados = set(self.perfiles_hotspot_usados())
        for perfil in self.perfiles_hotspot():
            if usados and perfil.get("name") not in usados:
                continue
            metodos = [
                m.strip()
                for m in (perfil.get("login-by") or "").split(",")
                if m.strip()
            ]
            if "http-pap" in metodos:
                continue
            metodos.append("http-pap")
            self._r("/ip/hotspot/profile").set(
                id=perfil["id"], **{"login-by": ",".join(metodos)}
            )
            cambios.append(perfil.get("name", "?"))
        return cambios

    def asegurar_perfil(
        self, cfg: Config, forzar: bool = False
    ) -> tuple[str, dict[str, Any]]:
        parametros: dict[str, Any] = {
            "shared-users": "1",
            "idle-timeout": "10m",
            "keepalive-timeout": "2m",
            "add-mac-cookie": "yes",
            "session-timeout": "0s",
        }
        if cfg.rate_limit:
            parametros["rate-limit"] = cfg.rate_limit

        existentes = {p.get("name"): p for p in self.perfiles_usuario()}
        actual = existentes.get(cfg.perfil)
        if actual is None:
            self._r("/ip/hotspot/user/profile").add(
                name=cfg.perfil, **parametros
            )
            return "creado", parametros
        if forzar:
            self._r("/ip/hotspot/user/profile").set(
                id=actual["id"], **parametros
            )
            return "actualizado", parametros
        return "existente", actual

    def crear_usuario(
        self,
        codigo: str,
        password: str,
        perfil: str,
        tiempo: str,
        comentario: str,
        limite_bytes: str = "",
    ) -> None:
        parametros: dict[str, Any] = {
            "name": codigo,
            "password": password,
            "profile": perfil,
            "limit-uptime": tiempo,
            "comment": comentario,
        }
        if limite_bytes:
            parametros["limit-bytes-total"] = limite_bytes
        self._r("/ip/hotspot/user").add(**parametros)

    def eliminar_usuario(self, ident: str) -> None:
        self._r("/ip/hotspot/user").remove(id=ident)

    def eliminar_activo(self, ident: str) -> None:
        self._r("/ip/hotspot/active").remove(id=ident)

    def eliminar_cookie(self, ident: str) -> None:
        self._r("/ip/hotspot/cookie").remove(id=ident)


@contextmanager
def conectar(cfg: Config) -> Iterator[MikroTik]:
    mt = MikroTik(cfg)
    try:
        yield mt
    finally:
        mt.cerrar()


# ---------------------------------------------------------------------------
# Tickets y QR
# ---------------------------------------------------------------------------


@dataclass
class Ticket:
    codigo: str
    password: str
    perfil: str
    limite_uptime: str
    lote: str
    creado: str
    login_url: str
    portal: str
    nota: str = ""

    def wifi_payload(self, cfg: Config) -> str:
        return wifi_qr_payload(cfg.ssid, cfg.wifi_password)


def escapar_wifi(texto: str) -> str:
    """Escapa caracteres especiales según el formato WIFI: de ZXing."""
    return re.sub(r"([\\;,\":])", r"\\\1", texto)


def wifi_qr_payload(ssid: str, password: str) -> str:
    return f"WIFI:T:WPA;S:{escapar_wifi(ssid)};P:{escapar_wifi(password)};;"


def generar_codigo(prefijo: str, existentes: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9]", "", prefijo or PREFIJO_POR_DEFECTO).upper()
    base = (base or PREFIJO_POR_DEFECTO)[:8]
    for _ in range(200):
        codigo = f"{base}-{''.join(secrets.choice(ALFABETO) for _ in range(6))}"
        if codigo not in existentes:
            return codigo
    raise ErrorApp("No se pudo generar un código único para el ticket.")


def generar_password(longitud: int = 8) -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(longitud))


def parsear_comentario(comentario: str) -> dict[str, str]:
    if not (comentario or "").startswith(MARCA_COMENTARIO):
        return {}
    partes = comentario.split("|", 4)
    claves = ["marca", "lote", "creado", "tiempo", "nota"]
    return {clave: partes[i] if i < len(partes) else "" for i, clave in enumerate(claves)}


def es_ticket(usuario: dict[str, Any], cfg: Config) -> bool:
    comentario = usuario.get("comment") or ""
    nombre = usuario.get("name") or ""
    return comentario.startswith(MARCA_COMENTARIO) or nombre.startswith(
        f"{cfg.prefijo.upper()}-"
    )


def nombre_archivo(codigo: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", codigo)


def _fuente(tamano: int, negrita: bool = False):
    if ImageFont is None:  # pragma: no cover
        return None
    variante = "Bold" if negrita else "Regular"
    candidatos = [
        f"/usr/share/fonts/liberation-sans-fonts/LiberationSans-{variante}.ttf",
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans-{variante}.ttf",
        f"/usr/share/fonts/dejavu/DejaVuSans-{variante}.ttf",
        f"/usr/share/fonts/google-noto/NotoSans-{variante}.ttf",
    ]
    for ruta in candidatos:
        if Path(ruta).exists():
            try:
                return ImageFont.truetype(ruta, tamano)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=tamano)  # Pillow >= 10
    except TypeError:  # pragma: no cover
        return ImageFont.load_default()


def qr_imagen(payload: str, lado: int = 300):
    """Devuelve un PIL.Image cuadrado con el QR y borde blanco."""
    if segno is None or Image is None:  # pragma: no cover
        raise ErrorApp("Faltan segno/Pillow para generar QR.")
    qr = segno.make(payload, error="m")
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=10, border=2, dark=AZUL, light="#ffffff")
    buffer.seek(0)
    imagen = Image.open(buffer).convert("RGB")
    # Reescalado entero para no emborronar los módulos.
    return imagen.resize((lado, lado), Image.Resampling.NEAREST)


def render_tarjeta(ticket: Ticket, cfg: Config):
    """Devuelve la tarjeta como imagen PIL (sin guardarla en disco)."""
    if Image is None or ImageDraw is None:  # pragma: no cover
        raise ErrorApp("Falta Pillow para generar la tarjeta.")

    ancho, alto = 1000, 650
    imagen = Image.new("RGB", (ancho, alto), "#ffffff")
    dibujo = ImageDraw.Draw(imagen)

    # Cabecera
    dibujo.rectangle([0, 0, ancho, 108], fill=AZUL)
    dibujo.text(
        (40, 20), "MIKROTIK-LAB", font=_fuente(34, True), fill="#ffffff"
    )
    dibujo.text(
        (40, 66),
        "Ticket de acceso WiFi + Internet",
        font=_fuente(18),
        fill="#c9dcf2",
    )
    dibujo.text(
        (ancho - 40, 28),
        "LOTE",
        font=_fuente(12, True),
        fill="#9db8d8",
        anchor="ra",
    )
    dibujo.text(
        (ancho - 40, 48),
        ticket.lote,
        font=_fuente(17, True),
        fill="#ffffff",
        anchor="ra",
    )

    # QR 1: WiFi
    qr_wifi = qr_imagen(ticket.wifi_payload(cfg), 300)
    x1, y1 = 55, 178
    dibujo.rounded_rectangle(
        [x1 - 12, y1 - 12, x1 + 312, y1 + 312],
        radius=16,
        outline="#d7dee8",
        width=2,
    )
    imagen.paste(qr_wifi, (x1, y1))
    dibujo.text(
        (x1, 126),
        "1. CONÉCTATE AL WIFI",
        font=_fuente(17, True),
        fill=AZUL,
    )
    dibujo.text(
        (x1, 500),
        cfg.ssid,
        font=_fuente(22, True),
        fill=AZUL,
    )
    dibujo.text(
        (x1, 530),
        "Escanea y acepta la red inalámbrica",
        font=_fuente(14),
        fill=GRIS,
    )

    # QR 2: login
    qr_login = qr_imagen(ticket.login_url, 300)
    x2, y2 = 555, 178
    dibujo.rounded_rectangle(
        [x2 - 12, y2 - 12, x2 + 312, y2 + 312],
        radius=16,
        outline="#d7dee8",
        width=2,
    )
    imagen.paste(qr_login, (x2, y2))
    dibujo.text(
        (x2, 126),
        "2. ACCEDE A INTERNET",
        font=_fuente(17, True),
        fill=AZUL,
    )
    dibujo.text(
        (x2, 500),
        "Escanea con la WiFi ya conectada",
        font=_fuente(14),
        fill=GRIS,
    )
    dibujo.text(
        (x2, 530),
        "El navegador abrirá el portal y entrará solo",
        font=_fuente(14),
        fill=GRIS,
    )

    # Credenciales
    dibujo.rounded_rectangle(
        [40, 552, ancho - 40, 620], radius=14, fill=GRIS_CLARO
    )
    dibujo.text((62, 562), "USUARIO", font=_fuente(11, True), fill=GRIS)
    dibujo.text(
        (62, 580), ticket.codigo, font=_fuente(24, True), fill=AZUL
    )
    dibujo.text((330, 562), "CLAVE", font=_fuente(11, True), fill=GRIS)
    dibujo.text(
        (330, 580), ticket.password, font=_fuente(24, True), fill=AZUL
    )
    dibujo.text((555, 562), "VÁLIDO", font=_fuente(11, True), fill=GRIS)
    dibujo.text(
        (555, 580),
        ticket.limite_uptime,
        font=_fuente(24, True),
        fill=AZUL,
    )
    dibujo.text(
        (760, 565),
        "1 dispositivo",
        font=_fuente(14, True),
        fill=GRIS,
    )
    dibujo.text(
        (760, 588),
        "tiempo de conexión",
        font=_fuente(12),
        fill=GRIS,
    )
    return imagen


def crear_tarjeta(ticket: Ticket, cfg: Config, destino: Path) -> Path:
    """Genera y guarda la tarjeta PNG con los dos QR y las credenciales."""
    imagen = render_tarjeta(ticket, cfg)
    salida = destino / f"{nombre_archivo(ticket.codigo)}_ticket.png"
    imagen.save(salida, "PNG", optimize=True)
    return salida


def guardar_ticket(ticket: Ticket, cfg: Config, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    base = nombre_archivo(ticket.codigo)

    # QR individuales
    qr_imagen(ticket.login_url, 420).save(destino / f"{base}_login.png")
    qr_imagen(ticket.wifi_payload(cfg), 420).save(destino / f"{base}_wifi.png")

    # Tarjeta combinada
    crear_tarjeta(ticket, cfg, destino)

    # Texto de ayuda
    texto = (
        f"MIKROTIK-LAB — Ticket de acceso\n"
        f"================================\n\n"
        f"Usuario : {ticket.codigo}\n"
        f"Clave   : {ticket.password}\n"
        f"Válido  : {ticket.limite_uptime} de conexión\n"
        f"Lote    : {ticket.lote}\n"
        f"Creado  : {ticket.creado}\n\n"
        f"Paso 1: conéctate a la WiFi '{cfg.ssid}'.\n"
        f"        Clave WiFi: {cfg.wifi_password}\n\n"
        f"Paso 2: escanea el QR de acceso o abre esta URL\n"
        f"        con el móvil ya conectado a la WiFi:\n\n"
        f"        {ticket.login_url}\n\n"
        f"Un dispositivo por ticket. El tiempo solo corre mientras\n"
        f"la sesión está conectada.\n"
    )
    (destino / f"{base}.txt").write_text(texto, encoding="utf-8")


def escribir_csv(destino: Path, tickets: Sequence[Ticket], cfg: Config) -> Path:
    ruta = destino / "tickets.csv"
    with ruta.open("w", newline="", encoding="utf-8-sig") as archivo:
        campos = [
            "codigo",
            "password",
            "perfil",
            "limite_uptime",
            "lote",
            "creado",
            "login_url",
            "wifi_qr",
            "ssid",
            "wifi_password",
        ]
        escritor = csv.DictWriter(archivo, fieldnames=campos)
        escritor.writeheader()
        for t in tickets:
            escritor.writerow(
                {
                    "codigo": t.codigo,
                    "password": t.password,
                    "perfil": t.perfil,
                    "limite_uptime": t.limite_uptime,
                    "lote": t.lote,
                    "creado": t.creado,
                    "login_url": t.login_url,
                    "wifi_qr": t.wifi_payload(cfg),
                    "ssid": cfg.ssid,
                    "wifi_password": cfg.wifi_password,
                }
            )
    return ruta


def escribir_html(destino: Path, tickets: Sequence[Ticket]) -> Path:
    ruta = destino / "tickets.html"
    tarjetas = "\n".join(
        f'      <section class="card">'
        f'<img src="{nombre_archivo(t.codigo)}_ticket.png" '
        f'alt="Ticket {t.codigo}"></section>'
        for t in tickets
    )
    html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tickets QR — {tickets[0].lote if tickets else ""}</title>
  <style>
    :root {{ color-scheme: light; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 24px;
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      background: #e9edf3; color: #102743;
    }}
    header {{ max-width: 1000px; margin: 0 auto 18px; }}
    h1 {{ margin: 0 0 6px; font-size: 22px; }}
    p {{ margin: 0; color: #5c6b7f; }}
    .card {{
      max-width: 1000px; margin: 0 auto 18px; background: white;
      border-radius: 12px; overflow: hidden;
      box-shadow: 0 6px 18px rgba(16, 39, 67, .12);
      page-break-inside: avoid;
    }}
    .card img {{ display: block; width: 100%; height: auto; }}
    @media print {{
      @page {{ size: A4 portrait; margin: 8mm; }}
      body {{ background: white; padding: 0; }}
      header {{ display: none; }}
      .card {{
        box-shadow: none; border-radius: 0; margin: 0;
        page-break-after: always;
      }}
      .card:last-of-type {{ page-break-after: auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Tickets QR — lote {tickets[0].lote if tickets else ""}</h1>
    <p>{len(tickets)} ticket(s). Imprime esta página o abre cada PNG.
       Escanea primero el QR del WiFi y después el de acceso.</p>
  </header>
{tarjetas}
</body>
</html>
"""
    ruta.write_text(html, encoding="utf-8")
    return ruta


def escribir_resumen(
    destino: Path,
    tickets: Sequence[Ticket],
    cfg: Config,
    portal: str,
) -> Path:
    ruta = destino / "resumen.txt"
    texto = (
        f"Lote        : {tickets[0].lote if tickets else '-'}\n"
        f"Creado      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Tickets     : {len(tickets)}\n"
        f"Perfil      : {cfg.perfil}\n"
        f"Portal      : {portal}\n"
        f"SSID        : {cfg.ssid}\n"
        f"Clave WiFi  : {cfg.wifi_password}\n"
        f"Carpeta     : {destino}\n\n"
        "Archivos por ticket:\n"
        "  <codigo>_ticket.png   tarjeta con los dos QR\n"
        "  <codigo>_wifi.png     QR para unirse a la WiFi\n"
        "  <codigo>_login.png    QR de acceso (HTTP-PAP)\n"
        "  <codigo>.txt          credenciales y URL\n\n"
        "tickets.csv  : datos del lote (UTF-8 con BOM, para hoja de cálculo)\n"
        "tickets.html : página imprimible con todas las tarjetas\n"
    )
    ruta.write_text(texto, encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def resolver_portal(mt: MikroTik, cfg: Config) -> str:
    portal = cfg.portal or mt.detectar_portal()
    if not portal:
        raise ErrorApp(
            "No pude detectar la dirección del portal del hotspot.\n"
            "Define MIKROTIK_PORTAL en .env o usa --portal http://192.168.77.254"
        )
    return portal


def comando_setup(args: argparse.Namespace, cfg: Config) -> int:
    with conectar(cfg) as mt:
        titulo("Preparando hotspot para tickets QR")
        print(f"RouterOS   : {mt.identidad()} ({mt.version()})")
        print(f"API        : {cfg.host}:{cfg.puerto}  OK")

        servidores = mt.servidores_hotspot()
        if not servidores:
            raise ErrorApp(
                "No hay ningún servidor hotspot configurado en el router."
            )
        for servidor in servidores:
            print(
                f"Hotspot    : {servidor.get('name')} "
                f"(interfaz {servidor.get('interface')}, "
                f"perfil {servidor.get('profile')})"
            )

        estado_perfil, parametros = mt.asegurar_perfil(
            cfg, forzar=bool(getattr(args, "forzar", False))
        )
        print(
            f"Perfil     : {cfg.perfil} ({estado_perfil})  "
            f"shared-users={parametros.get('shared-users')} "
            f"idle-timeout={parametros.get('idle-timeout')}"
        )

        cambios = mt.asegurar_http_pap()
        if cambios:
            print(
                "login-by   : http-pap añadido a "
                + ", ".join(cambios)
                + "  (login por URL habilitado)"
            )
        else:
            print("login-by   : http-pap ya estaba activo")

        portal = resolver_portal(mt, cfg)
        print(f"Portal     : {portal}/login")
        print(f"SSID       : {cfg.ssid}")
        print()
        print("Listo. Ya puedes crear tickets con:")
        print("  ./scripts/ticket_qr.py crear -n 10 -t 1h")
    return 0


def comando_estado(args: argparse.Namespace, cfg: Config) -> int:
    with conectar(cfg) as mt:
        titulo("Estado del laboratorio")
        print(f"RouterOS   : {mt.identidad()} ({mt.version()})")
        print(f"API        : {cfg.host}:{cfg.puerto}  OK")

        portal = mt.detectar_portal() or cfg.portal
        print(f"Portal     : {portal or '(no detectado)'}/login")
        print(f"SSID       : {cfg.ssid}  (configurado en hostapd)")

        for servidor in mt.servidores_hotspot():
            print(
                f"Hotspot    : {servidor.get('name')} "
                f"({servidor.get('interface')}) -> perfil "
                f"{servidor.get('profile')}"
            )

        perfiles = {p.get("name"): p for p in mt.perfiles_hotspot()}
        for nombre in mt.perfiles_hotspot_usados():
            perfil = perfiles.get(nombre, {})
            login_by = perfil.get("login-by", "?")
            estado = "OK" if "http-pap" in login_by else "FALTA http-pap"
            print(f"login-by   : {login_by}  [{estado}]")

        perfiles_usuario = {p.get("name") for p in mt.perfiles_usuario()}
        if cfg.perfil in perfiles_usuario:
            print(f"Perfil QR  : {cfg.perfil}  OK")
        else:
            print(
                f"Perfil QR  : {cfg.perfil}  "
                f"{Color(cfg.color).aviso('NO existe (ejecuta setup)')}"
            )

        usuarios = mt.usuarios()
        tickets = [u for u in usuarios if es_ticket(u, cfg)]
        activos = mt.activos()
        activos_qr = [
            a for a in activos if any(a.get("user") == t.get("name") for t in tickets)
        ]
        print()
        print(f"Tickets QR : {len(tickets)}")
        print(f"Activos QR : {len(activos_qr)}")
        if activos_qr:
            for a in activos_qr:
                print(
                    f"  - {a.get('user'):<14} {a.get('address', '?'):<16} "
                    f"{a.get('uptime', '?')}"
                )
    return 0


def comando_crear(args: argparse.Namespace, cfg: Config) -> int:
    cantidad = int(getattr(args, "cantidad", 1))
    if cantidad < 1 or cantidad > 500:
        raise ErrorApp("La cantidad debe estar entre 1 y 500.")
    tiempo = validar_duracion(getattr(args, "tiempo", "1h"))
    lote = sanitizar_nombre(
        getattr(args, "lote", "")
        or datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    nota = (getattr(args, "nota", "") or "").strip()
    limite_bytes = (getattr(args, "limite_bytes", "") or "").strip()
    salida = getattr(args, "salida", "") or ""
    destino = (
        Path(salida).expanduser()
        if salida
        else cfg.dir_tickets / lote
    )
    if destino.exists() and any(destino.iterdir()):
        destino = cfg.dir_tickets / f"{lote}-{datetime.now().strftime('%H%M%S')}"

    with conectar(cfg) as mt:
        destino.mkdir(parents=True, exist_ok=True)
        titulo(f"Creando {cantidad} ticket(s) QR — lote {lote}")
        estado, _ = mt.asegurar_perfil(cfg)
        cambios = mt.asegurar_http_pap()
        if cambios:
            print(f"login-by http-pap añadido a: {', '.join(cambios)}")
        portal = resolver_portal(mt, cfg)
        print(f"Perfil     : {cfg.perfil} ({estado})")
        print(f"Portal     : {portal}/login")
        print(f"Duración   : {tiempo} de conexión")
        if limite_bytes:
            print(f"Límite     : {limite_bytes} de tráfico total")
        print(f"Salida     : {destino}")
        print()

        existentes = {u.get("name") for u in mt.usuarios() if u.get("name")}
        tickets: list[Ticket] = []
        for numero in range(1, cantidad + 1):
            codigo = generar_codigo(cfg.prefijo, existentes)
            existentes.add(codigo)
            password = generar_password(8)
            creado = datetime.now().strftime("%Y-%m-%d %H:%M")
            comentario = f"{MARCA_COMENTARIO}{lote}|{creado}|{tiempo}"
            if nota:
                comentario += f"|{nota}"

            mt.crear_usuario(
                codigo=codigo,
                password=password,
                perfil=cfg.perfil,
                tiempo=tiempo,
                comentario=comentario,
                limite_bytes=limite_bytes,
            )

            login_url = f"{portal}/login?" + urlencode(
                {"username": codigo, "password": password}
            )
            ticket = Ticket(
                codigo=codigo,
                password=password,
                perfil=cfg.perfil,
                limite_uptime=tiempo,
                lote=lote,
                creado=creado,
                login_url=login_url,
                portal=portal,
                nota=nota,
            )
            guardar_ticket(ticket, cfg, destino)
            tickets.append(ticket)
            print(
                f"  [{numero:>3}/{cantidad}] {codigo}  "
                f"clave {password}  ->  _ticket.png"
            )

        escribir_csv(destino, tickets, cfg)
        escribir_html(destino, tickets)
        escribir_resumen(destino, tickets, cfg, portal)

    print()
    print(Color(cfg.color).ok(f"Listo: {cantidad} ticket(s) creados."))
    print(f"Abre la página imprimible: {destino / 'tickets.html'}")
    print(f"Datos del lote          : {destino / 'tickets.csv'}")
    return 0


def comando_listar(args: argparse.Namespace, cfg: Config) -> int:
    with conectar(cfg) as mt:
        usuarios = mt.usuarios()
        activos = {a.get("user"): a for a in mt.activos()}
        todas = bool(getattr(args, "todas", False))
        if not todas:
            usuarios = [u for u in usuarios if es_ticket(u, cfg)]

        if not usuarios:
            print("No hay tickets QR. Crea algunos con: ticket_qr.py crear")
            return 0

        usuarios.sort(key=lambda u: (u.get("comment") or "", u.get("name") or ""))
        titulo(
            "Tickets QR" if not todas else "Todos los usuarios del hotspot"
        )
        filas = []
        for u in usuarios:
            comentario = parsear_comentario(u.get("comment") or "")
            limite = u.get("limit-uptime") or "—"
            activo = activos.get(u.get("name"))
            usado_seg = duracion_a_segundos(u.get("uptime") or "0s")
            if activo:
                usado_seg += duracion_a_segundos(activo.get("uptime") or "0s")
            usado = formatear_duracion(usado_seg) if usado_seg else "0s"
            if limite not in ("—", "none", "0s"):
                restante = duracion_a_segundos(limite) - usado_seg
                if u.get("disabled") == "true":
                    estado = "deshab."
                elif restante <= 0:
                    estado = "agotado"
                elif activo:
                    estado = "activo"
                else:
                    estado = "libre"
            else:
                estado = "activo" if activo else "libre"
            filas.append(
                [
                    u.get("name", "?"),
                    u.get("profile", "?"),
                    limite,
                    usado,
                    estado,
                    comentario.get("lote", ""),
                    comentario.get("creado", ""),
                    comentario.get("nota", ""),
                ]
            )
        tabla(
            ["USUARIO", "PERFIL", "LÍMITE", "USADO", "ESTADO", "LOTE", "CREADO", "NOTA"],
            filas,
        )
        print()
        print(f"Total: {len(usuarios)}")
    return 0


def comando_activos(args: argparse.Namespace, cfg: Config) -> int:
    with conectar(cfg) as mt:
        activos = mt.activos()
        tickets = {u.get("name") for u in mt.usuarios() if es_ticket(u, cfg)}
        titulo("Sesiones activas del hotspot")
        if not activos:
            print("No hay sesiones activas.")
            return 0
        filas = []
        for a in activos:
            usuario = a.get("user", "?")
            filas.append(
                [
                    usuario,
                    a.get("address", "?"),
                    a.get("mac-address", "?"),
                    a.get("uptime", "?"),
                    formatear_bytes(a.get("bytes-in", 0)),
                    formatear_bytes(a.get("bytes-out", 0)),
                    a.get("login-by", "?"),
                    "QR" if usuario in tickets else "otro",
                ]
            )
        tabla(
            ["USUARIO", "IP", "MAC", "UPTIME", "RX", "TX", "LOGIN", "TIPO"],
            filas,
        )
        print()
        print(f"Total: {len(activos)} sesión(es)")
    return 0


def _seleccionar_para_eliminar(
    usuarios: list[dict[str, Any]],
    cfg: Config,
    nombres: Sequence[str],
    lote: str,
    todos: bool,
    forzar: bool = False,
) -> list[dict[str, Any]]:
    seleccion: list[dict[str, Any]] = []
    nombres_set = {n.strip() for n in nombres if n.strip()}
    for u in usuarios:
        nombre = u.get("name", "")
        comentario = u.get("comment") or ""
        if not forzar and not es_ticket(u, cfg):
            continue
        if nombres_set and nombre not in nombres_set:
            continue
        if lote and f"|{lote}|" not in comentario:
            continue
        if not (nombres_set or lote or todos):
            continue
        seleccion.append(u)
    return seleccion


def comando_eliminar(args: argparse.Namespace, cfg: Config) -> int:
    nombres_crudos = getattr(args, "nombre", None) or []
    nombres = [
        n.strip()
        for crudo in nombres_crudos
        for n in str(crudo).split(",")
        if n.strip()
    ]
    lote = (getattr(args, "lote", "") or "").strip()
    todos = bool(getattr(args, "todos", False))
    forzar = bool(getattr(args, "forzar", False))
    if not (nombres or lote or todos):
        raise ErrorApp(
            "Indica qué eliminar: --nombre CODIGO, --lote LOTE o --todos."
        )

    with conectar(cfg) as mt:
        usuarios = mt.usuarios()
        seleccion = _seleccionar_para_eliminar(
            usuarios, cfg, nombres, lote, todos, forzar
        )
        if not seleccion:
            print("No encontré tickets que coincidan.")
            return 0

        print("Se eliminarán:")
        for u in seleccion:
            print(f"  - {u.get('name')}  ({u.get('comment', '')})")
        if not getattr(args, "si", False):
            try:
                respuesta = input(f"\n¿Eliminar {len(seleccion)} ticket(s)? [s/N]: ")
            except (EOFError, KeyboardInterrupt):
                print("\nCancelado.")
                return 1
            if respuesta.strip().lower() not in ("s", "si", "sí", "y", "yes"):
                print("Cancelado.")
                return 1

        activos = mt.activos()
        cookies = mt.cookies()
        eliminados = 0
        for u in seleccion:
            nombre = u.get("name")
            for a in activos:
                if a.get("user") == nombre:
                    mt.eliminar_activo(a["id"])
            for c in cookies:
                if c.get("user") == nombre:
                    mt.eliminar_cookie(c["id"])
            mt.eliminar_usuario(u["id"])
            eliminados += 1

    print(Color(cfg.color).ok(f"Eliminados {eliminados} ticket(s)."))
    return 0


def comando_qr(args: argparse.Namespace, cfg: Config) -> int:
    usuario = (getattr(args, "usuario", "") or "").strip()
    if not usuario:
        raise ErrorApp("Indica el usuario con --usuario.")
    password = getattr(args, "password", "") or ""
    if not password:
        password = getpass.getpass(f"Clave de {usuario}: ")
    if not password:
        raise ErrorApp("La clave no puede estar vacía.")

    lote = f"qr-{sanitizar_nombre(usuario)}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    destino = (
        Path(getattr(args, "salida", "")).expanduser()
        if getattr(args, "salida", "")
        else cfg.dir_tickets / lote
    )

    with conectar(cfg) as mt:
        if not getattr(args, "no_verificar", False):
            encontrado = any(
                u.get("name") == usuario for u in mt.usuarios()
            )
            if not encontrado:
                raise ErrorApp(
                    f"El usuario {usuario!r} no existe en /ip/hotspot/user.\n"
                    "Si es un usuario RADIUS o externo, usa --no-verificar."
                )
        portal = resolver_portal(mt, cfg)

    destino.mkdir(parents=True, exist_ok=True)
    login_url = f"{portal}/login?" + urlencode(
        {"username": usuario, "password": password}
    )
    ticket = Ticket(
        codigo=usuario,
        password=password,
        perfil="(existente)",
        limite_uptime="según perfil",
        lote=lote,
        creado=datetime.now().strftime("%Y-%m-%d %H:%M"),
        login_url=login_url,
        portal=portal,
    )
    guardar_ticket(ticket, cfg, destino)
    escribir_csv(destino, [ticket], cfg)
    escribir_html(destino, [ticket])
    escribir_resumen(destino, [ticket], cfg, portal)

    print(Color(cfg.color).ok(f"QR generado para {usuario}."))
    print(f"Tarjeta : {destino / (nombre_archivo(usuario) + '_ticket.png')}")
    print(f"Login   : {destino / (nombre_archivo(usuario) + '_login.png')}")
    print(f"WiFi    : {destino / (nombre_archivo(usuario) + '_wifi.png')}")
    print(f"HTML    : {destino / 'tickets.html'}")
    return 0


# ---------------------------------------------------------------------------
# Menú interactivo
# ---------------------------------------------------------------------------


def _preguntar(texto: str, defecto: str = "") -> str:
    valor = input(f"{texto}" + (f" [{defecto}]" if defecto else "") + ": ").strip()
    return valor or defecto


def menu(cfg: Config) -> int:
    while True:
        print()
        print("=" * 64)
        print("  TICKETS QR — HOTSPOT MIKROTIK-LAB")
        print("=" * 64)
        print("  1) Estado del laboratorio")
        print("  2) Crear tickets QR")
        print("  3) Listar tickets")
        print("  4) Ver sesiones activas")
        print("  5) Eliminar tickets")
        print("  6) QR para un usuario existente")
        print("  7) Preparar hotspot (setup)")
        print("  0) Salir")
        print()
        try:
            opcion = input("Opción: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        try:
            if opcion == "0":
                return 0
            if opcion == "1":
                comando_estado(argparse.Namespace(), cfg)
            elif opcion == "2":
                cantidad = _preguntar("Cantidad", "1")
                tiempo = _preguntar("Duración (30m, 1h, 1d)", "1h")
                lote = _preguntar(
                    "Lote", datetime.now().strftime("%Y%m%d-%H%M%S")
                )
                nota = _preguntar("Nota (opcional)", "")
                args = argparse.Namespace(
                    cantidad=int(cantidad),
                    tiempo=tiempo,
                    lote=lote,
                    nota=nota,
                    limite_bytes="",
                    salida="",
                )
                comando_crear(args, cfg)
            elif opcion == "3":
                comando_listar(argparse.Namespace(todas=False), cfg)
            elif opcion == "4":
                comando_activos(argparse.Namespace(), cfg)
            elif opcion == "5":
                print("  1) Por nombre  2) Por lote  3) Todos los tickets QR")
                modo = _preguntar("Modo", "2")
                args = argparse.Namespace(
                    nombre=[], lote="", todos=False, si=False
                )
                if modo == "1":
                    args.nombre = [
                        _preguntar("Código(s), separados por coma", "")
                    ]
                    args.nombre = [
                        n.strip()
                        for n in args.nombre[0].split(",")
                        if n.strip()
                    ]
                elif modo == "3":
                    args.todos = True
                else:
                    args.lote = _preguntar("Lote", "")
                comando_eliminar(args, cfg)
            elif opcion == "6":
                usuario = _preguntar("Usuario", "Armindev")
                password = getpass.getpass(f"Clave de {usuario}: ")
                args = argparse.Namespace(
                    usuario=usuario,
                    password=password,
                    no_verificar=False,
                    salida="",
                )
                comando_qr(args, cfg)
            elif opcion == "7":
                comando_setup(
                    argparse.Namespace(forzar=False), cfg
                )
            else:
                print("Opción no válida.")
        except ErrorApp as exc:
            print(Color(cfg.color).error(f"\nError: {exc}"))
        except KeyboardInterrupt:
            print("\nCancelado.")
        except Exception as exc:  # noqa: BLE001
            print(Color(cfg.color).error(f"\nError inesperado: {exc}"))
            if cfg.debug:
                traceback.print_exc()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parser_comun() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--host", default=argparse.SUPPRESS)
    parser.add_argument("--puerto", type=int, default=argparse.SUPPRESS)
    parser.add_argument("--api-usuario", default=argparse.SUPPRESS)
    parser.add_argument("--api-password", default=argparse.SUPPRESS)
    parser.add_argument("--ssid", default=argparse.SUPPRESS)
    parser.add_argument("--wifi-password", default=argparse.SUPPRESS)
    parser.add_argument("--portal", default=argparse.SUPPRESS)
    parser.add_argument("--perfil", default=argparse.SUPPRESS)
    parser.add_argument("--prefijo", default=argparse.SUPPRESS)
    parser.add_argument("--rate-limit", default=argparse.SUPPRESS)
    parser.add_argument("--dir-tickets", default=argparse.SUPPRESS)
    parser.add_argument("--sin-color", action="store_true", default=argparse.SUPPRESS)
    parser.add_argument("--debug", action="store_true", default=argparse.SUPPRESS)
    return parser


def construir_parser() -> argparse.ArgumentParser:
    comun = parser_comun()
    parser = argparse.ArgumentParser(
        description=(
            "Crea tickets QR para el hotspot MikroTik del laboratorio. "
            "El QR de acceso usa login HTTP-PAP por URL."
        ),
        epilog=(
            "Ejemplos:\n"
            "  ./scripts/ticket_qr.py setup\n"
            "  ./scripts/ticket_qr.py crear -n 10 -t 1h --nota 'Evento'\n"
            "  ./scripts/ticket_qr.py listar\n"
            "  ./scripts/ticket_qr.py activos\n"
            "  ./scripts/ticket_qr.py eliminar --lote 20261023-153000\n"
            "  ./scripts/ticket_qr.py qr --usuario Armindev --password armin2DEV\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[comun],
    )
    sub = parser.add_subparsers(dest="comando")

    p = sub.add_parser(
        "setup",
        parents=[comun],
        help="Prepara el perfil de tickets y login HTTP-PAP",
    )
    p.add_argument(
        "--forzar",
        action="store_true",
        help="Actualiza el perfil de usuario si ya existe",
    )

    p = sub.add_parser(
        "crear",
        parents=[comun],
        help="Crea tickets y genera los QR",
    )
    p.add_argument("-n", "--cantidad", type=int, default=1)
    p.add_argument("-t", "--tiempo", default="1h", help="30m, 1h, 1h30m, 1d...")
    p.add_argument("--lote", default="", help="Nombre del lote")
    p.add_argument("--nota", default="", help="Texto libre en el comentario")
    p.add_argument(
        "--limite-bytes", default="", help="Ej.: 500M, 1G (tráfico total)"
    )
    p.add_argument(
        "--salida", default="", help="Carpeta de salida (por defecto tickets/<lote>)"
    )

    p = sub.add_parser(
        "listar",
        parents=[comun],
        help="Lista los tickets QR (o todos los usuarios)",
    )
    p.add_argument(
        "--todas", action="store_true", help="Incluye usuarios que no son tickets"
    )

    sub.add_parser(
        "activos", parents=[comun], help="Muestra las sesiones hotspot activas"
    )

    p = sub.add_parser(
        "eliminar",
        parents=[comun],
        help="Elimina tickets (y sus sesiones/cookies)",
    )
    p.add_argument("--nombre", action="append", default=[], help="Código del ticket")
    p.add_argument("--lote", default="", help="Elimina todo un lote")
    p.add_argument("--todos", action="store_true", help="Todos los tickets QR")
    p.add_argument("--si", action="store_true", help="No pedir confirmación")
    p.add_argument(
        "--forzar",
        action="store_true",
        help="Permite borrar usuarios que no son tickets QR (peligroso)",
    )

    p = sub.add_parser(
        "qr",
        parents=[comun],
        help="Genera QR para un usuario que ya existe",
    )
    p.add_argument("--usuario", required=True)
    p.add_argument("--password", default="", help="Si se omite, se pide por teclado")
    p.add_argument(
        "--no-verificar",
        action="store_true",
        help="No comprobar que el usuario exista en el router",
    )
    p.add_argument("--salida", default="")

    sub.add_parser(
        "estado", parents=[comun], help="Resumen del hotspot y los tickets"
    )
    sub.add_parser("menu", parents=[comun], help="Menú interactivo")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    cargar_env()
    args = construir_parser().parse_args(argv)
    requerir_dependencias()
    cfg = Config.desde_args(args)

    comandos = {
        "setup": comando_setup,
        "crear": comando_crear,
        "listar": comando_listar,
        "activos": comando_activos,
        "eliminar": comando_eliminar,
        "qr": comando_qr,
        "estado": comando_estado,
    }

    try:
        if args.comando in (None, "menu"):
            return menu(cfg)
        return comandos[args.comando](args, cfg)
    except ErrorApp as exc:
        print(Color(cfg.color).error(f"\nError: {exc}"), file=sys.stderr)
        if cfg.debug:
            traceback.print_exc()
        return 1
    except KeyboardInterrupt:
        print("\nCancelado.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(
            Color(cfg.color).error(f"\nError inesperado: {type(exc).__name__}: {exc}"),
            file=sys.stderr,
        )
        if cfg.debug:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
