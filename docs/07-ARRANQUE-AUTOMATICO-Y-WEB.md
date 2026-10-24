# 07 — Arranque automático y panel web de administración

**Objetivo:** dejar todo el laboratorio en marcha con **un solo comando** (y
automáticamente al iniciar sesión), incluyendo el **panel web en Python** que
administra los tickets QR a través de la API de RouterOS.

> Documentos relacionados:
> [`05-INFORME-VERIFICACION-HOTSPOT.md`](./05-INFORME-VERIFICACION-HOTSPOT.md)
> (pruebas punta a punta) y [`06-TICKETS-QR.md`](./06-TICKETS-QR.md)
> (generador de tickets y API).

---

## 1. Qué se levanta y en qué orden

```
        Internet
           │
   wlp0s20f0u1  ← uplink (USB, perfil HIKVISION-USB, métrica 100)
           │
   ┌───────┴─────────────────────────────────────────────┐
   │  laptop Fedora                                      │
   │                                                     │
   │  wlp59s0 (radio interna, modo AP con hostapd)       │
   │      │  SSID: MIKROTIK-LAB  (WPA2)                  │
   │      ▼                                              │
   │  br-mikrotik  192.168.77.1/24   (STP desactivado)   │
   │      │                                              │
   │      ▼                                              │
   │  tap-mikrotik  ──► QEMU ──► CHR RouterOS 7.24.5     │
   │                              ether2 192.168.77.254  │
   │                              hotspot1 + DHCP + NAT  │
   │                              ether1 10.0.2.15       │
   │                                                     │
   │  web/app.py (Flask) ── API 127.0.0.1:8728 ──────────┘
   │      ▲                                              │
   │      └── http://127.0.0.1:5000                      │
   └─────────────────────────────────────────────────────┘
```

Orden correcto (importante):

1. **Uplink** con Internet por la USB.
2. **Liberar** la radio interna (`wlp59s0`) de NetworkManager.
3. **Bridge** `br-mikrotik` con STP off.
4. **Tap** `tap-mikrotik` creado **antes** de arrancar QEMU.
5. **hostapd** emitiendo `MIKROTIK-LAB`.
6. **QEMU** con reenvíos `2222`, `8291` y **`8728`**.
7. **Panel web** Flask, una vez que la API responde.

> Si el tap se crea **después** de arrancar QEMU, `ether2` queda *invalid* y el
> hotspot muestra el error de configuración de IP. Por eso el script crea el
> tap primero y nunca lo destruye si QEMU ya está corriendo.

---

## 2. Arranque en un comando

```bash
cd ~/Documentos/MICRO-TIK
./scripts/arrancar-todo.sh
```

Pide la contraseña de `sudo` (solo para red, bridge y hostapd), levanta lo que
falte y al final imprime:

```
SSID WiFi      : MIKROTIK-LAB  (clave: mikrotik123)
Portal         : http://192.168.77.254/login
Panel web      : http://127.0.0.1:5000
CHR SSH        : ssh -p 2222 admin@127.0.0.1
CHR WinBox     : 127.0.0.1:8291
CHR API        : 127.0.0.1:8728
```

El script es **idempotente**: si QEMU o el panel ya están corriendo, no los
duplica.

### Parar todo

```bash
./scripts/parar-lab.sh
```

Detiene QEMU, hostapd y el panel web, y devuelve `wlp59s0` a NetworkManager.

---

## 3. Scripts nuevos

| Script | Usuario | Qué hace |
|---|---|---|
| `scripts/preparar-red.sh` | root (`sudo`) | Comprueba Internet, libera la radio AP, prepara `br-mikrotik` + `tap-mikrotik`, arranca `hostapd`. No arranca QEMU ni la web. |
| `scripts/arrancar-todo.sh` | usuario normal | Llama al anterior con `sudo`, arranca QEMU con los tres `hostfwd`, arranca el panel Flask y verifica puertos. |
| `scripts/instalar-autostart.sh` | usuario normal | Instala/quita el arranque automático en `~/.config/autostart`. |

### 3.1 `preparar-red.sh`

```bash
sudo ./scripts/preparar-red.sh
```

Pasos:

1. Si no hay ruta por defecto, intenta conectar `UPLINK_IF`.
2. Si la ruta está en `AP_IF`, intenta moverla al uplink y aborta con mensaje
   claro si no es posible (nunca deja la laptop sin Internet).
3. `nmcli device disconnect wlp59s0` + `managed no`.
4. `ip link set br-mikrotik type bridge stp_state 0 forward_delay 0`.
5. Crea el tap solo si no existe (`persist on`, propietario el usuario real).
6. Reinicia `hostapd -B /etc/hostapd/mikrotik-lab.conf`.
7. Espera a que la interfaz pase a *forwarding* y comprueba `state=ENABLED`.

Variables opcionales: `AP_IF`, `UPLINK_IF`, `BR`, `TAP`, `AP_CONF`.

### 3.2 `arrancar-todo.sh`

```bash
./scripts/arrancar-todo.sh
```

- Llama a `preparar-red.sh` con `sudo`.
- Si QEMU no está, lo arranca con:

  ```
  hostfwd=tcp:127.0.0.1:2222-:22
  hostfwd=tcp:127.0.0.1:8291-:8291
  hostfwd=tcp:127.0.0.1:8728-:8728
  ```

- Espera a los puertos 2222 y 8728.
- Arranca `scripts/admin-web` si no está activo.
- Guarda logs en `logs/qemu.log` y `logs/admin-web.log`.
- Si no hay entorno gráfico, arranca QEMU con `-display none`.

Variables: `DISK`, `MEM`, `CPUS`, `WEB_HOST`, `WEB_PORT`.

---

## 4. Arranque automático al iniciar sesión

Instalación:

```bash
./scripts/instalar-autostart.sh
```

Crea `~/.config/autostart/mikrotik-lab.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=MikroTik Lab
Exec=/home/armintec/Documentos/MICRO-TIK/scripts/arrancar-todo.sh
Path=/home/armintec/Documentos/MICRO-TIK
Terminal=true
X-GNOME-Autostart-Delay=10
```

Al iniciar sesión se abre una terminal, se pide la contraseña de `sudo` y se
levanta todo. La espera de 10 s deja que NetworkManager conecte la WiFi.

### 4.1 Opcional: que no pida contraseña

Solo si aceptas el riesgo (el script con `NOPASSWD` es equivalente a root para
tu usuario y debe ser de confianza):

```bash
echo 'armintec ALL=(root) NOPASSWD: /home/armintec/Documentos/MICRO-TIK/scripts/preparar-red.sh' \
  | sudo tee /etc/sudoers.d/mikrotik-lab
sudo chmod 440 /etc/sudoers.d/mikrotik-lab
sudo visudo -c
```

Después cambia `Terminal=true` por `Terminal=false` en el `.desktop` (o vuelve
a ejecutar el instalador y edítalo).

### 4.2 Desinstalar

```bash
./scripts/instalar-autostart.sh --quitar
```

---

## 5. Panel web de administración (Python/Flask)

- Código: [`web/app.py`](../web/app.py)
- Lanzador: [`scripts/admin-web`](../scripts/admin-web)
- URL por defecto: **http://127.0.0.1:5000**
- Usuario por defecto: **`admin`**
- Contraseña por defecto: la de RouterOS (**`Dahua2026`**), salvo que definas
  `WEB_ADMIN_PASSWORD`.

El panel:

- Se autentica en la **API de RouterOS** (`127.0.0.1:8728`).
- Muestra estado del hotspot, tickets, activos, lotes y QR.
- Crea y elimina usuarios hotspot desde la web.
- Tiene un hilo de monitorización que refresca el estado.

### 5.1 Configuración (`.env`)

```bash
cp .env.example .env
```

Variables relevantes:

| Variable | Por defecto | Descripción |
|---|---|---|
| `WEB_ADMIN_USER` | `admin` | Usuario del panel |
| `WEB_ADMIN_PASSWORD` | igual a `MIKROTIK_PASSWORD` | Clave del panel |
| `WEB_SECRET_KEY` | se genera en `.web-secret` | Firma de sesiones |
| `WEB_HOST` | `127.0.0.1` | Interfaz de escucha |
| `WEB_PORT` | `5000` | Puerto |
| `MIKROTIK_HOST` / `PORT` | `127.0.0.1` / `8728` | API del CHR |
| `MIKROTIK_USER` / `PASSWORD` | `admin` / `Dahua2026` | Credenciales RouterOS |
| `MIKROTIK_SSID` | `MIKROTIK-LAB` | SSID para los QR |
| `MIKROTIK_WIFI_PASSWORD` | `mikrotik123` | Clave WiFi para los QR |

> `.env` no se versiona (está en `.gitignore`).

### 5.2 Exponer el panel a la red local

Por defecto solo escucha en `localhost`. Para abrirlo a la LAN (por ejemplo,
para administrar desde el móvil):

```bash
WEB_HOST=0.0.0.0 WEB_PORT=5000 ./scripts/arrancar-todo.sh
```

Luego entra desde otro equipo a `http://IP_DE_LA_LAPTOP:5000`.

**Importante:**

- Cambia `WEB_ADMIN_PASSWORD` antes de exponerlo.
- Abre el puerto solo en la red de confianza:
  ```bash
  sudo firewall-cmd --add-port=5000/tcp --permanent
  sudo firewall-cmd --reload
  ```
- Flask trae un servidor de desarrollo; para producción usa `gunicorn` o
  `waitress`, no `app.run()`.

### 5.3 Arrancar solo el panel

```bash
./scripts/admin-web
# o en segundo plano:
nohup ./scripts/admin-web >> logs/admin-web.log 2>&1 &
```

---

## 6. Verificación rápida (checklist)

```bash
# 1. Uplink e Internet
ip route show default                 # debe salir wlp0s20f0u1
ping -c 2 1.1.1.1

# 2. AP y bridge
sudo hostapd_cli -i wlp59s0 status | grep -E 'state|ssid|channel'
bridge link show                      # wlp59s0 y tap-mikrotik en forwarding

# 3. CHR + API
ss -tlnp | grep -E ':(2222|8291|8728)\b'
ssh -p 2222 admin@127.0.0.1 '/interface print; /ip hotspot print'

# 4. Panel web
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5000/login   # 200
tail -5 logs/admin-web.log

# 5. Hotspot (desde un móvil)
#    SSID MIKROTIK-LAB / mikrotik123 → portal → usuario de hotspot
```

En el panel web, el endpoint `GET /api/estado` debe devolver
`"ok": true` e `"identity": "MICRO-DEV-ROOT"`.

---

## 7. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `Connection refused` en `127.0.0.1:8728` | QEMU arrancado con un comando antiguo sin `hostfwd` del 8728 | `./scripts/parar-lab.sh` y `./scripts/arrancar-todo.sh` |
| **“Error de configuración de IP”** en el panel / `hotspot1` *invalid* / solo existe `ether1` | QEMU arrancó antes de crear el tap, o el tap se recreó con QEMU vivo | Parar QEMU, crear/reutilizar el tap y volver a arrancar con `arrancar-todo.sh` |
| `hostapd` queda en `COUNTRY_UPDATE` unos segundos | Reconfiguración del dominio regulatorio al arrancar | Esperar 5–10 s; el script espera a `ENABLED` |
| No aparece `MIKROTIK-LAB` | `hostapd` no corriendo o radio ocupada por NetworkManager | `sudo hostapd_cli -i wlp59s0 status`; `preparar-red.sh` la libera |
| La ruta por defecto está en `wlp59s0` | La radio AP tiene el uplink | Conectar `wlp0s20f0u1`; el script intenta moverla |
| El panel no arranca | Falta `.venv` o dependencias | `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` |
| El autostart pide contraseña | Es el comportamiento por defecto (`Terminal=true`) | Ver §4.1 para `NOPASSWD` opcional |
| Puerto 5000 ocupado | Otro proceso o instancia previa | `WEB_PORT=5001 ./scripts/arrancar-todo.sh` |
| `ping 192.168.77.254` da “red prohibida” | El host es un cliente no autenticado del hotspot | Es correcto; usar el portal o un cliente autenticado |

---

## 8. Archivos y logs

| Ruta | Contenido |
|---|---|
| `logs/qemu.log` | Salida de QEMU |
| `logs/admin-web.log` | Salida de Flask |
| `~/.config/autostart/mikrotik-lab.desktop` | Arranque automático |
| `/etc/hostapd/mikrotik-lab.conf` | Configuración del AP |
| `.env` | Configuración web/API (no versionado) |
| `.web-secret` | Clave de sesiones Flask (no versionada) |

---

## 9. Valores de este equipo (2026-10-24)

| Elemento | Valor |
|---|---|
| Radio AP | `wlp59s0` (interna, `phy0`, soporta AP) |
| Radio uplink | `wlp0s20f0u1` (USB, `phy1`, no soporta AP) |
| Perfil uplink | `HIKVISION-USB` (clon de `HIKVISION_BLUETEL`, métrica 100) |
| Red del uplink | `192.168.9.0/24`, gateway `192.168.9.1` |
| Bridge | `br-mikrotik` — `192.168.77.1/24` — STP off |
| AP | `MIKROTIK-LAB`, canal 11, WPA2 `mikrotik123` |
| CHR | RouterOS 7.24.5, `MICRO-DEV-ROOT` |
| Hotspot | `hotspot1` en `ether2`, perfil `hsprof1` |
| Login del portal | `cookie,http-chap,http-pap` |
| Panel web | `http://127.0.0.1:5000` — usuario `admin` |

---

## 10. Arranque manual paso a paso (para depurar)

Si algo falla, este es el orden exacto:

```bash
# 1. Uplink
ip route show default

# 2. Red + AP (una sola vez)
sudo ./scripts/preparar-red.sh

# 3. CHR
qemu-system-x86_64 -enable-kvm -machine type=pc -cpu host -smp 2 -m 512 \
  -drive file=chr-disk.qcow2,format=qcow2 -boot c \
  -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:2222-:22,hostfwd=tcp:127.0.0.1:8291-:8291,hostfwd=tcp:127.0.0.1:8728-:8728 \
  -netdev tap,id=lan0,ifname=tap-mikrotik,script=no,downscript=no \
  -device virtio-net-pci,netdev=lan0 -display gtk &

# 4. Esperar y comprobar
ss -tlnp | grep 8728
ssh -p 2222 admin@127.0.0.1 '/interface print'

# 5. Panel web
./scripts/admin-web
```
