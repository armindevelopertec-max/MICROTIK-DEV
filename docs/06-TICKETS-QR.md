# 06 — Tickets QR para el hotspot (RouterOS API)

**Objetivo:** crear usuarios hotspot desde Python, consumiendo la **API de
RouterOS**, y entregar un **ticket con QR** que permita conectarse a la WiFi y
autenticarse en el portal sin escribir usuario ni contraseña.

El script es [`scripts/ticket_qr.py`](../scripts/ticket_qr.py) y el lanzador
cómodo es [`scripts/ticket-qr`](../scripts/ticket-qr).

---

## 1. Cómo funciona (resumen)

```
┌──────────────┐   1. API 8728    ┌──────────────────────┐
│  tu laptop   │ ───────────────► │  CHR RouterOS        │
│ ticket_qr.py │                  │  /ip hotspot/user    │
└──────┬───────┘                  │  usuario + clave     │
       │                          └──────────┬───────────┘
       │ 2. genera PNG/CSV/HTML              │
       ▼                                     │
  tickets/<lote>/                            │
  ├── QR-XXXX_ticket.png  ◄── se imprime o se muestra en pantalla
  ├── QR-XXXX_wifi.png        (WIFI:T:WPA;S:MIKROTIK-LAB;P:...)
  ├── QR-XXXX_login.png       (http://192.168.77.254/login?username=...&password=...)
  ├── tickets.csv
  └── tickets.html
                                             │
       ┌─────────────────────────────────────┘
       │ 3. el alumno/invitado escanea
       ▼
  ┌──────────────┐   WiFi MIKROTIK-LAB   ┌──────────────────────┐
  │   móvil      │ ────────────────────► │  portal 192.168.77.254│
  │  cámara/QR  │   luego QR de acceso  │  login HTTP-PAP       │
  └──────────────┘ ────────────────────► │  sesión hotspot       │
                                          └──────────────────────┘
```

**Dos QR, no uno.** El primero une el móvil a la WiFi (formato `WIFI:` que
entienden Android e iOS). El segundo abre la URL de login. No es posible que un
único QR estándar haga las dos cosas: primero hay que estar dentro de la red
para que el portal responda. La tarjeta PNG muestra ambos QR numerados.

El login por URL funciona porque el perfil del hotspot incluye el método
**`http-pap`**:

```routeros
/ip hotspot profile set hsprof1 login-by=cookie,http-chap,http-pap
```

Con `http-pap`, RouterOS acepta:

```
http://192.168.77.254/login?username=QR-XXXXXX&password=YYYYYYYY
```

y autentica la sesión directamente (probado en este laboratorio con
`login-by=http-pap`, `HTTP/1.1 200 OK` y la sesión visible en
`/ip hotspot active`).

> **Seguridad:** la contraseña viaja en la URL y en el QR en texto plano. Es
> aceptable para tickets de un laboratorio/evento, pero no para producción
> expuesta a Internet. Ver §8.

---

## 2. Requisitos

### En el CHR

1. Servicio API habilitado (ya lo está en el laboratorio):
   ```routeros
   /ip service print
   # api  8728  tcp
   ```
2. Puerto **8728** reenviado por QEMU a `127.0.0.1` (ya está en
   `iniciar-lab.sh`):
   ```
   hostfwd=tcp:127.0.0.1:8728-:8728
   ```
3. Perfil de hotspot con `http-pap` y un perfil de usuario para tickets. El
   comando `setup` del script lo deja listo de forma idempotente.

> Si el CHR ya estaba arrancado antes de actualizar `iniciar-lab.sh`, hay que
> reiniciarlo una vez para que QEMU abra el puerto 8728. Comprueba con:
> `ss -tlnp | grep 8728`.

### En la laptop

```bash
cd ~/Documentos/MICRO-TIK
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Dependencias: `routeros-api`, `segno` (QR) y `Pillow` (tarjetas PNG).

---

## 3. Configuración

Copia el ejemplo y ajusta si hace falta:

```bash
cp .env.example .env
```

`.env` **no se versiona** (está en `.gitignore`). Valores por defecto del
laboratorio:

| Variable | Valor | Para qué |
|---|---|---|
| `MIKROTIK_HOST` | `127.0.0.1` | API del CHR (hostfwd de QEMU) |
| `MIKROTIK_PORT` | `8728` | Puerto API |
| `MIKROTIK_USER` | `admin` | Usuario RouterOS |
| `MIKROTIK_PASSWORD` | `Dahua2026` | Clave RouterOS |
| `MIKROTIK_SSID` | `MIKROTIK-LAB` | SSID que se pone en el QR WiFi |
| `MIKROTIK_WIFI_PASSWORD` | `mikrotik123` | Clave WPA2 del AP |
| `MIKROTIK_PORTAL` | *(vacío)* | Se detecta de `/ip hotspot/profile` |
| `MIKROTIK_PROFILE` | `qr-ticket` | Perfil de usuario de los tickets |
| `MIKROTIK_PREFIX` | `QR` | Prefijo de los códigos |
| `MIKROTIK_RATE_LIMIT` | *(vacío)* | Ej. `5M/5M`; vacío = sin límite |
| `MIKROTIK_TICKETS_DIR` | `tickets` | Carpeta de salida |

También se puede pasar todo por CLI (`--host`, `--api-password`, `--ssid`,
`--portal`, etc.) o por variables de entorno.

> El SSID y la clave WiFi los pone **hostapd** en la laptop, no RouterOS. El
> script solo los usa para construir el QR `WIFI:`. Si cambias
> `/etc/hostapd/mikrotik-lab.conf`, actualiza también `.env`.

---

## 4. Uso

### 4.1 Preparar el hotspot (una vez)

```bash
./scripts/ticket-qr setup
```

Salida esperada:

```
RouterOS   : MICRO-DEV-ROOT (7.24.5 (stable))
API        : 127.0.0.1:8728  OK
Hotspot    : hotspot1 (interfaz ether2, perfil hsprof1)
Perfil     : qr-ticket (creado)  shared-users=1 idle-timeout=10m
login-by   : http-pap añadido a hsprof1  (login por URL habilitado)
Portal     : http://192.168.77.254/login
```

`setup --forzar` actualiza un perfil `qr-ticket` que ya exista (por ejemplo,
para aplicar `MIKROTIK_RATE_LIMIT`).

### 4.2 Crear tickets

```bash
# 10 tickets de 1 hora, lote con nombre del evento
./scripts/ticket-qr crear -n 10 -t 1h --lote evento-octubre --nota "Taller de redes"

# Un ticket de 30 minutos con tope de tráfico
./scripts/ticket-qr crear -t 30m --limite-bytes 500M
```

Duración (`-t`): `30m`, `1h`, `1h30m`, `1d`, etc. Es **tiempo de conexión**
(`limit-uptime` de RouterOS), no tiempo de calendario. Si el usuario se
desconecta, deja de consumirse.

Salida:

```
  [  1/10] QR-XFYK25  clave UJB7Y3SH  ->  _ticket.png
  ...
Listo: 10 ticket(s) creados.
Abre la página imprimible: .../tickets/evento-octubre/tickets.html
Datos del lote          : .../tickets/evento-octubre/tickets.csv
```

### 4.3 Ver y administrar

```bash
./scripts/ticket-qr listar          # solo tickets QR
./scripts/ticket-qr listar --todas  # incluye admin, Armindev, Daniel...
./scripts/ticket-qr activos         # sesiones hotspot con IP/MAC/consumo
./scripts/ticket-qr estado          # salud del hotspot y de la API
./scripts/ticket-qr eliminar --lote evento-octubre
./scripts/ticket-qr eliminar --nombre QR-XFYK25
./scripts/ticket-qr eliminar --todos          # pide confirmación
```

Al eliminar un ticket también se cierran sus sesiones activas y se borran sus
cookies, para que el usuario no siga conectado.

### 4.4 QR para un usuario que ya existe

Útil para `Armindev`, `Daniel`, `admin` o cualquier usuario creado en WinBox.
No crea ni modifica nada en el router; solo genera los QR con la clave que le
indiques.

```bash
./scripts/ticket-qr qr --usuario Armindev --password armin2DEV
```

Si omites `--password`, la pide por teclado (no queda en el historial de bash).
Con `--no-verificar` se puede generar para usuarios RADIUS/externos.

### 4.5 Menú interactivo

```bash
./scripts/ticket-qr
# o
./scripts/ticket-qr menu
```

Opciones: estado, crear, listar, activos, eliminar, QR de usuario existente y
`setup`.

---

## 5. Archivos generados

Por cada lote, en `tickets/<lote>/`:

| Archivo | Contenido |
|---|---|
| `<codigo>_ticket.png` | Tarjeta 1000×650 con los dos QR, usuario, clave, vigencia y lote |
| `<codigo>_wifi.png` | Solo el QR `WIFI:T:WPA;S:MIKROTIK-LAB;P:...` |
| `<codigo>_login.png` | Solo el QR de login (`/login?username=...&password=...`) |
| `<codigo>.txt` | Credenciales e instrucciones en texto |
| `tickets.csv` | Lote completo (UTF-8 con BOM, abre en Excel/LibreOffice) |
| `tickets.html` | Página imprimible con todas las tarjetas (A4, una por página) |
| `resumen.txt` | Datos del lote y del portal |

`tickets/` está en `.gitignore` porque contiene credenciales en claro.

### Flujo para el usuario final

1. Escanea el **QR 1** (WiFi): el móvil propone unirse a `MIKROTIK-LAB`.
   Acepta (en Android/iOS suele pedir confirmación).
2. Escanea el **QR 2** (acceso): se abre el navegador en
   `http://192.168.77.254/login?...` y RouterOS autentica la sesión.
3. Listo: ya navega. Si el móvil muestra el aviso de "red sin Internet",
   elige "Seguir conectado" y escanea el QR 2.

> En iPhone, el QR WiFi abre una tarjeta para unirse a la red; tras aceptar,
> vuelve a la cámara y escanea el segundo QR. En Android, Google Lens/la cámara
> hacen lo mismo.

---

## 6. Qué hace exactamente en RouterOS

`crear` ejecuta, por cada ticket, el equivalente a:

```routeros
/ip hotspot user add \
    name="QR-XFYK25" \
    password="UJB7Y3SH" \
    profile="qr-ticket" \
    limit-uptime="30m" \
    comment="QR|prueba-qr|2026-10-23 14:44|30m|prueba automatizada"
```

Y el perfil se crea así (una vez):

```routeros
/ip hotspot user profile add \
    name="qr-ticket" \
    shared-users=1 \
    idle-timeout=10m \
    keepalive-timeout=2m \
    add-mac-cookie=yes \
    session-timeout=0s
```

- `shared-users=1`: un dispositivo por ticket.
- `idle-timeout=10m`: cierra sesiones inactivas (no consume cuota).
- `limit-uptime`: tiempo total de conexión del ticket.
- `add-mac-cookie=yes`: reconexión cómoda del mismo equipo.
- `session-timeout=0s`: sin corte forzado adicional; manda `limit-uptime`.

Puedes verlo en WinBox en **IP → Hotspot → Users** y **User Profiles**, o por
SSH:

```bash
sshpass -p 'Dahua2026' ssh -p 2222 admin@127.0.0.1 \
  '/ip hotspot user print; /ip hotspot user profile print; /ip hotspot active print'
```

---

## 7. Verificación realizada en este laboratorio

| Prueba | Resultado |
|---|---|
| API `127.0.0.1:8728` desde la laptop | OK (`RouterOS 7.24.5`) |
| `setup` con `http-pap` | `login-by=cookie,http-chap,http-pap` |
| `crear -n 2 -t 30m` | 2 usuarios creados en `/ip hotspot/user` |
| QR WiFi decodificado | `WIFI:T:WPA;S:MIKROTIK-LAB;P:mikrotik123;;` |
| QR login decodificado | `http://192.168.77.254/login?username=QR-...&password=...` |
| Abrir la URL del QR desde un cliente | `HTTP/1.1 200 OK` y sesión `http-pap` activa |
| `activos` | mostró IP, MAC, uptime y tipo `QR` |
| `eliminar --lote` | borró usuarios, sesiones y cookies |
| `qr --usuario Armindev` | generó tarjeta con `armin2DEV` sin tocar el router |

---

## 8. Seguridad y límites

1. **La URL del QR lleva la clave en claro.** Cualquiera que vea el ticket puede
   usarlo hasta que se agote o se elimine. Trata los PNG/CSV como credenciales.
2. **HTTP, no HTTPS.** El portal del laboratorio es HTTP; no hay certificado
   válido para `192.168.77.254`. No expongas este hotspot a Internet.
3. **`http-pap` acepta contraseñas en claro.** Es lo que permite el login por
   URL. En producción, valora HTTPS + un portal propio, o tickets de un solo uso
   con RADIUS/User Manager.
4. **La API queda en `127.0.0.1:8728`**, no en la red WiFi. No publiques el
   puerto 8728 hacia fuera.
5. **Cambia las claves por defecto** (`Dahua2026`, `mikrotik123`) si el
   laboratorio deja de ser local.
6. El CHR sin licencia limita a **1 Mbps**; el `rate-limit` del perfil no
   supera ese techo.

---

## 9. Problemas frecuentes

| Síntoma | Causa / solución |
|---|---|
| `Connection refused` en 8728 | El CHR se arrancó antes de añadir el hostfwd. Reinicia el laboratorio o comprueba `ss -tlnp \| grep 8728`. |
| `No se pudo conectar a la API` | Laboratorio apagado, puerto no reenviado o usuario/clave incorrectos en `.env`. |
| El QR de login abre el portal pero no entra | Falta `http-pap` en el perfil. Ejecuta `setup` y comprueba `login-by`. |
| El QR WiFi no conecta | El SSID/clave de `.env` no coinciden con `/etc/hostapd/mikrotik-lab.conf`. |
| El móvil dice "sin Internet" tras el QR | Es el aviso normal de portal cautivo; elige "Seguir conectado" y escanea el QR 2. |
| El ticket dice "agotado" | Se consumió `limit-uptime`; crea otro o sube la duración. |
| `Faltan dependencias` | `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`. |
| El usuario no aparece en `activos` | Debe escanear el QR 2 **después** de estar conectado a la WiFi. |

---

## 10. Cambiar SSID, clave o portal

1. Edita `/etc/hostapd/mikrotik-lab.conf` (SSID/clave) y reinicia el AP:
   ```bash
   sudo pkill -x hostapd
   sudo hostapd -B /etc/hostapd/mikrotik-lab.conf
   ```
2. Actualiza `MIKROTIK_SSID` y `MIKROTIK_WIFI_PASSWORD` en `.env`.
3. Si cambia la IP del portal, actualiza `MIKROTIK_PORTAL` o deja que el script
   la detecte con `/ip hotspot profile`.

---

## 11. Comandos de referencia rápida

```bash
cd ~/Documentos/MICRO-TIK

# Preparación
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./scripts/ticket-qr setup

# Operación
./scripts/ticket-qr crear -n 10 -t 1h --lote evento
./scripts/ticket-qr listar
./scripts/ticket-qr activos
./scripts/ticket-qr estado
./scripts/ticket-qr eliminar --lote evento

# Usuario existente
./scripts/ticket-qr qr --usuario Armindev --password armin2DEV

# Menú
./scripts/ticket-qr
```
