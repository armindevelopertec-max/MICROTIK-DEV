#!/usr/bin/env python3
"""Panel web de administración de tickets QR para MikroTik Hotspot.

Uso:
  ./scripts/admin-web
  ./scripts/admin-web --host 0.0.0.0 --port 8080

Configuración vía .env / variables:
  WEB_ADMIN_USER, WEB_ADMIN_PASSWORD, WEB_SECRET_KEY, WEB_HOST, WEB_PORT
"""

from __future__ import annotations

import argparse
import csv
import hmac
import io
import json
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))
import ticket_qr as core

APP_DIR = Path(__file__).resolve().parent


def _cargar_secreto() -> str:
    clave = os.environ.get("WEB_SECRET_KEY", "").strip()
    if clave:
        return clave
    ruta = BASE_DIR / ".web-secret"
    if ruta.exists():
        clave = ruta.read_text(encoding="utf-8").strip()
        if clave:
            return clave
    clave = secrets.token_hex(32)
    ruta.write_text(clave + "\n", encoding="utf-8")
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass
    return clave


core.cargar_env()
CFG = core.Config.desde_args(argparse.Namespace())

WEB_USER = os.environ.get("WEB_ADMIN_USER", "admin")
WEB_PASSWORD = os.environ.get("WEB_ADMIN_PASSWORD", CFG.password)
WEB_HOST_DEFAULT = os.environ.get("WEB_HOST", "127.0.0.1")
WEB_PORT_DEFAULT = int(os.environ.get("WEB_PORT", "5000"))

app = Flask(
    __name__,
    template_folder=str(APP_DIR / "templates"),
    static_folder=str(APP_DIR / "static"),
)
app.secret_key = _cargar_secreto()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)


def csrf_token() -> str:
    token = session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf"] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


def validar_csrf() -> None:
    esperado = session.get("csrf", "")
    recibido = (
        request.headers.get("X-CSRF-Token")
        or request.form.get("csrf_token")
        or ""
    )
    if not esperado or not recibido or not hmac.compare_digest(esperado, recibido):
        abort(400, description="CSRF token inválido")


def api_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return jsonify({"ok": False, "error": "No autenticado"}), 401
        return f(*args, **kwargs)

    return wrapper


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            next_url = request.full_path
            if next_url.startswith("/?"):
                next_url = "/"
            return redirect(url_for("login", next=next_url))
        return f(*args, **kwargs)

    return wrapper


class Monitor:
    def __init__(self, cfg: core.Config):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._state = self._estado_inicial()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def _estado_inicial(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": "Iniciando monitor...",
            "ts": time.time(),
            "identity": "?",
            "version": "?",
            "portal": self.cfg.portal or "",
            "ssid": self.cfg.ssid,
            "wifi_password": self.cfg.wifi_password,
            "login_by": "",
            "http_pap": False,
            "perfil_ok": False,
            "hotspot": [],
            "usuarios": [],
            "activos": [],
            "resumen": {
                "tickets": 0,
                "activos": 0,
                "disponibles": 0,
                "agotados": 0,
                "libres": 0,
                "total": 0,
            },
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="monitor-mikrotik", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def refrescar(self) -> None:
        self._wake.set()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                with core.conectar(self.cfg) as mt:
                    nuevo = self._leer(mt)
                with self._lock:
                    self._state = nuevo
            except Exception as exc:
                with self._lock:
                    estado = dict(self._state)
                    estado.update(
                        {
                            "ok": False,
                            "error": f"{type(exc).__name__}: {exc}",
                            "ts": time.time(),
                        }
                    )
                    self._state = estado
            self._wake.wait(2.0)
            self._wake.clear()

    def _leer(self, mt: core.MikroTik) -> dict[str, Any]:
        usuarios = mt.usuarios()
        activos = mt.activos()
        perfiles_hp = mt.perfiles_hotspot()
        servidores = mt.servidores_hotspot()
        perfiles_up = mt.perfiles_usuario()

        perfiles_hp_map = {p.get("name"): p for p in perfiles_hp}
        portal = core.normalizar_portal(self.cfg.portal) or mt.detectar_portal() or ""

        login_by_parts: list[str] = []
        for nombre in mt.perfiles_hotspot_usados():
            p = perfiles_hp_map.get(nombre, {})
            lb = p.get("login-by") or ""
            for part in str(lb).split(","):
                part = part.strip()
                if part and part not in login_by_parts:
                    login_by_parts.append(part)
        login_by_str = ",".join(login_by_parts)

        http_pap = "http-pap" in login_by_str
        perfiles_up_nombres = {p.get("name") for p in perfiles_up}
        perfil_ok = self.cfg.perfil in perfiles_up_nombres

        activos_por_usuario: dict[str, list[dict[str, Any]]] = {}
        for a in activos:
            usr = a.get("user") or ""
            if not usr:
                continue
            activos_por_usuario.setdefault(usr, []).append(a)

        usuarios_json: list[dict[str, Any]] = []
        for u in usuarios:
            nombre = u.get("name") or ""
            if not nombre:
                continue
            activo_list = activos_por_usuario.get(nombre, [])
            usado_seg = core.duracion_a_segundos(u.get("uptime") or "0s")
            for a in activo_list:
                usado_seg += core.duracion_a_segundos(a.get("uptime") or "0s")
            limite = u.get("limit-uptime") or "—"
            limite_seg = core.duracion_a_segundos(limite)
            if limite_seg > 0:
                restante_seg = max(0, limite_seg - usado_seg)
            else:
                restante_seg = None
            if u.get("disabled") == "true":
                estado = "deshabilitado"
            elif limite_seg > 0 and restante_seg is not None and restante_seg <= 0:
                estado = "agotado"
            elif activo_list:
                estado = "activo"
            else:
                estado = "libre"
            comentario = core.parsear_comentario(u.get("comment") or "")
            ip_activo = ""
            mac_activo = ""
            if activo_list:
                ip_activo = activo_list[0].get("address") or ""
                mac_activo = activo_list[0].get("mac-address") or ""
            usuarios_json.append(
                {
                    "codigo": nombre,
                    "perfil": u.get("profile") or "—",
                    "password": u.get("password") or "",
                    "limite": limite,
                    "limite_segundos": limite_seg,
                    "usado_segundos": usado_seg,
                    "usado": core.formatear_duracion(usado_seg),
                    "restante_segundos": restante_seg,
                    "restante": core.formatear_duracion(restante_seg)
                    if restante_seg is not None
                    else "—",
                    "estado": estado,
                    "lote": comentario.get("lote") or "—",
                    "creado": comentario.get("creado") or "—",
                    "nota": comentario.get("nota") or "",
                    "comment": u.get("comment") or "",
                    "es_ticket": bool(core.es_ticket(u, self.cfg)),
                    "activo": bool(activo_list),
                    "sesiones": len(activo_list),
                    "ip": ip_activo,
                    "mac": mac_activo,
                    "bytes_in": u.get("bytes-in") or 0,
                    "bytes_out": u.get("bytes-out") or 0,
                }
            )

        activos_json: list[dict[str, Any]] = []
        for a in activos:
            usr = a.get("user") or ""
            uref = None
            for uu in usuarios_json:
                if uu["codigo"] == usr:
                    uref = uu
                    break
            activos_json.append(
                {
                    "usuario": usr,
                    "ip": a.get("address") or "",
                    "mac": a.get("mac-address") or "",
                    "uptime_segundos": core.duracion_a_segundos(a.get("uptime") or "0s"),
                    "uptime": core.formatear_duracion(
                        core.duracion_a_segundos(a.get("uptime") or "0s")
                    ),
                    "bytes_in": a.get("bytes-in") or 0,
                    "bytes_out": a.get("bytes-out") or 0,
                    "login_by": a.get("login-by") or "",
                    "es_ticket": bool(uref and uref.get("es_ticket")),
                }
            )

        tickets = [u for u in usuarios_json if u.get("es_ticket")]
        resumen = {
            "tickets": len(tickets),
            "activos": sum(1 for t in tickets if t.get("activo")),
            "disponibles": sum(
                1 for t in tickets if t.get("estado") in ("libre",)
            ),
            "agotados": sum(1 for t in tickets if t.get("estado") == "agotado"),
            "libres": sum(1 for t in tickets if t.get("estado") == "libre"),
            "total": len(usuarios_json),
        }

        try:
            identity = mt.identidad()
            version = mt.version()
        except Exception:
            identity = "?"
            version = "?"

        return {
            "ok": True,
            "error": None,
            "ts": time.time(),
            "identity": identity,
            "version": version,
            "portal": portal,
            "ssid": self.cfg.ssid,
            "wifi_password": self.cfg.wifi_password,
            "login_by": login_by_str,
            "http_pap": http_pap,
            "perfil_ok": perfil_ok,
            "perfil": self.cfg.perfil,
            "hotspot": [
                {"name": s.get("name"), "interface": s.get("interface"), "profile": s.get("profile")}
                for s in servidores
            ],
            "usuarios": usuarios_json,
            "activos": activos_json,
            "resumen": resumen,
        }


monitor = Monitor(CFG)
monitor.start()


@app.after_request
def after_request(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.errorhandler(400)
def bad_request(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": str(getattr(e, "description", e))}), 400
    flash(str(getattr(e, "description", e)), "error")
    return redirect(request.referrer or url_for("index"))


@app.errorhandler(401)
def unauthorized(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "No autenticado"}), 401
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin"):
        return redirect(url_for("index"))
    if request.method == "POST":
        try:
            validar_csrf()
        except Exception:
            flash("Token de seguridad inválido. Recarga la página.", "error")
            return render_template("login.html")
        user = (request.form.get("usuario") or "").strip()
        pw = request.form.get("password") or ""
        if hmac.compare_digest(user, WEB_USER) and hmac.compare_digest(pw, WEB_PASSWORD):
            session.clear()
            session["admin"] = True
            session.permanent = True
            csrf_token()
            nxt = request.args.get("next") or ""
            if not nxt or not nxt.startswith("/") or nxt.startswith("//"):
                nxt = url_for("index")
            return redirect(nxt)
        time.sleep(0.4)
        flash("Credenciales incorrectas", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    try:
        validar_csrf()
    except Exception:
        pass
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    snap = monitor.snapshot()
    portal = snap.get("portal") or CFG.portal or ""
    config_ui = {
        "ssid": CFG.ssid,
        "portal": portal,
        "profile": CFG.perfil,
        "host": CFG.host,
        "port": CFG.puerto,
    }
    return render_template("index.html", estado=snap, config_ui=config_ui)


@app.route("/api/estado")
@api_login_required
def api_estado():
    return jsonify(monitor.snapshot())


@app.route("/api/usuarios/<codigo>")
@api_login_required
def api_usuario_detalle(codigo: str):
    snap = monitor.snapshot()
    for u in snap.get("usuarios", []):
        if u.get("codigo") == codigo:
            return jsonify(
                {
                    "ok": True,
                    "codigo": u.get("codigo"),
                    "password": u.get("password"),
                    "perfil": u.get("perfil"),
                    "limite": u.get("limite"),
                    "estado": u.get("estado"),
                    "lote": u.get("lote"),
                    "creado": u.get("creado"),
                    "nota": u.get("nota"),
                    "es_ticket": u.get("es_ticket"),
                    "activo": u.get("activo"),
                    "ip": u.get("ip"),
                    "mac": u.get("mac"),
                }
            )
    try:
        with core.conectar(CFG) as mt:
            portal = core.resolver_portal(mt, CFG)
            for u in mt.usuarios():
                if u.get("name") == codigo:
                    return jsonify(
                        {
                            "ok": True,
                            "codigo": codigo,
                            "password": u.get("password") or "",
                            "perfil": u.get("profile") or "—",
                            "limite": u.get("limit-uptime") or "—",
                            "estado": "—",
                            "lote": core.parsear_comentario(u.get("comment") or "").get(
                                "lote"
                            )
                            or "—",
                            "creado": core.parsear_comentario(u.get("comment") or "").get(
                                "creado"
                            )
                            or "—",
                            "nota": core.parsear_comentario(u.get("comment") or "").get(
                                "nota"
                            )
                            or "",
                            "es_ticket": bool(core.es_ticket(u, CFG)),
                            "activo": False,
                            "ip": "",
                            "mac": "",
                            "portal": portal,
                        }
                    )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": False, "error": "Usuario no encontrado"}), 404


@app.route("/api/lotes")
@api_login_required
def api_lotes():
    base = CFG.dir_tickets
    lotes = []
    if base.exists():
        for d in sorted(
            [p for p in base.iterdir() if p.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            csvp = d / "tickets.csv"
            htmlp = d / "tickets.html"
            count = 0
            if csvp.exists():
                try:
                    with csvp.open(encoding="utf-8-sig") as f:
                        lector = csv.reader(f)
                        next(lector, None)
                        count = sum(1 for _ in lector)
                except Exception:
                    count = 0
            lotes.append(
                {
                    "lote": d.name,
                    "tickets": count,
                    "mtime": int(d.stat().st_mtime),
                    "tiene_csv": csvp.exists(),
                    "tiene_html": htmlp.exists(),
                    "tiene_resumen": (d / "resumen.txt").exists(),
                }
            )
    return jsonify({"ok": True, "lotes": lotes})


@app.route("/api/lotes/<lote>/<archivo>")
@api_login_required
def api_lote_archivo(lote: str, archivo: str):
    if archivo not in ("tickets.csv", "tickets.html", "resumen.txt"):
        abort(404)
    safe = core.sanitizar_nombre(lote)
    path = (CFG.dir_tickets / safe / archivo).resolve()
    base_res = CFG.dir_tickets.resolve()
    if base_res not in path.parents and path != base_res:
        abort(404)
    if not path.exists():
        abort(404)
    as_attachment = archivo != "tickets.html"
    return send_file(path, as_attachment=as_attachment, download_name=path.name)


@app.route("/api/tickets", methods=["POST"])
@api_login_required
def api_crear_tickets():
    try:
        validar_csrf()
    except Exception as exc:
        return jsonify({"ok": False, "error": str(getattr(exc, "description", exc))}), 400
    try:
        datos = request.get_json(silent=True) or {}
        cantidad = int(datos.get("cantidad") or 1)
        if cantidad < 1 or cantidad > 200:
            raise core.ErrorApp("La cantidad debe estar entre 1 y 200.")
        tiempo = core.validar_duracion(datos.get("tiempo") or "1h")
        lote_req = core.sanitizar_nombre(datos.get("lote") or "")
        if not lote_req:
            lote_req = datetime.now().strftime("web-%Y%m%d-%H%M%S")
        nota = str(datos.get("nota") or "")[:200]
        limite_bytes = str(datos.get("limite_bytes") or "").strip()
        rate_limit = str(datos.get("rate_limit") or "").strip()
        mismo_login = bool(datos.get("mismo_login"))
        dispositivos_simultaneos = int(datos.get("dispositivos_simultaneos") or 5)
        if dispositivos_simultaneos < 2:
            dispositivos_simultaneos = 2
        if dispositivos_simultaneos > 50:
            dispositivos_simultaneos = 50
        if mismo_login:
            cantidad = 1

        perfil_usar = CFG.perfil
        cfg_usar = CFG
        if mismo_login:
            perfil_usar = f"{CFG.perfil}-shared{dispositivos_simultaneos}"
            try:
                cfg_usar = dataclasses.replace(CFG, perfil=perfil_usar, rate_limit=rate_limit)
            except Exception:
                cfg_usar = CFG
        elif rate_limit:
            perfil_usar = f"{CFG.perfil}-{core.sanitizar_nombre(rate_limit)}"
            try:
                cfg_usar = dataclasses.replace(CFG, perfil=perfil_usar, rate_limit=rate_limit)
            except Exception:
                cfg_usar = CFG

        with core.conectar(CFG) as mt:
            if mismo_login:
                parametros: dict = {
                    "shared-users": str(dispositivos_simultaneos),
                    "idle-timeout": "10m",
                    "keepalive-timeout": "2m",
                    "add-mac-cookie": "yes",
                    "session-timeout": "0s",
                }
                if cfg_usar.rate_limit:
                    parametros["rate-limit"] = cfg_usar.rate_limit
                existentes_p = {p.get("name"): p for p in mt.perfiles_usuario()}
                if perfil_usar not in existentes_p:
                    mt._r("/ip/hotspot/user/profile").add(name=perfil_usar, **parametros)
                else:
                    mt._r("/ip/hotspot/user/profile").set(id=existentes_p[perfil_usar]["id"], **parametros)
            else:
                mt.asegurar_perfil(cfg_usar)
            mt.asegurar_http_pap()
            portal = core.resolver_portal(mt, CFG)

        destino = CFG.dir_tickets / lote_req
        if destino.exists() and any(destino.iterdir()):
            destino = CFG.dir_tickets / f"{lote_req}-{datetime.now().strftime('%H%M%S')}"

        lote_final = destino.name
        destino.mkdir(parents=True, exist_ok=True)

        tickets_out: list[dict[str, Any]] = []
        with core.conectar(CFG) as mt:
            if mismo_login:
                parametros: dict = {
                    "shared-users": str(dispositivos_simultaneos),
                    "idle-timeout": "10m",
                    "keepalive-timeout": "2m",
                    "add-mac-cookie": "yes",
                    "session-timeout": "0s",
                }
                if cfg_usar.rate_limit:
                    parametros["rate-limit"] = cfg_usar.rate_limit
                existentes_p = {p.get("name"): p for p in mt.perfiles_usuario()}
                if perfil_usar not in existentes_p:
                    mt._r("/ip/hotspot/user/profile").add(name=perfil_usar, **parametros)
                else:
                    mt._r("/ip/hotspot/user/profile").set(id=existentes_p[perfil_usar]["id"], **parametros)
            else:
                mt.asegurar_perfil(cfg_usar)
            mt.asegurar_http_pap()
            portal = core.resolver_portal(mt, CFG)
            existentes = {u.get("name") for u in mt.usuarios() if u.get("name")}
            for i in range(cantidad):
                codigo = core.generar_codigo(CFG.prefijo, existentes)
                existentes.add(codigo)
                password = core.generar_password(8)
                creado = datetime.now().strftime("%Y-%m-%d %H:%M")
                comentario = f"{core.MARCA_COMENTARIO}{lote_final}|{creado}|{tiempo}"
                if nota:
                    comentario += f"|{nota}"
                mt.crear_usuario(
                    codigo=codigo,
                    password=password,
                    perfil=perfil_usar,
                    tiempo=tiempo,
                    comentario=comentario,
                    limite_bytes=limite_bytes,
                )
                login_url = f"{portal}/login?" + urlencode({"username": codigo, "password": password})
                ticket = core.Ticket(
                    codigo=codigo,
                    password=password,
                    perfil=perfil_usar,
                    limite_uptime=tiempo,
                    lote=lote_final,
                    creado=creado,
                    login_url=login_url,
                    portal=portal,
                    nota=nota,
                )
                core.guardar_ticket(ticket, CFG, destino)
                tickets_out.append(
                    {
                        "codigo": codigo,
                        "password": password,
                        "perfil": perfil_usar,
                        "limite_uptime": tiempo,
                        "login_url": login_url,
                        "card_url": f"/api/tickets/{codigo}/qr/ticket",
                        "login_qr_url": f"/api/tickets/{codigo}/qr/login",
                        "wifi_qr_url": f"/api/tickets/{codigo}/qr/wifi",
                    }
                )

        with core.conectar(CFG) as mt:
            usuarios = mt.usuarios()
            lista = []
            portal2 = core.resolver_portal(mt, CFG)
            for u in usuarios:
                if u.get("name") in {x["codigo"] for x in tickets_out}:
                    c = core.parsear_comentario(u.get("comment") or "")
                    login_url2 = f"{portal2}/login?" + urlencode(
                        {"username": u.get("name"), "password": u.get("password") or ""}
                    )
                    lista.append(
                        core.Ticket(
                            codigo=u.get("name"),
                            password=u.get("password") or "",
                            perfil=u.get("profile") or perfil_usar,
                            limite_uptime=u.get("limit-uptime") or tiempo,
                            lote=c.get("lote") or lote_final,
                            creado=c.get("creado") or "",
                            login_url=login_url2,
                            portal=portal2,
                            nota=c.get("nota") or "",
                        )
                    )
            core.escribir_csv(destino, lista, CFG)
            core.escribir_html(destino, lista)
            core.escribir_resumen(destino, lista, CFG, portal2)

        monitor.refrescar()
        return jsonify(
            {
                "ok": True,
                "lote": lote_final,
                "carpeta": str(destino),
                "portal": portal,
                "tickets": tickets_out,
                "csv_url": f"/api/lotes/{lote_final}/tickets.csv",
                "html_url": f"/api/lotes/{lote_final}/tickets.html",
            }
        )
    except core.ErrorApp as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500


@app.route("/api/tickets/<codigo>/eliminar", methods=["POST"])
@api_login_required
def api_eliminar_ticket(codigo: str):
    try:
        validar_csrf()
    except Exception as exc:
        return jsonify({"ok": False, "error": str(getattr(exc, "description", exc))}), 400
    try:
        with core.conectar(CFG) as mt:
            usuarios = mt.usuarios()
            sel = [u for u in usuarios if u.get("name") == codigo]
            if not sel:
                return jsonify({"ok": False, "error": "Usuario no encontrado"}), 404
            u = sel[0]
            if not core.es_ticket(u, CFG):
                return jsonify(
                    {"ok": False, "error": "Solo se pueden eliminar tickets QR desde este panel."}
                ), 400
            activos = mt.activos()
            cookies = mt.cookies()
            for a in activos:
                if a.get("user") == codigo:
                    aid = a.get("id") or a.get(".id")
                    if aid:
                        try:
                            mt._r("/ip/hotspot/active").remove(id=aid)
                        except Exception:
                            pass
            for c in cookies:
                if c.get("user") == codigo:
                    cid = c.get("id") or c.get(".id")
                    if cid:
                        try:
                            mt._r("/ip/hotspot/cookie").remove(id=cid)
                        except Exception:
                            pass
            try:
                uid = u.get("id") or u.get(".id")
                if not uid:
                    raise core.ErrorApp("No se pudo obtener el ID del usuario")
                mt._r("/ip/hotspot/user").remove(id=uid)
            except core.ErrorApp:
                raise
            except Exception as exc:
                raise core.ErrorApp(f"No se pudo eliminar el usuario: {exc}") from exc
        monitor.refrescar()
        return jsonify({"ok": True, "eliminados": 1})
    except core.ErrorApp as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500


@app.route("/api/lotes/<lote>/eliminar", methods=["POST"])
@api_login_required
def api_eliminar_lote(lote: str):
    try:
        validar_csrf()
    except Exception as exc:
        return jsonify({"ok": False, "error": str(getattr(exc, "description", exc))}), 400
    try:
        safe = core.sanitizar_nombre(lote)
        with core.conectar(CFG) as mt:
            usuarios = mt.usuarios()
            sel = [
                u
                for u in usuarios
                if f"|{safe}|" in (u.get("comment") or "") and core.es_ticket(u, CFG)
            ]
            activos = mt.activos()
            cookies = mt.cookies()
            for u in sel:
                nombre = u.get("name")
                for a in activos:
                    if a.get("user") == nombre:
                        aid = a.get("id") or a.get(".id")
                        if aid:
                            try:
                                mt._r("/ip/hotspot/active").remove(id=aid)
                            except Exception:
                                pass
                for c in cookies:
                    if c.get("user") == nombre:
                        cid = c.get("id") or c.get(".id")
                        if cid:
                            try:
                                mt._r("/ip/hotspot/cookie").remove(id=cid)
                            except Exception:
                                pass
                try:
                    uid = u.get("id") or u.get(".id")
                    if uid:
                        mt._r("/ip/hotspot/user").remove(id=uid)
                except Exception:
                    pass
        monitor.refrescar()
        return jsonify({"ok": True, "eliminados": len(sel)})
    except core.ErrorApp as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500


@app.route("/api/activos/<usuario>/desconectar", methods=["POST"])
@api_login_required
def api_desconectar(usuario: str):
    try:
        validar_csrf()
    except Exception as exc:
        return jsonify({"ok": False, "error": str(getattr(exc, "description", exc))}), 400
    try:
        count = 0
        with core.conectar(CFG) as mt:
            activos = mt.activos()
            cookies = mt.cookies()
            for a in activos:
                if a.get("user") == usuario:
                    aid = a.get("id") or a.get(".id")
                    if aid:
                        try:
                            mt._r("/ip/hotspot/active").remove(id=aid)
                            count += 1
                        except Exception:
                            pass
            for c in cookies:
                if c.get("user") == usuario:
                    cid = c.get("id") or c.get(".id")
                    if cid:
                        try:
                            mt._r("/ip/hotspot/cookie").remove(id=cid)
                        except Exception:
                            pass
        monitor.refrescar()
        return jsonify({"ok": True, "desconectados": count})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500


def _buscar_archivo_qr(codigo: str, tipo: str):
    safe = core.nombre_archivo(codigo)
    patron = f"{safe}_{tipo}.png"
    candidatos = list(CFG.dir_tickets.rglob(patron))
    if not candidatos:
        return None
    candidatos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidatos[0]


def _obtener_ticket_obj(codigo: str) -> tuple[core.Ticket | None, str]:
    with core.conectar(CFG) as mt:
        portal = core.resolver_portal(mt, CFG)
        for u in mt.usuarios():
            if u.get("name") == codigo:
                c = core.parsear_comentario(u.get("comment") or "")
                ticket = core.Ticket(
                    codigo=codigo,
                    password=u.get("password") or "",
                    perfil=u.get("profile") or "—",
                    limite_uptime=u.get("limit-uptime") or "—",
                    lote=c.get("lote") or "existente",
                    creado=c.get("creado") or "",
                    login_url="",
                    portal=portal,
                    nota=c.get("nota") or "",
                )
                return ticket, portal
    return None, ""


@app.route("/api/tickets/<codigo>/qr/<tipo>")
@api_login_required
def api_qr_ticket(codigo: str, tipo: str):
    if tipo not in ("ticket", "login", "wifi"):
        abort(404)
    path = _buscar_archivo_qr(codigo, tipo)
    if path and path.exists():
        return send_file(path, mimetype="image/png", download_name=path.name)
    try:
        ticket, portal = _obtener_ticket_obj(codigo)
        if not ticket:
            abort(404)
        if not ticket.password:
            return (
                jsonify({"ok": False, "error": "Este usuario no tiene contraseña legible para generar QR."}),
                400,
            )
        if tipo == "ticket":
            img = core.render_tarjeta(ticket, CFG)
        elif tipo == "wifi":
            payload = ticket.wifi_payload(CFG)
            img = core.qr_imagen(payload, 600)
        else:
            payload = ticket.login_url
            img = core.qr_imagen(payload, 600)
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        buf.seek(0)
        safe = core.nombre_archivo(codigo)
        return send_file(
            buf,
            mimetype="image/png",
            download_name=f"{safe}_{tipo}.png",
        )
    except core.ErrorApp as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Panel web de tickets QR")
    parser.add_argument("--host", default=WEB_HOST_DEFAULT)
    parser.add_argument("--port", type=int, default=WEB_PORT_DEFAULT)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    try:
        core.requerir_dependencias()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    monitor.start()
    print("=" * 70)
    print("  PANEL WEB DE TICKETS QR - MIKROTIK-LAB")
    print("=" * 70)
    print(f"  URL:      http://{args.host}:{args.port}")
    print(f"  Usuario:  {WEB_USER}")
    print(f"  API:      {CFG.host}:{CFG.puerto}")
    print(f"  SSID:     {CFG.ssid}")
    print("=" * 70)
    if args.host not in ("127.0.0.1", "localhost", "::1") and hmac.compare_digest(
        WEB_PASSWORD, CFG.password
    ):
        print(
            "\nAVISO: Estás enlazando en una interfaz no local con la contraseña por defecto.\n"
            "Cambia WEB_ADMIN_PASSWORD en .env.\n",
            file=sys.stderr,
        )
    try:
        app.run(
            host=args.host,
            port=args.port,
            debug=args.debug,
            use_reloader=False,
            threaded=True,
        )
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
