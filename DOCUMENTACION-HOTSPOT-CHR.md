# Laboratorio MikroTik CHR + Hotspot WiFi desde una laptop

**Documento completo de instalación, configuración y operación**

| Dato | Valor |
|---|---|
| Fecha | 2026-10-21 |
| RouterOS probado | 7.24.5 (CHR, x86_64) |
| Host probado | Fedora 44, kernel 7.2.9 |
| QEMU | 10.2.2 |
| hostapd | 2.11 |
| Directorio del laboratorio | `/home/armintec/Documentos/MICRO-TIK` |

---

## Índice

1. [Objetivo](#1-objetivo)
2. [Conceptos clave](#2-conceptos-clave)
3. [Arquitectura del laboratorio](#3-arquitectura-del-laboratorio)
4. [Requisitos](#4-requisitos)
5. [Valores del laboratorio](#5-valores-del-laboratorio)
6. [Fase 1 — Preparar el host](#6-fase-1--preparar-el-host)
7. [Fase 2 — Configurar el CHR desde cero](#7-fase-2--configurar-el-chr-desde-cero)
8. [Fase 3 — Crear el AP WiFi en la laptop](#8-fase-3--crear-el-ap-wifi-en-la-laptop)
9. [Fase 4 — Conectar el celular y autenticarse](#9-fase-4--conectar-el-celular-y-autenticarse)
10. [Verificación y diagnóstico](#10-verificación-y-diagnóstico)
11. [Solución de problemas](#11-solución-de-problemas)
12. [Persistencia: script de arranque](#12-persistencia-script-de-arranque)
13. [Seguridad y buenas prácticas](#13-seguridad-y-buenas-prácticas)
14. [Anexos](#14-anexos)

---

## 1. Objetivo

Montar un laboratorio real de **hotspot cautivo MikroTik** usando:

- Un **MikroTik CHR** (Cloud Hosted Router) corriendo como máquina virtual en QEMU/KVM.
- La **laptop como host** de la virtualización.
- Un **adaptador WiFi de la laptop en modo AP** para que teléfonos y otros equipos se conecten por WiFi.
- Un **segundo adaptador WiFi de la laptop** (o la conexión existente) como salida a Internet.

El resultado: el celular se conecta a una red WiFi emitida por la laptop, recibe IP del MikroTik, ve el portal cautivo y, tras autenticarse, navega a Internet a través del CHR.

---

## 2. Conceptos clave

### 2.1 El CHR no tiene WiFi

El **CHR (Cloud Hosted Router)** es una versión de RouterOS para máquinas virtuales. **No incluye driver wireless ni radio WiFi**. Sus interfaces son Ethernet virtuales:

- `ether1` → salida a Internet (NAT de QEMU).
- `ether2` → LAN del hotspot (conectada al `tap` del host).

Por eso, aunque RouterOS tenga el hotspot configurado, **no emite ningún SSID**. El SSID lo emite la laptop con `hostapd`.

### 2.2 Qué es el "hotspot" de RouterOS

El hotspot de RouterOS es un **portal cautivo** que funciona sobre una red IP normal. No es una tecnología WiFi. Hace lo siguiente:

1. Detecta clientes no autenticados en la interfaz configurada.
2. Redirige su tráfico HTTP/HTTPS/DNS al portal de login.
3. Valida usuario y contraseña.
4. Autoriza la MAC/IP del cliente y le permite salir a Internet.
5. Aplica límites de tiempo, velocidad y tráfico según el perfil.

### 2.3 La cadena completa

```
Celular
  │  WiFi (SSID MIKROTIK-LAB, WPA2)
  ▼
Adaptador QCA6174 de la laptop  ── modo AP (hostapd)
  │
  ▼
br-mikrotik  (bridge Linux, IP 192.168.77.1/24)
  │
  ▼
tap-mikrotik  (interfaz TAP de QEMU)
  │  Ethernet virtual
  ▼
ether2 del CHR  (192.168.77.254/24)
  │  Hotspot RouterOS (DHCP + portal + NAT)
  ▼
ether1 del CHR  (10.0.2.15/24, DHCP de QEMU)
  │
  ▼
NAT de QEMU (slirp) → adaptador USB MT7601U → WiFi TecRoot → Internet
```

---

## 3. Arquitectura del laboratorio

### 3.1 Interfaces del host (laptop)

| Interfaz | Tipo | Función | IP |
|---|---|---|---|
| `wlp0s20f0u1` | WiFi USB MT7601U | Cliente de TecRoot (salida a Internet) | DHCP `192.168.100.x` |
| `wlp59s0` | WiFi PCIe QCA6174 | AP del laboratorio (`MIKROTIK-LAB`) | sin IP (bridge) |
| `br-mikrotik` | Bridge Linux | Une el AP y el tap | `192.168.77.1/24` |
| `tap-mikrotik` | TAP de QEMU | Enlace L2 hacia el CHR | sin IP |
| `enp0s20f0u2c2` | Ethernet USB (si existe) | No usada en este montaje | — |

### 3.2 Interfaces y direcciones del CHR

| Interfaz | IP | Función |
|---|---|---|
| `ether1` | `10.0.2.15/24` (DHCP) | WAN, salida por NAT de QEMU |
| `ether2` | `192.168.77.254/24` | LAN del hotspot |
| `lo` | `127.0.0.1` | Loopback |

- Gateway de `ether1`: `10.0.2.2`
- DNS de QEMU: `10.0.2.3`
- Pool DHCP del hotspot: `192.168.77.100 – 192.168.77.199`

### 3.3 Puertos publicados por QEMU

| Host | CHR | Servicio |
|---|---|---|
| `127.0.0.1:2222` | `22` | SSH |
| `127.0.0.1:8291` | `8291` | WinBox |

> Los puertos están enlazados solo a `127.0.0.1`, así que **no** quedan expuestos a la red WiFi.

---

## 4. Requisitos

### 4.1 Hardware

- Laptop con virtualización por hardware (VT-x/AMD-V) habilitada.
- **Dos adaptadores WiFi**:
  - Uno para la salida a Internet (en el montaje actual, un USB MT7601U).
  - Otro que soporte **modo AP** (en el montaje actual, una QCA6174 PCIe).
- Al menos 2 GB de RAM libre (el CHR usa 512 MB).
- Espacio en disco para la imagen del CHR (~128 MB + crecimiento).

> Si solo tienes un adaptador WiFi, puedes intentar AP+STA simultáneo, pero muchos firmwares (incluido el de la QCA6174 de este laboratorio) fallan con `Operation already in progress`. La solución robusta es usar dos adaptadores.

### 4.2 Software en Fedora

```bash
sudo dnf install -y qemu-system-x86 qemu-img hostapd iw NetworkManager
```

Verificar:

```bash
qemu-system-x86_64 --version
hostapd -v
iw --version
```

### 4.3 Comprobar virtualización y permisos

```bash
ls -l /dev/kvm
ls -l /dev/net/tun
groups   # debe incluir kvm (y wheel para sudo)
```

Si `/dev/kvm` no existe, habilitar VT-x/AMD-V en la BIOS.

### 4.4 Imagen del CHR

En el directorio del laboratorio deben existir:

```text
chr-7.24.5.img      # imagen raw original
chr-7.24.5.img.zip  # respaldo comprimido
chr-disk.qcow2      # disco de trabajo (el que usa QEMU)
chr-lab.img         # otra imagen de laboratorio
```

Si necesitas recrear el disco de trabajo desde la imagen raw:

```bash
qemu-img convert -f raw -O qcow2 chr-7.24.5.img chr-disk.qcow2
```

> **Licencia CHR:** sin licencia, el CHR está limitado a 1 Mbps. Para un laboratorio de portal es suficiente. Para más velocidad, aplicar una licencia de MikroTik.

---

## 5. Valores del laboratorio

| Parámetro | Valor actual |
|---|---|
| Identidad del CHR | `MICRO-DEV-ROOT` |
| SSH del CHR | `ssh -p 2222 admin@127.0.0.1` |
| Contraseña SSH | la definida en el laboratorio (no se escribe aquí) |
| WinBox | `127.0.0.1:8291` |
| IP LAN del CHR | `192.168.77.254/24` |
| IP del bridge del host | `192.168.77.1/24` |
| Pool DHCP | `192.168.77.100 – 192.168.77.199` |
| SSID del AP | `MIKROTIK-LAB` |
| Clave WiFi | `mikrotik123` |
| Usuario hotspot | `cliente` |
| Clave hotspot | `cliente123` |
| Portal (recomendado) | `http://192.168.77.254/login` |
| Nombre DNS opcional | `wifi.dev` |

> Cambia todas las claves antes de usar esto fuera del laboratorio.

---

## 6. Fase 1 — Preparar el host

### 6.1 Crear el bridge `br-mikrotik`

Opción recomendada con NetworkManager:

```bash
sudo nmcli con add type bridge ifname br-mikrotik con-name br-mikrotik
sudo nmcli con mod br-mikrotik \
  ipv4.method manual \
  ipv4.addresses 192.168.77.1/24 \
  ipv6.method disabled \
  bridge.stp no
sudo nmcli con up br-mikrotik
```

Verificar:

```bash
ip -brief addr show br-mikrotik
```

Debe mostrar `UP` y `192.168.77.1/24`.

> **STP:** se desactiva (`bridge.stp no`) para que los puertos pasen a *forwarding* de inmediato. Si se deja activado, hay una espera de 15–30 segundos antes de que el celular pueda pasar tráfico.

Si el bridge ya existe y está activo, no lo vuelvas a crear.

### 6.2 Crear el tap de QEMU

```bash
sudo ip tuntap add dev tap-mikrotik mode tap user "$USER"
sudo ip link set tap-mikrotik up
sudo ip link set tap-mikrotik master br-mikrotik
```

Verificar:

```bash
ip link show tap-mikrotik
bridge link show
```

El tap debe aparecer como puerto del bridge. Si el puerto está en `listening` o `learning`, espera unos segundos (o desactiva STP como se indicó).

> Si `ip tuntap add` falla con `Operation not permitted`, falta `sudo` o el usuario no tiene permiso sobre `/dev/net/tun`.

### 6.3 (Opcional) Perfil de NetworkManager para el tap

NetworkManager puede recordar la relación tap → bridge:

```bash
sudo nmcli con add type ethernet ifname tap-mikrotik con-name tap-mikrotik master br-mikrotik
```

En la práctica, los dispositivos TAP no siempre son gestionados por NetworkManager; por eso los comandos `ip link` del paso 6.2 son la fuente de verdad. El perfil no estorba.

### 6.4 Arrancar QEMU

Desde el directorio del laboratorio:

```bash
qemu-system-x86_64 \
  -enable-kvm \
  -machine type=pc \
  -cpu host \
  -smp 2 \
  -m 512 \
  -drive file=chr-disk.qcow2,format=qcow2 \
  -boot c \
  -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:2222-:22,hostfwd=tcp:127.0.0.1:8291-:8291 \
  -netdev tap,id=lan0,ifname=tap-mikrotik,script=no,downscript=no \
  -device virtio-net-pci,netdev=lan0 \
  -display gtk
```

Explicación:

- `-nic user,...` → primera NIC (`ether1`) con NAT de QEMU y reenvío de puertos.
- `-netdev tap,...` → segunda NIC (`ether2`) conectada al tap del host.
- `script=no,downscript=no` → QEMU no intenta crear/configurar el tap; ya lo creamos nosotros.
- `-display gtk` → ventana de QEMU (puedes usar `-display none` si no la necesitas).

### 6.5 Comprobar el enlace hacia el CHR

```bash
ping -c 3 192.168.77.254
```

Mientras el cliente no esté autenticado, es normal recibir `Destination Net Prohibited` o perder ICMP: el hotspot bloquea clientes no autorizados. Lo importante es que el CHR responda (aunque sea con un ICMP de rechazo).

---

## 7. Fase 2 — Configurar el CHR desde cero

### 7.1 Acceso inicial

```bash
ssh -p 2222 admin@127.0.0.1
```

En un CHR recién instalado, `admin` no tiene contraseña. Cámbiala de inmediato:

```routeros
/user set admin password="TU_CLAVE_SEGURA"
```

### 7.2 Configuración base

```routeros
# Identidad
/system identity set name=MICRO-DEV-ROOT

# ether1: cliente DHCP hacia el NAT de QEMU
/ip dhcp-client add interface=ether1 name=client1 disabled=no

# ether2: LAN del hotspot
/ip address add address=192.168.77.254/24 interface=ether2 comment="LAN HOTSPOT"

# NAT de salida y NAT del hotspot
/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade comment="NAT salida"
/ip firewall nat add chain=srcnat src-address=192.168.77.0/24 action=masquerade comment="NAT hotspot"
```

Verificar que `ether1` tome IP:

```routeros
/ip address print
/ip route print
```

Debe aparecer `10.0.2.15/24` en `ether1` y la ruta por defecto `0.0.0.0/0` vía `10.0.2.2`.

### 7.3 Pool y servidor DHCP

```routeros
/ip pool add name=pool-lan ranges=192.168.77.100-192.168.77.199

/ip dhcp-server network add \
  address=192.168.77.0/24 \
  gateway=192.168.77.254 \
  dns-server=1.1.1.1,8.8.8.8

/ip dhcp-server add \
  name=dhcp-lan \
  interface=ether2 \
  address-pool=pool-lan \
  lease-time=1h \
  disabled=no
```

### 7.4 Perfil y servidor hotspot

```routeros
/ip hotspot profile add \
  name=hsprof1 \
  hotspot-address=192.168.77.254 \
  dns-name="" \
  html-directory=hotspot

/ip hotspot add \
  name=hotspot1 \
  interface=ether2 \
  address-pool=pool-lan \
  profile=hsprof1 \
  idle-timeout=5m \
  disabled=no
```

Puntos importantes:

- `hotspot-address=192.168.77.254` debe coincidir con la IP de `ether2`.
- **`dns-name=""` es intencional.** Si se pone `wifi.dev`, el formulario de login apunta a `http://wifi.dev/login`; los clientes que no resuelven ese nombre (por DNS privado en Android, por ejemplo) no pueden enviar el login. Con `dns-name=""`, todo usa la IP y funciona siempre.
- El hotspot crea automáticamente las reglas NAT dinámicas del portal (redirección de HTTP/HTTPS/DNS).

### 7.5 Usuarios del hotspot

```routeros
/ip hotspot user add \
  name=cliente \
  password=cliente123 \
  profile=default \
  comment="Usuario de prueba"

# Seguridad: eliminar el usuario admin sin contraseña si existe
:if ([:len [/ip hotspot user find name="admin"]] > 0) do={
  /ip hotspot user remove [find name="admin"]
}
```

Verificar:

```routeros
/ip hotspot print
/ip hotspot user print
/ip hotspot profile print
```

El perfil `hsprof1` debe mostrar `dns-name=""` y `proxy-status="running"` en el hotspot.

### 7.6 DNS: dos modos posibles

#### Modo A — Solo IP (recomendado)

- DHCP entrega `1.1.1.1` y `8.8.8.8`.
- El portal se usa en `http://192.168.77.254/login`.
- **No se usa `wifi.dev`.** Es el modo más confiable y el que está activo.

#### Modo B — Con nombre `wifi.dev`

Útil si quieres una URL bonita. Requiere que el cliente use el DNS del MikroTik:

```routeros
/ip dns set allow-remote-requests=yes servers=1.1.1.1,8.8.8.8
/ip dns static add name=wifi.dev address=192.168.77.254
/ip dhcp-server network set [find address=192.168.77.0/24] dns-server=192.168.77.254
```

Además, en el celular hay que **desactivar el DNS privado**:

- Android: Ajustes → Red e Internet → DNS privado → **Desactivado**.
- iPhone: no usa DoT por defecto, normalmente funciona.

> `wifi.dev` **no existe en Internet**. Es un nombre privado del laboratorio. `dig @1.1.1.1 wifi.dev` devuelve NXDOMAIN. Por eso no funciona si el cliente usa DNS públicos o DNS over TLS.
>
> Aunque actives el Modo B, **deja `dns-name=""`** en el perfil del hotspot para que el portal siga usando la IP.

### 7.7 Script RouterOS completo (`.rsc`)

Guarda esto como `hotspot-lab.rsc` y ejecútalo con `/import file-name=hotspot-lab.rsc` en un CHR limpio, o pégalo por bloques.

```routeros
# ============================================================
# Laboratorio Hotspot CHR
# RouterOS 7.24.5
# ============================================================

/system identity set name=MICRO-DEV-ROOT

# --- WAN: ether1 por DHCP de QEMU ---
/ip dhcp-client add interface=ether1 name=client1 disabled=no

# --- LAN del hotspot: ether2 ---
/ip address add address=192.168.77.254/24 interface=ether2 comment="LAN HOTSPOT"

# --- Pool y DHCP ---
/ip pool add name=pool-lan ranges=192.168.77.100-192.168.77.199

/ip dhcp-server network add \
  address=192.168.77.0/24 \
  gateway=192.168.77.254 \
  dns-server=1.1.1.1,8.8.8.8

/ip dhcp-server add \
  name=dhcp-lan \
  interface=ether2 \
  address-pool=pool-lan \
  lease-time=1h \
  disabled=no

# --- NAT ---
/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade comment="NAT salida"
/ip firewall nat add chain=srcnat src-address=192.168.77.0/24 action=masquerade comment="NAT hotspot"

# --- Hotspot ---
/ip hotspot profile add \
  name=hsprof1 \
  hotspot-address=192.168.77.254 \
  dns-name="" \
  html-directory=hotspot

/ip hotspot add \
  name=hotspot1 \
  interface=ether2 \
  address-pool=pool-lan \
  profile=hsprof1 \
  idle-timeout=5m \
  disabled=no

# --- Usuario de prueba ---
/ip hotspot user add \
  name=cliente \
  password=cliente123 \
  profile=default \
  comment="Usuario de prueba"

# --- Quitar admin de hotspot sin clave (si existe) ---
:if ([:len [/ip hotspot user find name="admin"]] > 0) do={
  /ip hotspot user remove [find name="admin"]
}

# --- Opcional: DNS con nombre wifi.dev (ver Modo B) ---
# /ip dns set allow-remote-requests=yes servers=1.1.1.1,8.8.8.8
# /ip dns static add name=wifi.dev address=192.168.77.254
# /ip dhcp-server network set [find address=192.168.77.0/24] dns-server=192.168.77.254
```

---

## 8. Fase 3 — Crear el AP WiFi en la laptop

### 8.1 Identificar los adaptadores

```bash
iw dev
nmcli -f DEVICE,TYPE,STATE,CONNECTION device status
```

En este laboratorio:

| Interfaz | Chip | Función asignada |
|---|---|---|
| `wlp59s0` | Qualcomm QCA6174 (PCIe) | **AP** del laboratorio |
| `wlp0s20f0u1` | Ralink MT7601U (USB) | **Cliente** de TecRoot |

Comprobar que la interfaz del AP soporta modo AP:

```bash
iw phy phy0 info | sed -n '/Supported interface modes/,/Band/p'
```

Debe incluir `* AP`. El MT7601U solo soporta `managed` y `monitor`, por eso no puede ser AP.

### 8.2 Conectar el adaptador USB a TecRoot

Si ya existe el perfil `TecRoot`, puedes reutilizar su clave:

```bash
PSK=$(sudo nmcli -s -g 802-11-wireless-security.psk con show TecRoot)
sudo nmcli con add type wifi ifname wlp0s20f0u1 con-name TecRoot-USB ssid TecRoot
sudo nmcli con modify TecRoot-USB wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PSK"
sudo nmcli con up TecRoot-USB
```

Alternativa interactiva:

```bash
sudo nmcli device wifi connect TecRoot password 'CLAVE_DE_TECROOT' ifname wlp0s20f0u1 name TecRoot-USB
```

Verificar:

```bash
nmcli -f DEVICE,STATE,CONNECTION device status
iw dev wlp0s20f0u1 link
ip route | grep default
```

La ruta por defecto debe salir por `wlp0s20f0u1` y el enlace debe tener señal aceptable (mejor que −70 dBm).

> Este paso es crítico: al liberar la QCA para el AP, la laptop pierde su conexión WiFi original. Internet debe seguir por el USB.

### 8.3 Liberar la QCA para el AP

```bash
sudo nmcli device disconnect wlp59s0
sudo nmcli device set wlp59s0 managed no
```

Verificar que `wlp59s0` quede sin conexión y sin IP:

```bash
nmcli -f DEVICE,STATE,CONNECTION device status
ip -brief addr show wlp59s0
```

### 8.4 Configurar hostapd

Crear `/etc/hostapd/mikrotik-lab.conf`:

```bash
sudo tee /etc/hostapd/mikrotik-lab.conf >/dev/null <<'EOF'
interface=wlp59s0
bridge=br-mikrotik
driver=nl80211
ssid=MIKROTIK-LAB
hw_mode=g
channel=11
ieee80211n=1
wmm_enabled=1
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=mikrotik123
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
ctrl_interface=/var/run/hostapd
ctrl_interface_group=0
EOF

sudo chmod 600 /etc/hostapd/mikrotik-lab.conf
```

Parámetros:

- `bridge=br-mikrotik` → hostapd mete la interfaz AP en el bridge automáticamente.
- `hw_mode=g` + `channel=11` → 2.4 GHz, canal 11. Se eligió para no solaparse con TecRoot (canal 4).
- `wpa=2` + `WPA-PSK` + `CCMP` → WPA2 seguro.
- `ieee80211n=1` → habilita 802.11n.

> Si TecRoot cambia de canal, elige 1, 6 u 11 que no se solape con él. Puedes ver el canal actual con `iw dev wlp0s20f0u1 link`.

### 8.5 Arrancar hostapd

```bash
sudo hostapd -B /etc/hostapd/mikrotik-lab.conf
```

Verificar:

```bash
pgrep -a hostapd
iw dev wlp59s0 info
bridge link show
```

Debe mostrar:

- `ssid MIKROTIK-LAB`
- `type AP`
- `channel 11 (2462 MHz)`
- `wlp59s0` en el bridge, estado `forwarding` (puede tardar unos segundos).

Para ver clientes conectados:

```bash
sudo hostapd_cli all_sta
```

### 8.6 Detener el AP y restaurar la laptop

```bash
sudo pkill hostapd
sudo nmcli device set wlp59s0 managed yes
sudo nmcli con up TecRoot
```

---

## 9. Fase 4 — Conectar el celular y autenticarse

1. En el celular, buscar la red WiFi **`MIKROTIK-LAB`**.
2. Conectar con la clave **`mikrotik123`**.
3. El celular recibe una IP del rango `192.168.77.100–199` por DHCP.
4. Debe aparecer el portal cautivo. Si no aparece, abrir el navegador en:
   - **`http://192.168.77.254/login`**
5. Ingresar:
   - Usuario: **`cliente`**
   - Contraseña: **`cliente123`**
6. Pulsar **Connect**. Debe redirigir a `http://192.168.77.254/status` y permitir la navegación.

> Si el celular muestra "sin Internet" o "red no disponible" antes del login, es normal: el hotspot bloquea todo hasta autenticarse. El portal debe aparecer igualmente.

---

## 10. Verificación y diagnóstico

### 10.1 En el host (laptop)

```bash
# Estado de adaptadores
nmcli -f DEVICE,TYPE,STATE,CONNECTION device status

# AP encendido
iw dev wlp59s0 info

# Clientes WiFi asociados
sudo hostapd_cli all_sta

# Bridge y tap
ip -brief addr show br-mikrotik
ip link show tap-mikrotik
bridge link show

# Ruta a Internet
ip route | grep default
ping -c 3 1.1.1.1

# Llegada al CHR
ping -c 3 192.168.77.254
```

### 10.2 En el CHR

```routeros
# Estado general
/system resource print
/interface print
/ip address print
/ip route print

# Clientes DHCP
/ip dhcp-server lease print

# Clientes vistos por el hotspot
/ip hotspot host print

# Sesiones autenticadas
/ip hotspot active print detail
/ip hotspot active print stats

# Usuarios y perfiles
/ip hotspot user print
/ip hotspot profile print

# Reglas NAT dinámicas del hotspot
/ip firewall nat print

# Logs del hotspot
/log print where topics~"hotspot"
```

### 10.3 Prueba de Internet desde el CHR

```routeros
/ping 1.1.1.1 count=3
/tool fetch url="http://neverssl.com" mode=http dst-path=test.html
/file print where name=test.html
/file remove [find name="test.html"]
```

### 10.4 Prueba del portal desde la laptop

```bash
# La página de login debe responder 200
curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://192.168.77.254/login

# El formulario debe apuntar a la IP, no a wifi.dev
curl -sS http://192.168.77.254/login | grep -E 'form name="(sendin|login)"'
```

La acción debe ser:

```html
<form name="sendin" action="http://192.168.77.254/login" ...>
<form name="login" action="http://192.168.77.254/login" ...>
```

Si aparece `wifi.dev`, el perfil del hotspot todavía tiene `dns-name` configurado. Corregir con:

```routeros
/ip hotspot profile set hsprof1 dns-name=""
```

---

## 11. Solución de problemas

### 11.1 El celular no ve el SSID

| Causa probable | Verificación | Solución |
|---|---|---|
| hostapd no está corriendo | `pgrep -a hostapd` | `sudo hostapd -B /etc/hostapd/mikrotik-lab.conf` |
| Interfaz ocupada por NetworkManager | `nmcli device status` | `sudo nmcli device disconnect wlp59s0; sudo nmcli device set wlp59s0 managed no` |
| Canal no permitido | `iw reg get` | Usar canal 1, 6 u 11 |
| Adaptador no soporta AP | `iw phy phyX info` | Usar otro adaptador |
| hostapd falla al iniciar | `sudo hostapd -dd /etc/hostapd/mikrotik-lab.conf` | Leer el error concreto |

### 11.2 `hostapd: Could not configure driver mode ... Operation already in progress`

Significa que el driver no soporta **AP + STA simultáneos** en la misma radio. Ocurrió con la QCA6174.

Solución aplicada:

1. Conectar el **segundo adaptador** (MT7601U USB) a TecRoot como cliente.
2. Desconectar la QCA de TecRoot y ponerla en modo AP.

Si solo tienes un adaptador, alternativas:

- Usar el mismo canal que la conexión STA (algunos drivers lo permiten).
- Usar un AP externo conectado por Ethernet.
- Usar un router MikroTik físico con wireless.

### 11.3 El celular se conecta pero no recibe IP

| Causa probable | Verificación | Solución |
|---|---|---|
| `tap-mikrotik` está DOWN | `ip link show tap-mikrotik` | `sudo ip link set tap-mikrotik up` |
| Tap no está en el bridge | `bridge link show` | `sudo ip link set tap-mikrotik master br-mikrotik` |
| Puerto en `listening`/`learning` | `bridge link show` | Esperar o desactivar STP: `sudo nmcli con mod br-mikrotik bridge.stp no; sudo nmcli con up br-mikrotik` |
| DHCP del CHR no corre | `/ip dhcp-server print` | Habilitarlo y revisar el pool |
| Pool agotado | `/ip pool print` | Ampliar el rango |

### 11.4 El portal no carga

- Usar **`http://192.168.77.254/login`** (sin nombre DNS).
- Verificar que el hotspot esté corriendo: `/ip hotspot print` → `proxy-status="running"`.
- Probar desde el host: `curl -I http://192.168.77.254/login` → debe dar `200` o `302`.

### 11.5 `wifi.dev` no carga

Explicación completa:

1. `wifi.dev` **no existe en Internet**. Es un nombre privado del hotspot.
2. Los DNS públicos (`1.1.1.1`, `8.8.8.8`) devuelven NXDOMAIN.
3. Android con **DNS privado (DoT)** consulta directo a `8.8.8.8:853` y se salta el DNS del hotspot.
4. Si el formulario de login apunta a `wifi.dev`, el POST nunca llega y el login "no hace nada".

Soluciones:

- **Recomendada:** usar la IP `http://192.168.77.254/login` y dejar `dns-name=""`.
- **Alternativa:** configurar el Modo B (DNS del MikroTik + entrada estática) y desactivar el DNS privado en el celular.
- En la laptop, `/etc/hosts` puede forzar el nombre:
  ```bash
  echo '192.168.77.254  wifi.dev' | sudo tee -a /etc/hosts
  ```
  Pero eso **solo afecta a la laptop**, no al celular.

### 11.6 El login no inicia sesión / "no se puede acceder a este sitio"

Síntoma: se ingresan las credenciales y el navegador muestra un error de sitio inaccesible.

Causa: la página se cargó por IP, pero el formulario enviaba a `wifi.dev`, que no resuelve.

Solución:

```routeros
/ip hotspot profile set hsprof1 dns-name=""
```

Luego recargar `http://192.168.77.254/login` y volver a intentar.

Verificar que el login sí ocurrió:

```routeros
/ip hotspot active print
```

Debe aparecer el usuario con la MAC y la IP del celular.

### 11.7 El celular se autentica pero no navega

| Causa probable | Verificación | Solución |
|---|---|---|
| El CHR no tiene Internet | `/ping 1.1.1.1 count=3` | Revisar `ether1`, DHCP de QEMU y NAT |
| Falta NAT de salida | `/ip firewall nat print` | Agregar `masquerade out-interface=ether1` |
| El host no tiene Internet | `ping -c 3 1.1.1.1` en la laptop | Revisar `TecRoot-USB` y la ruta por defecto |
| El USB perdió la conexión | `iw dev wlp0s20f0u1 link` | `sudo nmcli con up TecRoot-USB` |
| DNS del cliente | Probar `ping 1.1.1.1` y `ping google.com` | Revisar DNS del DHCP |

### 11.8 La laptop se quedó sin Internet al liberar la QCA

Es lo esperado: la QCA era la conexión original. Verificar:

```bash
nmcli -f DEVICE,STATE,CONNECTION device status
iw dev wlp0s20f0u1 link
ip route | grep default
```

Si el USB no está conectado:

```bash
sudo nmcli con up TecRoot-USB
```

Si necesitas recuperar la conexión original:

```bash
sudo pkill hostapd
sudo nmcli device set wlp59s0 managed yes
sudo nmcli con up TecRoot
```

### 11.9 `tap-mikrotik: Operation not permitted` / `could not configure /dev/net/tun`

- Crear el tap con `sudo` y con `user "$USER"`.
- Verificar `/dev/net/tun` y que el usuario tenga permiso.
- No dejar que QEMU cree el tap (`script=no,downscript=no`).

### 11.10 El host no debe enrutar su tráfico por `192.168.77.254`

No agregues una ruta por defecto en la laptop hacia el CHR. El CHR usa el NAT de QEMU (slirp), cuyo tráfico sale por el host. Si el host enruta ese tráfico de vuelta al CHR, se produce un **bucle**:

```
CHR → slirp → host → (ruta por defecto al CHR) → CHR → ...
```

El host debe seguir usando el USB (`TecRoot-USB`) como ruta por defecto. Solo los clientes externos (el celular) deben salir por el hotspot.

---

## 12. Persistencia: script de arranque

Crea `iniciar-lab.sh` en el directorio del laboratorio:

```bash
#!/usr/bin/env bash
# ============================================================
# iniciar-lab.sh
# Levanta el laboratorio MikroTik CHR + hotspot WiFi.
# Uso: ./iniciar-lab.sh
# ============================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISK="$BASE_DIR/chr-disk.qcow2"
TAP="tap-mikrotik"
BR="br-mikrotik"
AP_IF="wlp59s0"
STA_IF="wlp0s20f0u1"
AP_CONF="/etc/hostapd/mikrotik-lab.conf"
STA_CON="TecRoot-USB"

log() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "$DISK" ]]    || die "No existe $DISK"
[[ -f "$AP_CONF" ]] || die "No existe $AP_CONF (crear según la documentación)"

log "Pidiendo privilegios"
sudo -v

log "Preparando bridge $BR"
if ! nmcli -t -f NAME connection show | grep -qx "$BR"; then
  sudo nmcli connection add type bridge ifname "$BR" con-name "$BR"
  sudo nmcli connection modify "$BR" \
    ipv4.method manual \
    ipv4.addresses 192.168.77.1/24 \
    ipv6.method disabled \
    bridge.stp no
  sudo nmcli connection up "$BR"
else
  sudo nmcli connection up "$BR" 2>/dev/null || true
fi

log "Creando $TAP si no existe"
if ! ip link show "$TAP" &>/dev/null; then
  sudo ip tuntap add dev "$TAP" mode tap user "${SUDO_USER:-$USER}"
fi
sudo ip link set "$TAP" up
sudo ip link set "$TAP" master "$BR"

log "Asegurando Internet por $STA_IF ($STA_CON)"
if ! nmcli -t -f DEVICE,STATE device status | grep -q "^${STA_IF}:connected"; then
  sudo nmcli connection up "$STA_CON"
fi
ip route | grep -q '^default' || die "No hay ruta por defecto (revisar $STA_CON)"

log "Liberando $AP_IF para el AP"
sudo nmcli device disconnect "$AP_IF" 2>/dev/null || true
sudo nmcli device set "$AP_IF" managed no 2>/dev/null || true

log "Arrancando hostapd"
if ! pgrep -x hostapd >/dev/null; then
  sudo hostapd -B "$AP_CONF"
fi

log "Esperando que $TAP pase a forwarding"
for _ in $(seq 1 30); do
  if bridge link show 2>/dev/null | grep -q "$TAP.*state forwarding"; then
    break
  fi
  sleep 1
done

if ! bridge link show 2>/dev/null | grep -q "$TAP.*state forwarding"; then
  echo "AVISO: $TAP no está en forwarding todavía. Revisar bridge/STP."
fi

log "Arrancando QEMU"
if pgrep -f "qemu-system-x86_64.*$DISK" >/dev/null; then
  log "QEMU ya está corriendo"
else
  exec qemu-system-x86_64 \
    -enable-kvm \
    -machine type=pc \
    -cpu host \
    -smp 2 \
    -m 512 \
    -drive file="$DISK",format=qcow2 \
    -boot c \
    -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:2222-:22,hostfwd=tcp:127.0.0.1:8291-:8291 \
    -netdev tap,id=lan0,ifname="$TAP",script=no,downscript=no \
    -device virtio-net-pci,netdev=lan0 \
    -display gtk
fi
```

Dar permisos y ejecutar:

```bash
chmod +x iniciar-lab.sh
./iniciar-lab.sh
```

> El script pide `sudo` una vez. Si tu usuario no tiene `sudo` sin contraseña, la terminal pedirá la clave al inicio.

### 12.1 Orden de arranque recomendado

1. Conectar el USB a TecRoot (el script lo hace).
2. Crear bridge y tap (el script lo hace).
3. Liberar la QCA y arrancar hostapd (el script lo hace).
4. Arrancar QEMU (el script lo hace al final).
5. Esperar ~20–30 segundos a que el CHR arranque y el bridge esté en *forwarding*.
6. Conectar el celular.

### 12.2 Apagado ordenado

```bash
# Cerrar QEMU (si está en primer plano, Ctrl+C; si no:)
pkill -f qemu-system-x86_64

# Detener el AP
sudo pkill hostapd

# Devolver la QCA a NetworkManager
sudo nmcli device set wlp59s0 managed yes
sudo nmcli connection up TecRoot

# Borrar el tap (opcional; se recrea al arrancar)
sudo ip link del tap-mikrotik
```

---

## 13. Seguridad y buenas prácticas

1. **Cambiar contraseñas por defecto**
   - RouterOS admin: `/user set admin password="..."`.
   - Usuario hotspot `cliente`.
   - Clave WiFi `mikrotik123`.
2. **No exponer SSH ni WinBox**: los reenvíos de QEMU están en `127.0.0.1`, correcto.
3. **Proteger el archivo de hostapd**:
   ```bash
   sudo chmod 600 /etc/hostapd/mikrotik-lab.conf
   ```
4. **No guardar la clave WiFi de TecRoot en documentos**. El perfil de NetworkManager la almacena; el script la reutiliza sin mostrarla.
5. **El hotspot no es un sistema de facturación**. Para producción, integrar RADIUS, portal personalizado y límites por usuario.
6. **CHR sin licencia**: límite de 1 Mbps. Para más velocidad, aplicar licencia.
7. **Aislar el laboratorio**: no conectar `ether2` a una red de producción.

---

## 14. Anexos

### Anexo A — Recrear el disco del CHR

```bash
cd /home/armintec/Documentos/MICRO-TIK
qemu-img convert -f raw -O qcow2 chr-7.24.5.img chr-disk.qcow2
```

Si la imagen está comprimida:

```bash
unzip chr-7.24.5.img.zip
qemu-img convert -f raw -O qcow2 chr-7.24.5.img chr-disk.qcow2
```

### Anexo B — Export actual del CHR

El laboratorio incluye configuración adicional (PPPoE, queue) que **no es necesaria** para el hotspot. El export limpio relevante es:

```routeros
/interface ethernet
set [ find default-name=ether1 ] disable-running-check=no
set [ find default-name=ether2 ] disable-running-check=no

/ip hotspot profile
add hotspot-address=192.168.77.254 name=hsprof1

/ip pool
add name=pool-lan ranges=192.168.77.100-192.168.77.199

/ip dhcp-server
add address-pool=pool-lan interface=ether2 lease-time=1h name=dhcp-lan

/ip address
add address=192.168.77.254/24 comment="LAN LABORATORIO" interface=ether2 network=192.168.77.0

/ip dhcp-client
add interface=ether1 name=client1

/ip dhcp-server network
add address=192.168.77.0/24 dns-server=1.1.1.1,8.8.8.8 gateway=192.168.77.254

/ip firewall nat
add action=masquerade chain=srcnat comment="NAT HACIA INTERNET" out-interface=ether1
add action=masquerade chain=srcnat comment="masquerade hotspot network" src-address=192.168.77.0/24

/ip hotspot
add address-pool=pool-lan disabled=no interface=ether2 name=hotspot1 profile=hsprof1

/ip hotspot user
add name=cliente comment="Usuario de prueba"

/ppp secret
add name=cliente001 profile=perfil-pppoe-5M service=pppoe

/system identity
set name=MICRO-DEV-ROOT
```

> El export omite contraseñas por seguridad (`hide-sensitive`). El usuario `cliente` tiene la clave definida en este documento.

### Anexo C — Comandos rápidos

| Acción | Comando |
|---|---|
| Ver estado del AP | `iw dev wlp59s0 info` |
| Ver clientes WiFi | `sudo hostapd_cli all_sta` |
| Ver bridge | `bridge link show` |
| Ver leases DHCP del CHR | `/ip dhcp-server lease print` |
| Ver sesiones hotspot | `/ip hotspot active print` |
| Ver hosts del hotspot | `/ip hotspot host print` |
| Cerrar sesión de un usuario | `/ip hotspot active remove [find user=cliente]` |
| Ver logs hotspot | `/log print where topics~"hotspot"` |
| Probar portal | `curl -I http://192.168.77.254/login` |
| Reiniciar hostapd | `sudo pkill hostapd && sudo hostapd -B /etc/hostapd/mikrotik-lab.conf` |
| Ver errores de hostapd | `sudo hostapd -dd /etc/hostapd/mikrotik-lab.conf` |

### Anexo D — Glosario

| Término | Significado |
|---|---|
| **CHR** | Cloud Hosted Router: RouterOS para máquinas virtuales, sin WiFi. |
| **Hotspot** | Portal cautivo de RouterOS; autentica clientes en una red IP. |
| **Tap** | Interfaz de red virtual de capa 2 que conecta QEMU con el host. |
| **Bridge** | Switch virtual de Linux que une interfaces (AP + tap). |
| **hostapd** | Demonio que convierte una interfaz WiFi en punto de acceso. |
| **AP** | Access Point; emite el SSID. |
| **STA** | Station; modo cliente WiFi. |
| **NAT slirp** | NAT en espacio de usuario que QEMU usa para dar Internet al guest. |
| **DoT** | DNS over TLS; Android lo usa como "DNS privado" y puede saltarse el DNS del hotspot. |
| **STP** | Spanning Tree Protocol; evita bucles, pero retrasa el forwarding. |

---

## Resumen final

```
1. Crear bridge br-mikrotik (192.168.77.1/24).
2. Crear tap-mikrotik y unirlo al bridge.
3. Arrancar QEMU con la imagen chr-disk.qcow2.
4. Configurar el CHR: DHCP, NAT y hotspot con dns-name="".
5. Conectar el USB a TecRoot (Internet).
6. Liberar la QCA y arrancar hostapd (SSID MIKROTIK-LAB).
7. Conectar el celular, abrir http://192.168.77.254/login.
8. Autenticarse con cliente / cliente123.
```

Con esto el laboratorio queda reproducible desde cero y documentado para futuras modificaciones.
