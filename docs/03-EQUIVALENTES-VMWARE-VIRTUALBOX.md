# Equivalentes VMware y VirtualBox — el CHR fuera de QEMU

> **Este es el cuarto documento.** Cómo montar el **mismo laboratorio MikroTik CHR + Hotspot**
> en **VMware Workstation/Player** y en **Oracle VirtualBox**, en lugar de QEMU/KVM.
> El entorno base (bridge, tap, hostapd) está en → [`00-ENTORNO-Y-PREPARACION.md`](./00-ENTORNO-Y-PREPARACION.md)

**Versión de referencia:** RouterOS 7.24.x (CHR) · VMware Workstation 17.x · VirtualBox 7.x
**Sintaxis y formatos verificados contra:** MikroTik (descargas CHR), Oracle VirtualBox Manual 7.x

---

## Índice

1. [Para qué sirve este documento](#1-para-qué-sirve-este-documento)
2. [La equivalencia mental: QEMU ↔ VMware ↔ VirtualBox](#2-la-equivalencia-mental-qemu--vmware--virtualbox)
3. [Qué imagen usar para cada hipervisor](#3-qué-imagen-usar-para-cada-hipervisor)
4. [Método A — VMware Workstation / Player](#4-método-a--vmware-workstation--player)
5. [Método B — Oracle VirtualBox](#5-método-b--oracle-virtualbox)
6. [Conversión de la imagen que ya tienes](#6-conversión-de-la-imagen-que-ya-tienes)
7. [Los dos modelos de red](#7-los-dos-modelos-de-red)
8. [Reconfigurar el CHR dentro de la VM](#8-reconfigurar-el-chr-dentro-de-la-vm)
9. [Conectar el AP de hostapd](#9-conectar-el-ap-de-hostapd)
10. [Rendimiento: qué esperar](#10-rendimiento-qué-esperar)
11. [Troubleshooting](#11-troubleshooting)
12. [Checklist final](#12-checklist-final)

---

## 1. Para qué sirve este documento

En el laboratorio original el CHR arranca con **QEMU/KVM**, con una topología muy concreta:

- **ether1** → red de usuario de QEMU (NAT + reenvío de puertos a `127.0.0.1`).
- **ether2** → un **tap** enchufado a un **bridge del host** (`br-mikrotik`, 192.168.77.1/24),
  donde vive la interfaz WiFi del AP `hostapd`.

Esa topología se puede reproducir **exactamente igual** en VMware y en VirtualBox. Lo único que
cambia es la sintaxis: en vez de flags de QEMU, hay menús y archivos de configuración.

Este documento te da:

1. La **tabla de equivalencias** para no perderte.
2. Los **pasos exactos** en cada hipervisor.
3. La **conversión de imagen** si ya tienes el `.qcow2` del laboratorio.
4. Los **scripts de red** para conectar el AP.

> 💡 La configuración de RouterOS **dentro** del CHR **no cambia** (mismas interfaces, mismo
> `hotspot-address`, mismos usuarios). Solo cambia cómo secreates la máquina virtual y cómo
> se enchufan los cables virtuales.

---

## 2. La equivalencia mental: QEMU ↔ VMware ↔ VirtualBox

### 2.1 Tabla general

| Concepto | QEMU/KVM (tu laboratorio) | VMware Workstation | Oracle VirtualBox |
|---|---|---|---|
| **Disco del CHR** | `-drive file=chr.img,format=qcow2` | Disco VMDK (importado del OVA) | Disco VDI o VMDK (importado del OVA) |
| **1ª NIC (salida a Internet)** | `-nic user` (SLIRP) | Adaptador 1 → **NAT (vmnet8)** | Adaptador 1 → **NAT** |
| **2ª NIC (LAN del hotspot)** | `-netdev tap,ifname=tap-mikrotik` | Adaptador 2 → **Host-only (vmnet1)** o **Bridged** | Adaptador 2 → **Host-only (vboxnet0)** o **Bridged** |
| **Puente del host** | `br-mikrotik` (creado con `nmcli`) | `vmnet1` (lo crea VMware) o tu `br-mikrotik` | `vboxnet0` (lo crea VBoxNetAdp) o tu `br-mikrotik` |
| **Reenvío de puertos (SSH/WinBox)** | `hostfwd=tcp:127.0.0.1:2222-:22` | NAT Settings → Port Forwarding | `--natpf1 "ssh,tcp,127.0.0.1,2222,,22"` |
| **Aceleración** | `-enable-kvm -cpu host` | VT-x/AMD-V automática | VT-x/AMD-V (requiere PaNX) |
| **Tipo de NIC virtual** | `virtio-net-pci` | `VmxNet3` | `VirtIO-Net` o `Intel PRO/1000` |
| **Consola** | `-display gtk` | Consola propia de VMware | Consola propia de VBox |
| **Encender/apagar** | `./scripts/iniciar-lab.sh` | `vmrun start/stop` | `VBoxManage start/stopvms` |
| **Red host-only por defecto** | `br-mikrotik` 192.168.77.1/24 | `vmnet1` 192.168.50.0/24 | `vboxnet0` 192.168.56.0/24 |

### 2.2 Los cuatro objetos que existen en los tres

En los tres hipervisores, la red virtual se compone de las mismas cuatro piezas:

```
  ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
  │  SWITCH      │        │  SWITCH      │        │  SWITCH      │
  │  VIRTUAL     │        │  VIRTUAL     │        │  VIRTUAL     │
  │  (puente)    │        │  (vmnetX)    │        │  (vboxnetX)  │
  └──────┬───────┘        └──────┬───────┘        └──────┬───────┘
         │                       │                       │
    ┌────┴────┐             ┌────┴────┐             ┌────┴────┐
    │  NIC VM  │             │  NIC VM  │             │  NIC VM  │
    └─────────┘             └─────────┘             └─────────┘
         ▲
         │  (aquí se enchufa el AP de hostapd)
```

1. **Switch virtual** — un puente en el host. En QEMU lo haces tú (`br-mikrotik`);
   en VMware y VirtualBox ya existe (`vmnet1`, `vboxnet0`).
2. **Adaptador de red de la VM** — el "cable virtual".
3. **Puente del host** — donde vive la interfaz WiFi del AP.
4. **Regla NAT** — la salida a Internet.

> 🔑 **Regla de oro del mapeo:** en los tres casos, el **lado LAN del hotspot** es una red
> *aislada* (puente del host) y el **lado WAN** es una red *NAT*. Si respetas eso, todo lo
> demás funciona igual.

---

## 3. Qué imagen usar para cada hipervisor

MikroTik publica el CHR en formatos listos para cada hipervisor desde
<https://mikrotik.com/download/chr>. Elige el que corresponda **sin conversiones**:

| Formato | Hipervisor | Descarga oficial |
|---|---|---|
| **RAW disk** (`.img`) | QEMU/KVM, Proxmox, Hyper-V (con conversión) | `chr-<ver>.img.zip` |
| **OVA** | VMware Workstation, ESXi, VirtualBox | `chr-<ver>.ova` |
| **VMDK** | VMware Workstation, ESXi | `chr-<ver>.vmdk.zip` |
| **VDI** | VirtualBox | `chr-<ver>.vdi.zip` |
| **VHDX** | Hyper-V | `chr-<ver>.vhdx.zip` |
| **VHD** | VirtualPC / Hyper-V | `chr-<ver>.vhd.zip` |
| **arm64** | AWS Graviton, ARM (`.img` / `.vdi` arm64) | `chr-<ver>-arm64.*` |

### Ya tienes un OVA en este repositorio

```
CONFIGURACIÓN Y COMERCIALIZACIÓN DE INTERNET CON STARLINK Y UBIQUITI/chr-7.24.1.ova
```

Es un `tar` que contiene:

| Fichero | Contenido |
|---|---|
| `chr-7.24.1.ovf` | Descriptor XML de la appliance (hardware virtual, red, discos) |
| `chr-7.24.1.mf` | Manifiesto SHA-256 para verificar la integridad |
| `chr-7.24.1-disk1.vmdk` | Disco VMDK *streamOptimized* de 128 MB |

Características declaradas en el `.ovf`:

- Nombre de la VM: `MikroTik_RouterOS_CHR`
- SO invitado: `otherLinux64Guest`
- **1 vCPU**, **1024 MB** de RAM
- Controlador **IDE** con 1 disco (128 MB, streamOptimized)
- **1 adaptador VmxNet3** en la red «VM Network»
- Familia de hardware: `vmx-10`

> 💡 El OVA trae **una sola NIC**. Para el laboratorio del hotspot necesitas **dos**.
> Eso lo añades tú en los pasos siguientes.

### Verificar la integridad del OVA

```bash
cd "/home/armintec/Documentos/MICRO-TIK/CONFIGURACIÓN Y COMERCIALIZACIÓN DE INTERNET CON STARLINK Y UBIQUITI"

mkdir -p /tmp/ova-chr && cd /tmp/ova-chr
tar -xf "/home/armintec/Documentos/MICRO-TIK/CONFIGURACIÓN Y COMERCIALIZACIÓN DE INTERNET CON STARLINK Y UBIQUITI/chr-7.24.1.ova"

sha256sum -c chr-7.24.1.mf
```

Salida esperada:

```
chr-7.24.1.ovf: OK
chr-7.24.1-disk1.vmdk: OK
```

---

## 4. Método A — VMware Workstation / Player

### 4.1 Importar el OVA

**Workstation Pro:**

1. `File → Open…` → selecciona `chr-7.24.1.ova` → `Open`.
2. Aparece el asistente **"Import Virtual Machine"**. Revisa:
   - *Storage*: destino del disco (deja el de por defecto).
   - *Network*: `VM Network` → déjala en **NAT** por ahora (la cambiarás después).
   - Acepta la licencia → `Finish`.

**Player:**

1. `Player → File → Open…` → `chr-7.24.1.ova`.
2. Player importa y crea la VM. El asistente de red no aparece: la configuras después a mano.

### 4.2 Ajustar la máquina virtual

`VM → Settings`:

| Ajuste | Valor recomendado | Por qué |
|---|---|---|
| Memory | **1024 MB** (mínimo) | RouterOS va sobrado con 256 MB; 1 GB es el valor del OVA |
| Processors | **2** | El CHR no usa más de 1, pero 2 da margen con QEMU anidado |
| Hard disk | **Expand** si quieres más espacio | 128 MB es suficiente para el laboratorio |
| Network Adapter 1 | **NAT** | salida a Internet + gestión |
| Network Adapter 2 | *(añadir)* → **Custom: vmnet1** o **Bridged** | LAN del hotspot |

Añadir la segunda NIC: `Add… → Network Adapter → NAT / Bridged / Host-only`.

> 💡 VMware Workstation Player **no tiene** editor de red. Si necesitas tocar `vmnet1`/`vmnet8`,
> necesitas Workstation Pro o editar los archivos de configuración a mano (§4.4).

### 4.3 La red en VMware

VMware crea tres redes virtuales:

| Red | Para qué | Gateway por defecto |
|---|---|---|
| **vmnet0** | *Bridged* — se conecta a tu LAN física | la IP de tu router |
| **vmnet1** | *Host-only* — red aislada host ↔ VMs | 192.168.50.1 |
| **vmnet8** | *NAT* — salida a Internet con masquerade | 192.168.x.1 (configurable) |

El equivalente exacto de tu `br-mikrotik` es **`vmnet1`**.

**Para cambiar la IP de `vmnet1`** (por ejemplo a 192.168.77.1/24, igual que el laboratorio):

1. `Edit → Virtual Network Editor` (necesita permisos root).
2. Pestaña **Host-only** → selecciona `VMnet1` → `Change Settings` → **NAT Settings / IP Address**.
3. Pon `192.168.77.1` con máscara `255.255.255.0`.
4. `Apply`.

### 4.4 Reenvío de puertos (el `hostfwd` de QEMU)

**Workstation Pro (GUI):**

1. `Edit → Virtual Network Editor`.
2. Pestaña **NAT** → `NAT Settings…` → pestaña **Port Forwarding**.
3. Añade dos filas:

| Protocol | Host IP | Host Port | Virtual IP | Virtual Port | Descripción |
|---|---|---|---|---|---|
| TCP | `127.0.0.1` | `2222` | *(vacío)* | `22` | SSH |
| TCP | `127.0.0.1` | `8291` | *(vacío)* | `8291` | WinBox |

4. `Apply`.

**Player o sin GUI — edita `nat.conf`:**

```bash
sudo vim /etc/vmware/vmnet8/nat/nat.conf
```

Añade al final:

```ini
[incomingtcp]
2222 = 127.0.0.1:22
8291 = 127.0.0.1:8291
```

Y reinicia el servicio de VMware:

```bash
sudo systemctl restart vmware   # o: sudo /etc/init.d/vmware restart
```

### 4.5 Configurar la segunda NIC por CLI (alternativa a la GUI)

Si prefieres no tocar la GUI de VMware:

```bash
# Localiza el .vmx de la VM
find ~/vmware -name "*.vmx" 2>/dev/null

# Añade una segunda NIC (VmxNet3, red vmnet1)
sudo vim /ruta/a/MikroTik_RouterOS_CHR.vmx
```

Añade al final:

```ini
ethernet1.present = "TRUE"
ethernet1.virtualDev = "vmxnet3"
ethernet1.connectionType = "custom"
ethernet1.vnet = "VMnet1"
ethernet1.addressType = "generated"
```

### 4.6 Encender y comprobar

```bash
# Encender (desde la GUI también vale)
vmrun start ~/vmware/MikroTik_RouterOS_CHR.vmx nogui

# Ver las VMs
vmrun list
```

Consola de la VM: `Player → Console` o `VM → Open Console`.

---

## 5. Método B — Oracle VirtualBox

### 5.1 Importar el OVA

1. `File → Import Appliance…`
2. `Local drive System` → `Select the OVA file…` → `chr-7.24.1.ova`.
3. Revisa el asistente:
   - *Appliance settings*: **Virtual Machine Name** = `CHR-LAB`, **Memory** = `1024`,
     **CPUs** = `2`.
   - *Disk*: marca `chr-7.24.1-disk1.vmdk` → *Storage format*: **VDI** (recomendado) o
     *Keep the disk image as VMDK*.
   - *Network*: deja la red 1 en **NAT**.
4. `Import`.

> ⚠️ Si VirtualBox protesta con el `.ovf`, comprueba que el `.mf` y el `.vmdk` están en la
> **misma carpeta** que el `.ova` y que los checksums cuadran (§3).

### 5.2 Alternativa: crear la VM a mano con la imagen VDI

Si prefieres la imagen `.vdi` oficial (más rápida que importar el OVA):

1. Descarga `chr-<ver>.vdi.zip` de <https://mikrotik.com/download/chr> y descomprímelo.
2. `File → New → Virtual Machine`:
   - Tipo: **Other** / `Other/Unknown` (64-bit).
   - Memoria: **1024 MB**.
   - Disco: `Use an existing virtual disk file` → `chr-<ver>.vdi`.
   - otros: omitir (skip).
3. `Settings → Network`:
   - **Adaptador 1** → `Cable conectado` ✓, **NAT**.
   - **Adaptador 2** → `Cable conectado` ✓, **Host-only** o **Bridged**.
4. `Settings → System → Motherboard`: **desmarca** `Boot from floppy` y marca `Boot from Hard Disk`.
5. `Settings → System → Processor`: **2** CPUs.

### 5.3 Tipo de adaptador de red

VirtualBox ofrece varios. Para CHR:

| Tipo | Valor | Nota |
|---|---|---|
| **Paravirtualized Network (virtio-net)** | `VirtIO-Net` | **Recomendado.** Requiere drivers virtio en el guest; RouterOS 7 los trae. |
| **Intel PRO/1000 MT Desktop (82540EM)** | `Intel PRO/1000 MT Desktop (82540EM)` | **Máxima compatibilidad.** Si algo falla, usa este. |
| AMD PCNet | `PCNet-FAST III` | El más compatible, el más lento. Funciona. |

> 💡 En VirtualBox 7.x, **VirtIO-Net está disponible sin Extension Pack**. Si tu versión
> antigua no lo ofrece, `Intel PRO/1000` es la opción segura.

### 5.4 La red en VirtualBox

| Modo | Qué hace | Cuándo usarlo |
|---|---|---|
| **NAT** | Sale a Internet con la IP del host. Aísla la VM de la LAN. | Adaptador 1 (salida a Internet) |
| **Host-only** | Red L2 aislada entre host y VMs, **sin** salida a Internet. | Adaptador 2 (LAN del hotspot) |
| **Bridged** | La VM aparece en tu LAN física como un equipo más. | Si quieres que el CHR sea visible en la red real |

**Adaptador 2 en Host-only.** El adaptador host-only por defecto se llama `vboxnet0` con IP
`192.168.56.1/24`. Comprueba el nombre real en tu máquina:

```bash
VBoxManage list hostonlyifs
ip -br addr show | grep vbox
```

Para crearlo o cambiarle la IP (por ejemplo a `192.168.77.1/24`, igual que el laboratorio):

```bash
# Ver los host-only existentes
VBoxManage list hostonlyifs

# Crear uno nuevo (si no existe)
VBoxManage hostonlyif create
VBoxManage hostonlyif ipaddress vboxnet0 192.168.77.1
VBoxManage hostonlyif netmask vboxnet0 255.255.255.0
```

Si el nombre no es `vboxnet0`, sustitúyelo por el que te dé `VBoxManage list hostonlyifs`.

> ⚠️ **Conflicto de subredes:** si tu red física es `192.168.77.0/24` (p. ej. la del AP
> `hostapd`), el host-only de VirtualBox **no puede usar la misma subred**. Elige otra
> (p. ej. `192.168.88.1/24` para el host-only y deja `192.168.77.0/24` para la red del AP).

### 5.5 Reenvío de puertos (el `hostfwd` de QEMU)

**GUI:** `Settings → Network → Advanced → Port Forwarding → `+`*

| Name | Protocol | Host IP | Host Port | Guest IP | Guest Port |
|---|---|---|---|---|---|
| `ssh` | TCP | `127.0.0.1` | `2222` | *(vacío)* | `22` |
| `winbox` | TCP | `127.0.0.1` | `8291` | *(vacío)* | `8291` |

**CLI (equivalente exacto):**

```bash
VBoxManage modifyvm "CHR-LAB" \
  --natpf1 "ssh,tcp,127.0.0.1,2222,,22" \
  --natpf1 "winbox,tcp,127.0.0.1,8291,,8291"

# Ver las reglas
VBoxManage showvminfo "CHR-LAB" | grep -i natpf
```

> 💡 El formato es `nombre,protocolo,ip_host,puerto_host,ip_guest,puerto_guest`.
> Con `ip_host` vacío, VirtualBox escucha en todas las interfaces; con `127.0.0.1` solo en
> local, que es lo seguro para un laboratorio.

### 5.6 Encender y comprobar

```bash
VBoxManage list vms
VBoxManage startvm "CHR-LAB" --type headless
VBoxManage showvminfo "CHR-LAB" | grep -E "State|nic[0-9]"
```

Abrir la consola: `VBoxManage startvm "CHR-LAB"` (con ventana) o `Ctrl+Alt+2` para la
consola serial dentro de la VM.

---

## 6. Conversión de la imagen que ya tienes

Si ya tienes el disco del laboratorio en `qcow2` o el `.img` crudo de MikroTik y quieres
reutilizarlo (con su configuración ya guardada), conviértelo con `qemu-img`:

```bash
# A disco VMware (monolítico, para Workstation local)
qemu-img convert -f qcow2 -O vmdk chr-lab.qcow2 chr-lab.vmdk

# A disco VMware optimizado para ESXi
qemu-img convert -f qcow2 -O vmdk -o subformat=streamOptimized chr-lab.qcow2 chr-lab-esxi.vmdk

# A disco VirtualBox
qemu-img convert -f qcow2 -O vdi chr-lab.qcow2 chr-lab.vdi

# A disco Hyper-V
qemu-img convert -f qcow2 -O vhdx chr-lab.qcow2 chr-lab.vhdx

# A disco RAW (el formato oficial de MikroTik)
qemu-img convert -f qcow2 -O raw chr-lab.qcow2 chr-lab.img
```

### Consideraciones importantes al convertir

| Tema | Detalle |
|---|---|
| **Orden de la NIC** | El CHR ve las interfaces **en orden de presentación**. Si en QEMU la 1ª era la NAT y la 2ª el tap, **mantén ese orden** en VMware/VirtualBox o la config se invierte. |
| **MAC addresses** | `qemu-img` no las toca, pero VMware/VirtualBox pueden regenerarlas. Si el CHR tiene reglas ligando a MAC, ajústalas o fija la MAC en la configuración de la VM. |
| **Compresión** | `qcow2` comprimido se convierte a un disco **más grande** que el original. Es normal. |
| **Espacio** | Reserva ~2× el tamaño del origen durante la conversión. |
| **Integridad** | Comprueba con `qemu-img check chr-lab.vmdk` antes de usarlo. |

### Fijar la dirección MAC (para que la config no se rompa)

```bash
# VirtualBox
VBoxManage modifyvm "CHR-LAB" --macaddress1 08:55:31:AA:BB:01 --macaddress2 08:55:31:AA:BB:02

# VMware: editar el .vmx
#   ethernet0.addressType = "static"
#   ethernet0.address      = "00:50:56:AA:BB:01"
```

Y en el CHR, comprueba cómo las ve:

```routeros
/interface ethernet print
```

---

## 7. Los dos modelos de red

Elige **uno** de los dos. No los mezcles.

### Modelo 1 — El puente del host (fiel a tu laboratorio QEMU)

```
   ┌─────────────┐   tap/bridge   ┌──────────────┐
   │  CHR (VM)   │◀──────────────▶│ br-mikrotik  │◀── wlp59s0 (hostapd, SSID)
   │  ether2     │                │ 192.168.77.1 │    (movido a este puente)
   └─────────────┘                └──────────────┘
```

- El puente `br-mikrotik` **ya existe** en tu host (creado por `scripts/iniciar-lab.sh`).
- La NIC 2 de la VM se conecta a ese puente:
  - **VirtualBox:** `Settings → Network → Adaptador 2 → Bridged → "Bridged to: br-mikrotik"`.
  - **VMware:** `Adaptador 2 → Custom: vmnet1` y luego se añade la interfaz al puente; o
    `Bridged` y en el Virtual Network Editor se selecciona `br-mikrotik`.
- El AP `hostapd` **también** se enchufa a `br-mikrotik`.

**Ventaja:** la configuración del CHR (`192.168.77.254`) es **idéntica** a la de QEMU.
**Inconveniente:** el puente del host no tiene salida a Internet por sí mismo (da igual:
la salida la da la NIC 1 en NAT).

### Modelo 2 — Todo dentro del hipervisor

```
   ┌─────────────┐                    ┌──────────────┐
   │  CHR (VM)   │◀── vmnet1/vboxnet0 ─┤ host-only    │◀── wlp59s0 (hostapd)
   │  ether2     │                    │ red aislada  │
   └─────────────┘                    └──────────────┘
```

- La NIC 2 va a **Host-only** (`vmnet1` / `vboxnet0`).
- El AP `hostapd` se **enchufa** a ese mismo puente virtual (§9).
- La IP del hotspot cambia a la subred del host-only (p. ej. `192.168.50.254`).

**Ventaja:** no tocas nada del host; todo el laboratorio vive dentro del hipervisor.
**Inconveniente:** hay que cambiar la IP del hotspot, el pool DHCP y el NAT en el CHR.

### Qué cambia dentro del CHR en cada modelo

| Parámetro | Modelo 1 (puente del host) | Modelo 2 (host-only) |
|---|---|---|
| `hotspot-address` | `192.168.77.254` (sin cambios) | `192.168.50.254` (o la que uses) |
| `/ip address` en ether2 | `192.168.77.254/24` | `192.168.50.254/24` |
| `/ip pool` | `192.168.77.100-192.168.77.199` | `192.168.50.100-192.168.50.199` |
| `/ip dhcp-server network` | `192.168.77.0/24` | `192.168.50.0/24` |
| Regla NAT `src-address` | `192.168.77.0/24` | `192.168.50.0/24` |

---

## 8. Reconfigurar el CHR dentro de la VM

Al arrancar un CHR **recién instalado** (no el del laboratorio), hay que configurarlo desde
cero. Estos son los **cuatro bloques** mínimos.

> 💡 Si vienes del laboratorio QEMU y solo cambias de hipervisor, **no toques nada**: la
> configuración ya está guardada en el disco. Solo verifica que el orden de las NIC sea el
> mismo (ether1 = NAT, ether2 = LAN).

### 8.1 Cambiar la clave de admin

```routeros
/user set admin password="UnaClaveFuerteAqui"
```

> ⚠️ En un CHR recién instalado la clave de `admin` suele estar **vacía**. Cámbiala
> **antes** de exponer la VM a cualquier red.

### 8.2 Identidad, hora y DNS

```routeros
/system identity set name=MICRO-DEV-ROOT
/system clock set time-of-day=12:00:00
/system ntp client set enabled=yes primary-ntp=pool.ntp.org
/ip dns set servers=1.1.1.1,8.8.8.8 allow-remote-requests=yes
```

### 8.3 WAN (ether1) por DHCP

```routeros
/ip dhcp-client add interface=ether1 name=wan1 disabled=no
/ip address print
```

Verifica que `ether1` ha cogido IP. En VMware/VirtualBox el NAT del hipervisor le da una
IP privada (típicamente `10.0.2.15` en QEMU SLIRP, `192.168.x.y` en VMware/VirtualBox).

### 8.4 LAN + hotspot (ether2)

```routeros
/ip address add address=192.168.77.254/24 interface=ether2 comment="LAN HOTSPOT"

/ip pool add name=pool-lan ranges=192.168.77.100-192.168.77.199

/ip dhcp-server network add \
  address=192.168.77.0/24 \
  gateway=192.168.77.254 \
  dns-server=1.1.1.1,8.8.8.8

/ip dhcp-server add \
  name=dhcp-lan interface=ether2 address-pool=pool-lan lease-time=1h disabled=no

/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade comment="NAT salida"
/ip firewall nat add chain=srcnat src-address=192.168.77.0/24 action=masquerade comment="NAT hotspot"

/ip hotspot profile add name=hsprof1 hotspot-address=192.168.77.254 dns-name="" html-directory=hotspot

/ip hotspot add \
  name=hotspot1 interface=ether2 address-pool=pool-lan profile=hsprof1 \
  idle-timeout=5m login-timeout=2m keepalive-timeout=30s disabled=no

/ip hotspot user profile add \
  name=perfil-gratis shared-users=1 session-timeout=1h idle-timeout=10m \
  keepalive-timeout=30s mac-cookie-timeout=1d rate-limit=512k/2M

/ip hotspot user add name=cliente password=cliente123 profile=perfil-gratis
```

### 8.5 Verificar que las NIC están en el orden correcto

```routeros
/interface ethernet print
/interface ethernet monitor ether1 once
/interface ethernet monitor ether2 once
```

Lo que **debe** cumplirse:

- `ether1` = la que tiene la IP del NAT (salida a Internet).
- `ether2` = la que tiene `192.168.77.254/24` (LAN del hotspot).

Si están al revés, intercambia los cables virtuales en el hipervisor (o los adaptadores de
la VM). **No cambies la configuración del CHR** para compensar: es más fácil confundirlo después.

---

## 9. Conectar el AP de hostapd

El AP emite el SSID. Para que los clientes lleguen al CHR, la interfaz WiFi del host debe
estar en **el mismo puente L2** que la NIC 2 de la VM.

### 9.1 En el Modelo 1 (puente `br-mikrotik`)

Es exactamente lo que ya hace `scripts/iniciar-lab.sh`:

```bash
# El hostapd corre sobre esta interfaz
sudo ip link set wlp59s0 master br-mikrotik
sudo ip link set wlp59s0 up

# Y la VM (ether2) se enchufa al mismo puente
#   VirtualBox: Adaptador 2 → Bridged → br-mikrotik
#   VMware:     Adaptador 2 → Custom → vmnet1 (y se añade la iface al puente)
```

Comprueba:

```bash
ip link show master br-mikrotik
bridge link show
```

Deben aparecer la interfaz WiFi **y** la NIC 2 de la VM.

### 9.2 En el Modelo 2 (red host-only del hipervisor)

```bash
# VMware: vmnet1 (192.168.50.1/24 por defecto)
sudo ip link set wlp59s0 master vmnet1
sudo ip link set wlp59s0 up

# VirtualBox: vboxnet0 (192.168.56.1/24 por defecto)
sudo ip link set wlp59s0 master vboxnet0
sudo ip link set wlp59s0 up
```

Comprueba:

```bash
ip link show master vmnet1     # o vboxnet0
ip -br addr show vmnet1        # o vboxnet0
```

> ⚠️ **El nombre del puente no es fijo.** Descúbrelo con:
> ```bash
> ip -br addr show | grep -E 'vmnet|vbox'
> VBoxManage list hostonlyifs
> ```
>
> ⚠️ **Si VirtualBox/VMware gestionan el puente con su propio servicio**, al reiniciar el
> host la interfaz WiFi puede quedar fuera. Hazlo persistente con NetworkManager:
> ```bash
> sudo nmcli connection add type bridge-slave \
>   con-name wlp59s0-master con-name wlp59s0 master vmnet0 \
>   connection.autoconnect yes
> ```
> (sustituye `vmnet0`/`vboxnet0` por el nombre real).

### 9.3 Lanzar hostapd

```bash
sudo hostapd -B /etc/hostapd/mikrotik-lab.conf
sudo hostapd_cli -i wlp59s0 status
```

El SSID debe ser visible:

```bash
iw dev wlp59s0 info | grep -E 'ssid|type|channel'
```

### 9.4 Probar la conexión desde el CHR

```routeros
/ping 192.168.77.1 count=4        # el puente del host
/ping 192.168.77.254 count=4      # la propia IP del hotspot
/ip arp print                    # ¿aparecen los clientes?
```

---

## 10. Rendimiento: qué esperar

| Hipervisor | Overhead de red | Overhead de CPU | Notas |
|---|---|---|---|
| **QEMU/KVM** (actual) | Bajo | Bajo | Acceso directo a KVM. |
| **VMware Workstation** | Medio | Medio | VmxNet3, buen rendimiento con NAT. |
| **VirtualBox** | Medio-alto | Medio | VirtIO-Net reduce bastante el coste. |
| **VirtualBox + Intel PRO/1000** | Alto | Alto | Emulación completa. Última opción. |

> 📌 **El cuello de botella real no es el hipervisor.** Sin licencia CHR el límite es
> **1 Mbps de subida por interfaz**, muy por debajo de cualquier overhead de virtualización.
> Con licencia P1 el límite sube a 1 Gbps y entonces sí se nota la diferencia entre
> hipervisores.
>
> Ver [doc 04 §12](./04-MIKROTIK-FISICO.md) para el rendimiento del hardware real.

---

## 11. Troubleshooting

| Síntoma | Causa | Solución |
|---|---|---|
| `ssh -p 2222` no responde | No hay reenvío de puertos | Revisa §4.4 / §5.5 y reinicia el servicio de red del hipervisor |
| WinBox no abre en `127.0.0.1:8291` | Idem | `ss -tlnp | grep 8291` en el host |
| La VM no tiene IP en ether1 | El adaptador no está en NAT | `Settings → Network → Adaptador 1 → NAT` |
| El cliente coge IP pero no navega | El AP y la NIC 2 no comparten puente | `ip link show master <puente>`: deben aparecer las dos |
| El cliente no coge IP | El AP está en un puente distinto al de la VM | Compara `bridge link show` con la red de la VM |
| La VM no arranca tras importar | Disco streamOptimized no soportado | Convierte a `-O vmdk` (sin `subformat`) o usa la imagen `.vdi`/`.img` oficial |
| VirtualBox: "network not found" | La red `vboxnet0` no existe | `VBoxManage hostonlyif create` y crea la red en la GUI |
| VMware: "no host-only adapter" | `vmnet1` deshabilitado | Virtual Network Editor → Host-only → `Change Settings` → marca el adaptador |
| Las interfaces salen invertidas | Orden de presentación distinto | Reordena los adaptadores en la VM, no la config del CHR |
| `Operation not permitted` al crear el tap | Faltan permisos | `sudo` + `CAP_NET_ADMIN` (§11 del doc 00) |
| El CHR arranca pero sin RouterOS | Disco vacío o mal convertido | `qemu-img check` y vuelve a convertir |

---

## 12. Checklist final

### VMware

- [ ] OVA importado y la VM arranca (consola muestra `RouterOS`).
- [ ] 1024 MB de RAM, 2 CPUs.
- [ ] Adaptador 1 = **NAT**; Adaptador 2 = **Host-only** o **Bridged**.
- [ ] Reenvío de puertos 2222 → 22 y 8291 → 8291 configurado.
- [ ] `ssh -p 2222 admin@127.0.0.1` responde.
- [ ] WinBox en `127.0.0.1:8291` responde.
- [ ] `ether1` = NAT, `ether2` = LAN del hotspot.
- [ ] AP `hostapd` en el mismo puente que la NIC 2.
- [ ] El celular recibe IP del pool del hotspot y ve el portal.

### VirtualBox

- [ ] Appliance importada (o VM creada con la `.vdi`).
- [ ] 1024 MB de RAM, 2 CPUs, orden de arranque = disco duro.
- [ ] Adaptador 1 = **NAT**; Adaptador 2 = **Host-only** o **Bridged**.
- [ ] Tipo de NIC = `VirtIO-Net` (o `Intel PRO/1000`).
- [ ] Reglas `--natpf1` para 2222 y 8291.
- [ ] `ssh -p 2222 admin@127.0.0.1` responde.
- [ ] WinBox en `127.0.0.1:8291` responde.
- [ ] `ether1` = NAT, `ether2` = LAN del hotspot.
- [ ] AP `hostapd` en el mismo puente que la NIC 2.
- [ ] El celular recibe IP del pool del hotspot y ve el portal.

### Comprobación final dentro del CHR

```routeros
/interface ethernet print
/ip address print
/ip dhcp-server lease print
/ip hotspot active print
/ping 1.1.1.1 count=4
```

---

## Documentos relacionados

| Documento | Cuándo leerlo |
|---|---|
| [`00-ENTORNO-Y-PREPARACION.md`](./00-ENTORNO-Y-PREPARACION.md) | El laboratorio base en QEMU: bridge, tap, hostapd. |
| [`01-COMANDOS-MIKROTIK.md`](./01-COMANDOS-MIKROTIK.md) | Todos los comandos del hotspot y la red. |
| [`02-COMANDOS-ESENCIALES-MIKROTIK.md`](./02-COMANDOS-ESENCIALES-MIKROTIK.md) | El mínimo imprescindible de RouterOS. |
| **Este** | Si quieres el CHR en VMware o VirtualBox. |
| [`04-MIKROTIK-FISICO.md`](./04-MIKROTIK-FISICO.md) | Si vas a montar esto en un router real. |
