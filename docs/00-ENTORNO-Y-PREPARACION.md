# Entorno y Preparación — Laboratorio MikroTik CHR + Hotspot

> **Este es el primer documento.** Describe *qué* es el laboratorio, *qué* necesitas y *cómo* preparar
> todo el entorno antes de configurar nada en RouterOS.
> La parte de **comandos de MikroTik** está en → [`01-COMANDOS-MIKROTIK.md`](./01-COMANDOS-MIKROTIK.md)

---

## Índice

1. [Propósito y alcance](#1-propósito-y-alcance)
2. [Cómo se usará este laboratorio](#2-cómo-se-usará-este-laboratorio)
3. [Conceptos que hay que entender antes](#3-conceptos-que-hay-que-entender-antes)
4. [Arquitectura del laboratorio](#4-arquitectura-del-laboratorio)
5. [Inventario de archivos](#5-inventario-de-archivos)
6. [Requisitos](#6-requisitos)
7. [Fase 1 — Preparar el host (Fedora)](#7-fase-1--preparar-el-host-fedora)
8. [Fase 2 — Preparar el CHR](#8-fase-2--preparar-el-chr)
9. [Fase 3 — Preparar el AP WiFi](#9-fase-3--preparar-el-ap-wifi)
10. [Arranque y parada](#10-arranque-y-parada)
11. [Verificación por capas](#11-verificación-por-capas)
12. [Problemas del entorno](#12-problemas-del-entorno)
13. [Seguridad del entorno](#13-seguridad-del-entorno)

---

## 1. Propósito y alcance

Este laboratorio permite **reproducir un portal cautivo MikroTik real** sin hardware MikroTik, usando:

- Un **MikroTik CHR** (Cloud Hosted Router) virtualizado con **QEMU/KVM** en una laptop.
- La **laptop como host** de la virtualización.
- Un **adaptador WiFi en modo AP** (`hostapd`) que emite el SSID.
- Un **segundo adaptador WiFi** (o cable) que aporta la salida a Internet.

**Resultado:** un celular se conecta al SSID del laboratorio, recibe IP del MikroTik, ve el portal
captivo, se autentica y navega a Internet a través del CHR.

### Qué NO es este laboratorio

| No es | Por qué |
|---|---|
| Un producto comercializable | El hotspot de RouterOS no trae facturación, cobros ni panel de cliente. |
| Un sustituto de un router MikroTik físico | El CHR no tiene radio WiFi; el SSID lo pone la laptop. |
| Un banco de pruebas de alto rendimiento | Sin licencia CHR, el límite es **1 Mbps**. |
| Un entorno de producción | Ver [Seguridad del entorno](#13-seguridad-del-entorno). |

### Documentos relacionados

| Documento | Cuándo leerlo |
|---|---|
| **Este** | Siempre, antes de tocar nada. |
| [`01-COMANDOS-MIKROTIK.md`](./01-COMANDOS-MIKROTIK.md) | Cuando el entorno ya está arriba y quieras configurar el hotspot. |
| [`DOCUMENTACION-HOTSPOT-CHR.md`](./DOCUMENTACION-HOTSPOT-CHR.md) | Documento narrativo original, con historia y contexto. Útil como referencia. |

---

## 2. Cómo se usará este laboratorio

El flujo de trabajo es siempre el mismo, en este orden:

```
   PASO 1              PASO 2               PASO 3              PASO 4
┌──────────────┐   ┌───────────────┐   ┌────────────────┐   ┌────────────────┐
│ Preparar el  │──▶│ Preparar el   │──▶│ Preparar el AP │──▶│  Configurar el │
│   ENTORNO    │   │     CHR       │   │      WiFi      │   │    HOTSPOT     │
│  (este doc)  │   │  (este doc)   │   │  (este doc)    │   │  (doc 01)      │
└──────────────┘   └───────────────┘   └────────────────┘   └────────────────┘
   bridge, tap       QEMU + SSH          hostapd + SSID      usuarios, perfiles,
   QEMU, KVM        IP, DHCP, NAT       cliente en AP       límites, tiempos
```

### Reglas de oro del laboratorio

1. **Primero el host, después el CHR.** El CHR sin bridge/tap no tiene red.
2. **Nunca una ruta por defecto hacia el CHR en la laptop.** Provoca un bucle de NAT. Ver §12.5.
3. **STP desactivado** en el bridge, si no los puertos tardan 15–30 s en pasar a *forwarding*.
4. **El CHR no emite WiFi.** El SSID lo emite la laptop.
5. **La laptop necesita dos radios WiFi** para AP + Internet simultáneos. Ver §12.2.

### Cuándo usar cada modo de DNS

| Modo | Configuración | Cuándo |
|---|---|---|
| **A — Solo IP** (recomendado) | `dns-name=""`, portal en `http://192.168.77.254/login` | Por defecto. Funciona siempre. |
| **B — Con nombre** | `dns-name=wifi.dev` + DNS estático + DNS privado off en Android | Solo si quieres una URL bonita. Ver §12.4. |

---

## 3. Conceptos que hay que entender antes

### 3.1 El CHR no tiene WiFi

El **CHR** es RouterOS para máquinas virtuales. **No incluye radio ni driver wireless.**
Sus interfaces son Ethernet virtuales:

| Interfaz CHR | Conectada a | Función |
|---|---|---|
| `ether1` | NAT de QEMU (`-nic user`) | WAN / salida a Internet |
| `ether2` | tap `tap-mikrotik` de la laptop | LAN del hotspot |

> Aunque RouterOS tenga el hotspot perfectly configurado, **no emite ningún SSID**.
> El SSID lo emite la laptop con `hostapd`.

### 3.2 Qué es realmente el "hotspot" de RouterOS

El hotspot es un **portal cautivo** que funciona sobre una red IP normal. No es una tecnología WiFi:

1. Detecta clientes no autenticados en la interfaz configurada.
2. Redirige su tráfico HTTP/HTTPS/DNS al portal de login.
3. Valida usuario y contraseña.
4. Autoriza la MAC/IP del cliente y le permite salir.
5. Aplica límites de tiempo, velocidad y tráfico según el perfil.

### 3.3 La cadena completa del tráfico

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
NAT de QEMU (slirp) → adaptador de salida → Internet
```

### 3.4 Glosario mínimo

| Término | Significado |
|---|---|
| **CHR** | Cloud Hosted Router: RouterOS para máquinas virtuales, sin WiFi. |
| **Hotspot** | Portal cautivo de RouterOS; autentica clientes en una red IP. |
| **Tap** | Interfaz de red virtual de capa 2 que conecta QEMU con el host. |
| **Bridge** | Switch virtual de Linux que une interfaces (AP + tap). |
| **hostapd** | Demonio que convierte una interfaz WiFi en punto de acceso. |
| **AP / STA** | Access Point (emite SSID) / Station (se conecta a un AP). |
| **NAT slirp** | NAT en espacio de usuario que QEMU usa para dar Internet al guest. |
| **DoT** | DNS over TLS; Android lo usa como "DNS privado" y puede saltarse el DNS del hotspot. |
| **STP** | Spanning Tree Protocol; evita bucles, pero retrasa el forwarding. |
| **NAT de QEMU** | `10.0.2.2` es la gateway, `10.0.2.3` el DNS, `10.0.2.15` la IP del guest. |

---

## 4. Arquitectura del laboratorio

### 4.1 Interfaces del host (laptop)

| Interfaz | Tipo | Función | IP |
|---|---|---|---|
| `wlp0s20f0u1` | WiFi USB MT7601U | Cliente de TecRoot (salida a Internet) | DHCP `192.168.100.x` |
| `wlp59s0` | WiFi PCIe QCA6174 | AP del laboratorio (`MIKROTIK-LAB`) | sin IP (bridge) |
| `br-mikrotik` | Bridge Linux | Une el AP y el tap | `192.168.77.1/24` |
| `tap-mikrotik` | TAP de QEMU | Enlace L2 hacia el CHR | sin IP |
| `enp0s20f0u2c2` | Ethernet USB | No usada en este montaje | — |

> ⚠️ **Los nombres de interfaz pueden cambiar** al reconectar adaptadores USB.
> Verifica siempre con `nmcli device status` e `iw dev` antes de seguir una instrucción.

### 4.2 Interfaces y direcciones del CHR

| Interfaz | IP | Función |
|---|---|---|
| `ether1` | `10.0.2.15/24` (DHCP) | WAN, salida por NAT de QEMU |
| `ether2` | `192.168.77.254/24` | LAN del hotspot |
| `lo` | `127.0.0.1` | Loopback |

- Gateway de `ether1`: `10.0.2.2`
- DNS de QEMU: `10.0.2.3`
- Pool DHCP del hotspot: `192.168.77.100 – 192.168.77.199`

### 4.3 Puertos publicados por QEMU

| Host | CHR | Servicio |
|---|---|---|
| `127.0.0.1:2222` | `22` | SSH |
| `127.0.0.1:8291` | `8291` | WinBox |

> Los puertos están enlazados solo a `127.0.0.1`, así que **no** quedan expuestos a la red WiFi.

### 4.4 Valores por defecto del laboratorio

| Parámetro | Valor |
|---|---|
| Identidad del CHR | `MICRO-DEV-ROOT` |
| SSH del CHR | `ssh -p 2222 admin@127.0.0.1` |
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

> 🔴 **Cambia todas las claves antes de usar esto fuera del laboratorio.**

---

## 5. Inventario de archivos

```
MICRO-TIK/
├── README.md                          ← este índice general
├── DOCUMENTACION-HOTSPOT-CHR.md       ← documento narrativo original
├── docs/
│   ├── 00-ENTORNO-Y-PREPARACION.md    ← este documento
│   └── 01-COMANDOS-MIKROTIK.md        ← catálogo de comandos RouterOS
├── scripts/
│   ├── iniciar-lab.sh                 ← levanta todo el laboratorio
│   └── parar-lab.sh                   ← lo detiene de forma ordenada
├── chr-7.24.5.img                     ← imagen raw original (128 MB)
├── chr-7.24.5.img.zip                 ← respaldo comprimido
├── chr-disk.qcow2                     ← disco de trabajo (el que usa QEMU)
├── chr-disk-vm2-limpia.qcow2          ← disco limpio para una VM secundaria
├── chr-lab.img                        ← imagen de laboratorio alternativa
├── iniciar.txt                        ← comando QEMU suelto (comodín)
└── tap-mikrotik.txt                   ← registro de un error de TAP (histórico)
```

Las imágenes están en `.gitignore` porque son pesadas. El repo solo versiona la documentación y scripts.

---

## 6. Requisitos

### 6.1 Hardware

- Laptop con virtualización por hardware (VT-x/AMD-V) habilitada en BIOS.
- **Dos adaptadores WiFi**:
  - Uno para la salida a Internet (en este montaje, un USB MT7601U).
  - Otro que soporte **modo AP** (en este montaje, una QCA6174 PCIe).
- Al menos 2 GB de RAM libre (el CHR usa 512 MB).
- Espacio en disco para la imagen del CHR (~128 MB + crecimiento).

> Si solo tienes un adaptador, puedes intentar AP+STA simultáneos, pero muchos firmwares
> (incluido el de la QCA6174 de este laboratorio) fallan con `Operation already in progress`.
> La solución robusta es **usar dos adaptadores**. Ver §12.2.

### 6.2 Software en Fedora

```bash
sudo dnf install -y qemu-system-x86 qemu-img hostapd iw NetworkManager
```

Verificar versiones:

```bash
qemu-system-x86_64 --version   # probado: 10.2.2
hostapd -v                     # probado: 2.11
iw --version
```

### 6.3 Virtualización y permisos

```bash
ls -l /dev/kvm      # debe existir
ls -l /dev/net/tun  # debe existir
id | grep -o 'kvm'  # tu usuario debe estar en el grupo kvm
```

Si `/dev/kvm` no existe, habilita VT-x/AMD-V en la BIOS.

### 6.4 Imagen del CHR

Si necesitas recrear el disco de trabajo desde la imagen raw:

```bash
cd /home/armintec/Documentos/MICRO-TIK
qemu-img convert -f raw -O qcow2 chr-7.24.5.img chr-disk.qcow2
```

> **Licencia CHR:** sin licencia, el CHR está limitado a **1 Mbps**. Para un laboratorio de portal es
> suficiente. Para más velocidad, aplica una licencia MikroTik (P1, P2 o superior).

---

## 7. Fase 1 — Preparar el host (Fedora)

### 7.1 Crear el bridge `br-mikrotik`

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
ip -brief addr show br-mikrotik    # UP + 192.168.77.1/24
nmcli -g bridge.stp con show br-mikrotik   # debe decir: no
```

> **STP desactivado** es importante: con STP activo los puertos tardan 15–30 s en pasar a
> *forwarding*, y el celular no puede pasar tráfico hasta entonces.

Si el bridge ya existe, **no lo vuelvas a crear**; solo ajústalo con `nmcli con mod`.

### 7.2 Crear el tap de QEMU

```bash
sudo ip tuntap add dev tap-mikrotik mode tap user "$USER" persist on
sudo ip link set tap-mikrotik up
sudo ip link set tap-mikrotik master br-mikrotik
```

Verificar:

```bash
ip link show tap-mikrotik
bridge link show | grep tap-mikrotik    # debe listarlo como forward
```

> - `persist on` hace que el tap sobreviva a que QEMU lo suelte.
> - Si `ip tuntap add` falla con `Operation not permitted`, falta `sudo` o permiso sobre `/dev/net/tun`.
> - Si el puerto aparece en `listening`/`learning`, espera unos segundos o desactiva STP.

### 7.3 (Opcional) Perfil de NetworkManager para el tap

```bash
sudo nmcli con add type ethernet ifname tap-mikrotik con-name tap-mikrotik master br-mikrotik
```

En la práctica los dispositivos TAP no siempre los gestiona NetworkManager; los comandos `ip link`
del paso 7.2 son la fuente de verdad. El perfil no estorba.

### 7.4 Conectar el adaptador USB a TecRoot (salida a Internet)

Si ya existe el perfil `TecRoot`, reutiliza su clave sin exponerla:

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
ip route | grep default     # debe salir por wlp0s20f0u1
```

> Este paso es **crítico**: al liberar la QCA para el AP, la laptop pierde su conexión WiFi
> original. Internet debe seguir por el USB.

### 7.5 Arrancar QEMU

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

| Flag | Significado |
|---|---|
| `-nic user,...` | Primera NIC (`ether1`) con NAT de QEMU y reenvío de puertos. |
| `-netdev tap,...` | Segunda NIC (`ether2`) conectada al tap del host. |
| `script=no,downscript=no` | QEMU no crea ni destruye el tap; ya lo creamos nosotros. |
| `-display gtk` | Ventana de QEMU (usa `-display none` si no la necesitas). |

> 💡 Ojo con el orden de las NICs: QEMU las enumera en el orden en que aparecen los dispositivos
> de red. La primera (`-nic user`) siempre será `ether1`.

### 7.6 Comprobar el enlace hacia el CHR

```bash
ping -c 3 192.168.77.254
```

Mientras el cliente no esté autenticado es normal recibir `Destination Net Prohibited` o perder ICMP:
el hotspot bloquea clientes no autorizados. Lo importante es que el CHR **responda** (aunque sea con
un ICMP de rechazo).

---

## 8. Fase 2 — Preparar el CHR

> Los comandos detallados (perfiles, walled-garden, colas, límites) están en
> [`01-COMANDOS-MIKROTIK.md`](./01-COMANDOS-MIKROTIK.md). Aquí solo la base mínima.

### 8.1 Acceso inicial

```bash
ssh -p 2222 admin@127.0.0.1
```

En un CHR recién instalado, `admin` no tiene contraseña. Cámbiala de inmediato:

```routeros
/user set admin password="TU_CLAVE_SEGURA"
```

> 🔴 **No guardes la contraseña en los `.md`.** Usa el gestor de contraseñas del sistema.
> Los reenvíos de puerto están en `127.0.0.1`, así que no queda expuesta a la red.

### 8.2 Configuración base mínima

```routeros
# Identidad
/system identity set name=MICRO-DEV-ROOT

# ether1: cliente DHCP hacia el NAT de QEMU
/ip dhcp-client add interface=ether1 name=client1 disabled=no

# ether2: LAN del hotspot
/ip address add address=192.168.77.254/24 interface=ether2 comment="LAN HOTSPOT"

# NAT de salida
/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade comment="NAT salida"
```

Verificar que `ether1` tome IP:

```routeros
/ip address print
/ip route print
```

Debe aparecer `10.0.2.15/24` en `ether1` y la ruta por defecto `0.0.0.0/0` vía `10.0.2.2`.

### 8.3 DHCP y pool

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

### 8.4 Hotspot mínimo

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

/ip hotspot user add \
  name=cliente \
  password=cliente123 \
  profile=default \
  comment="Usuario de prueba"
```

Puntos importantes:

- `hotspot-address=192.168.77.254` **debe coincidir** con la IP de `ether2`.
- **`dns-name=""` es intencional.** Si pones `wifi.dev`, el formulario apunta a `http://wifi.dev/login`
  y los clientes con DNS privado en Android no pueden enviar el login. Ver §12.4.
- El hotspot crea automáticamente las reglas NAT dinámicas del portal.

> Para la lista completa de propiedades del hotspot (tiempos, cuotas, scripts, RADIUS) ver
> [`01-COMANDOS-MIKROTIK.md`](./01-COMANDOS-MIKROTIK.md).

### 8.5 Script RouterOS completo

Para partir de un CHR limpio, guárdalo como `hotspot-lab.rsc` y ejecútalo con
`/import file-name=hotspot-lab.rsc`. El script íntegro está en
[`01-COMANDOS-MIKROTIK.md`](./01-COMANDOS-MIKROTIK.md) (sección "Script completo").

---

## 9. Fase 3 — Preparar el AP WiFi

### 9.1 Identificar los adaptadores

```bash
iw dev
nmcli -f DEVICE,TYPE,STATE,CONNECTION device status
```

Comprobar que la interfaz del AP soporta modo AP:

```bash
iw phy phy0 info | sed -n '/Supported interface modes/,/Band/p'
```

Debe incluir `* AP`. El MT7601U solo soporta `managed` y `monitor`, por eso no puede ser AP.

> 💡 Script para listar todas las interfaces que **sí** soportan AP:
> ```bash
> for phy in $(iw dev | awk '/^phy#/{print $1}'); do
>   iw phy "$phy" info | grep -qE '^\s+\* AP$' && echo "$phy soporta AP"
> done
> ```

### 9.2 Liberar la interfaz para el AP

```bash
sudo nmcli device disconnect wlp59s0
sudo nmcli device set wlp59s0 managed no
```

Verificar que quede sin conexión y sin IP:

```bash
nmcli -f DEVICE,STATE,CONNECTION device status
ip -brief addr show wlp59s0
```

### 9.3 Configurar hostapd

Crea `/etc/hostapd/mikrotik-lab.conf`:

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

| Parámetro | Significado |
|---|---|
| `bridge=br-mikrotik` | hostapd mete la interfaz AP en el bridge automáticamente. |
| `hw_mode=g` + `channel=11` | 2.4 GHz, canal 11 (canal no solapado con TecRoot, canal 4). |
| `wpa=2` + `WPA-PSK` + `CCMP` | WPA2 con cifrado fuerte. |
| `ieee80211n=1` | Habilita 802.11n. |
| `wmm_enabled=1` | QoS WiFi (necesario para throughput decente). |

> Si TecRoot cambia de canal, elige 1, 6 u 11 que no se solape. Ver canal actual con
> `iw dev wlp0s20f0u1 link`.

### 9.4 Arrancar hostapd

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

Clientes WiFi asociados:

```bash
sudo hostapd_cli all_sta
```

---

## 10. Arranque y parada

### 10.1 Scripts incluidos

```bash
cd /home/armintec/Documentos/MICRO-TIK

./scripts/iniciar-lab.sh     # levanta todo (bridge, tap, hostapd, QEMU)
./scripts/parar-lab.sh       # detiene todo de forma ordenada
./scripts/parar-lab.sh --full   # además borra tap y bridge
```

`iniciar-lab.sh` **detecta automáticamente** qué interfaz hace de uplink (la que tiene la ruta por
defecto) y cuál hace de AP (la única que soporte modo AP y no sea el uplink). Falla con un mensaje
claro si solo hay una radio WiFi.

Variables opcionales para forzar interfaces:

```bash
AP_IF=wlp59s0 UPLINK_IF=wlp0s20f0u1 ./scripts/iniciar-lab.sh
```

### 10.2 Orden de arranque recomendado

1. Conectar el USB a TecRoot (lo hace el script).
2. Crear bridge y tap (lo hace el script).
3. Liberar la interfaz del AP y arrancar hostapd (lo hace el script).
4. Arrancar QEMU (lo hace el script, al final).
5. Esperar **20–30 segundos** a que el CHR arranque y el bridge esté en *forwarding*.
6. Conectar el celular y autenticarse.

### 10.3 Apagado ordenado

```bash
# Cerrar QEMU (si está en primer plano, Ctrl+C; si no:)
pkill -f qemu-system-x86_64

# Detener el AP
sudo pkill hostapd

# Devolver la interfaz a NetworkManager
sudo nmcli device set wlp59s0 managed yes
sudo nmcli connection up TecRoot

# Borrar el tap (opcional; se recrea al arrancar)
sudo ip link del tap-mikrotik
```

---

## 11. Verificación por capas

Verifica **de abajo hacia arriba**. No avances de capa si la anterior falla.

### Capa 1 — Host tiene Internet

```bash
ip route | grep default
ping -c 3 1.1.1.1
ping -c 3 google.com
```

### Capa 2 — Bridge y tap

```bash
ip -brief addr show br-mikrotik      # UP + 192.168.77.1/24
ip link show tap-mikrotik            # UP
bridge link show                     # tap-mikrotik en forwarding
```

### Capa 3 — AP emitiendo

```bash
pgrep -a hostapd
iw dev wlp59s0 info                  # type AP, channel 11
sudo hostapd_cli all_sta             # lista de clientes
```

### Capa 4 — CHR con IP y ruta

```routeros
/system identity print
/ip address print          # ether1 = 10.0.2.15/24, ether2 = 192.168.77.254/24
/ip route print            # 0.0.0.0/0 vía 10.0.2.2
/ping 1.1.1.1 count=3
```

### Capa 5 — Hotspot sirviendo

```routeros
/ip hotspot print                     # proxy-status="running"
/ip hotspot user print
/ip dhcp-server lease print
/ip hotspot active print
```

### Capa 6 — Portal respondiendo

```bash
# La página de login debe responder 200
curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://192.168.77.254/login

# El formulario debe apuntar a la IP, no a wifi.dev
curl -sS http://192.168.77.254/login | grep -E 'form name="(sendin|login)"'
```

Debe mostrar:

```html
<form name="sendin" action="http://192.168.77.254/login" ...>
<form name="login" action="http://192.168.77.254/login" ...>
```

Si aparece `wifi.dev`, el perfil del hotspot todavía tiene `dns-name` configurado. Corregir con:

```routeros
/ip hotspot profile set hsprof1 dns-name=""
```

### Capa 7 — Cliente autenticado

```routeros
/ip hotspot active print detail
```

Debe aparecer el usuario con la MAC y la IP del celular.

---

## 12. Problemas del entorno

### 12.1 El celular no ve el SSID

| Causa probable | Verificación | Solución |
|---|---|---|
| hostapd no está corriendo | `pgrep -a hostapd` | `sudo hostapd -B /etc/hostapd/mikrotik-lab.conf` |
| Interfaz ocupada por NetworkManager | `nmcli device status` | `sudo nmcli device disconnect wlp59s0; sudo nmcli device set wlp59s0 managed no` |
| Canal no permitido | `iw reg get` | Usar canal 1, 6 u 11 |
| Adaptador no soporta AP | `iw phy phyX info` | Usar otro adaptador |
| hostapd falla al iniciar | `sudo hostapd -dd /etc/hostapd/mikrotik-lab.conf` | Leer el error concreto |

### 12.2 `hostapd: Could not configure driver mode ... Operation already in progress`

Significa que el driver **no soporta AP + STA simultáneos** en la misma radio. Ocurrió con la QCA6174.

**Solución aplicada en este laboratorio:**

1. Conectar el **segundo adaptador** (MT7601U USB) a TecRoot como cliente.
2. Desconectar la QCA de TecRoot y ponerla en modo AP.

Si solo tienes un adaptador, alternativas:

- Usar el mismo canal que la conexión STA (algunos drivers lo permiten).
- Usar un AP externo conectado por Ethernet.
- Usar un router MikroTik físico con wireless.

### 12.3 El celular se conecta pero no recibe IP

| Causa probable | Verificación | Solución |
|---|---|---|
| `tap-mikrotik` está DOWN | `ip link show tap-mikrotik` | `sudo ip link set tap-mikrotik up` |
| Tap no está en el bridge | `bridge link show` | `sudo ip link set tap-mikrotik master br-mikrotik` |
| Puerto en `listening`/`learning` | `bridge link show` | Esperar o desactivar STP: `sudo nmcli con mod br-mikrotik bridge.stp no && sudo nmcli con up br-mikrotik` |
| DHCP del CHR no corre | `/ip dhcp-server print` | Habilitarlo y revisar el pool |
| Pool agotado | `/ip pool print` | Ampliar el rango |

### 12.4 `wifi.dev` no carga

1. `wifi.dev` **no existe en Internet**. Es un nombre privado del hotspot.
2. Los DNS públicos (`1.1.1.1`, `8.8.8.8`) devuelven NXDOMAIN.
3. Android con **DNS privado (DoT)** consulta directo a `8.8.8.8:853` y se salta el DNS del hotspot.
4. Si el formulario apunta a `wifi.dev`, el POST nunca llega y el login "no hace nada".

**Soluciones:**

- **Recomendada:** usar la IP `http://192.168.77.254/login` y dejar `dns-name=""`.
- **Alternativa:** configurar el DNS del MikroTik + entrada estática y desactivar el DNS privado
  en el celular (Android: Ajustes → Red e Internet → DNS privado → Desactivado).
- En la laptop, `/etc/hosts` puede forzar el nombre, pero **solo afecta a la laptop**:
  ```bash
  echo '192.168.77.254  wifi.dev' | sudo tee -a /etc/hosts
  ```

### 12.5 La laptop se quedó sin Internet al liberar la QCA

Es lo esperado: la QCA era la conexión original.

```bash
nmcli -f DEVICE,STATE,CONNECTION device status
iw dev wlp0s20f0u1 link
ip route | grep default
```

Si el USB no está conectado:

```bash
sudo nmcli con up TecRoot-USB
```

Para recuperar la conexión original por la QCA:

```bash
sudo pkill hostapd
sudo nmcli device set wlp59s0 managed yes
sudo nmcli connection up TecRoot
```

### 12.6 Bucle de NAT: el host no debe enrutar por `192.168.77.254`

**No agregues una ruta por defecto en la laptop hacia el CHR.** El CHR usa el NAT de QEMU (slirp), cuyo
tráfico sale por el host. Si el host enruta ese tráfico de vuelta al CHR, se produce un **bucle**:

```
CHR → slirp → host → (ruta por defecto al CHR) → CHR → ...
```

El host debe seguir usando el USB (`TecRoot-USB`) como ruta por defecto. Solo los clientes externos
(el celular) deben salir por el hotspot.

### 12.7 `tap-mikrotik: Operation not permitted` / `could not configure /dev/net/tun`

- Crear el tap con `sudo` y con `user "$USER"`.
- Verificar `/dev/net/tun` y que el usuario tenga permiso.
- No dejar que QEMU cree el tap (`script=no,downscript=no`).
- Si el tap existe pero QEMU no lo encuentra: `sudo ip link del tap-mikrotik` y vuelve a crearlo.

### 12.8 Tabla de decisión rápida

| Síntoma | Causa más probable | Solución |
|---|---|---|
| No hay internet en la laptop | QCA liberada y USB no conectado | `sudo nmcli con up TecRoot-USB` |
| Cellular no ve SSID | hostapd caído / NM managing | §12.1 |
| Cellular ve SSID pero no IP | tap fuera del bridge | §12.3 |
| Portal no abre | `dns-name` con `wifi.dev` | `/ip hotspot profile set hsprof1 dns-name=""` |
| Login "no hace nada" | formulario apunta a `wifi.dev` | `/ip hotspot profile set hsprof1 dns-name=""` |
| Autentica pero no navega | falta NAT o sin internet en el CHR | `/ping 1.1.1.1 count=3` |
| Todo lento o intermitente | STP activo | `nmcli con mod br-mikrotik bridge.stp no` |

---

## 13. Seguridad del entorno

1. **Cambia contraseñas por defecto**:
   - RouterOS admin: `/user set admin password="..."`.
   - Usuario hotspot `cliente`.
   - Clave WiFi `mikrotik123`.
2. **No expongas SSH ni WinBox**: los reenvíos de QEMU están en `127.0.0.1`. Correcto.
3. **Protege el archivo de hostapd**:
   ```bash
   sudo chmod 600 /etc/hostapd/mikrotik-lab.conf
   ```
4. **No guardes la clave WiFi de TecRoot en documentos**. El perfil de NetworkManager la almacena;
   el script la reutiliza sin mostrarla.
5. **El hotspot no es un sistema de facturación**. Para producción, integra RADIUS, portal
   personalizado y límites por usuario.
6. **CHR sin licencia**: límite de 1 Mbps. Aplica licencia si necesitas más.
7. **Aísla el laboratorio**: no conectes `ether2` a una red de producción.

---

## Siguiente paso

El entorno está listo. Ahora sí, a configurar el hotspot:

→ **[`01-COMANDOS-MIKROTIK.md`](./01-COMANDOS-MIKROTIK.md)** — comandos RouterOS, tiempos, perfiles,
límites de ancho de banda, walled-garden, cuotas y diagnóstico.
