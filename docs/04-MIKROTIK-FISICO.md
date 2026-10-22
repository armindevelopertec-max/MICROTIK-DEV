# MikroTik Físico — del laboratorio CHR al router real

> **Este es el quinto documento.** Cómo llevar el laboratorio de **hotspot CHR** a un
> **RouterBOARD real**: qué cambia, cómo se enciende por primera vez, cómo se configura la
> radio WiFi de verdad y cómo se migra la configuración que ya tienes.
> El entorno virtual está en → [`00-ENTORNO-Y-PREPARACION.md`](./00-ENTORNO-Y-PREPARACION.md)

**Versión de referencia:** RouterOS 7.24.x (RouterBOARD) · CHR 7.24.5 como referencia
**Sintaxis verificada contra:** MikroTik CLI Reference oficial, rama `7.24` (`/interface/wifi`,
`/interface/bridge/port`, `/caps-man`)

---

## Índice

1. [Para qué sirve este documento](#1-para-qué-sirve-este-documento)
2. [CHR vs hardware: qué cambia de verdad](#2-chr-vs-hardware-qué-cambia-de-verdad)
3. [Elegir el equipo](#3-elegir-el-equipo)
4. [Primer contacto con el router](#4-primer-contacto-con-el-router)
5. [Configuración mínima de un router nuevo](#5-configuración-mínima-de-un-router-nuevo)
6. [Actualizar RouterOS y paquetes](#6-actualizar-routeros-y-paquetes)
7. [Interfaces en hardware: bridge y switch por hardware](#7-interfaces-en-hardware-bridge-y-switch-por-hardware)
8. [WiFi real: `/interface wifi` vs `/interface wireless`](#8-wifi-real-interface-wifi-vs-interface-wireless)
9. [Hotspot sobre la radio real](#9-hotspot-sobre-la-radio-real)
10. [CAPsMAN: un AP, muchos SSID, muchos clientes](#10-capsman-un-ap-muchos-ssid-muchos-clientes)
11. [WAN: PPPoE, DHCP y Starlink](#11-wan-pppoe-dhcp-y-starlink)
12. [Licencias y límites](#12-licencias-y-límites)
13. [Rendimiento real vs CHR](#13-rendimiento-real-vs-chr)
14. [Migrar la configuración del CHR al hardware](#14-migrar-la-configuración-del-chr-al-hardware)
15. [Diagnóstico en hardware](#15-diagnóstico-en-hardware)
16. [Seguridad y hardening](#16-seguridad-y-hardening)
17. [Mantenimiento: backup, netinstall y reset](#17-mantenimiento-backup-netinstall-y-reset)
18. [Checklist final](#18-checklist-final)

---

## 1. Para qué sirve este documento

El laboratorio del CHR te ha permitido **aprender RouterOS sin miedo**: puedes romper cosas,
reiniciar el CHR y empezar de cero en 30 segundos. Eso es oro para aprender.

Pero el CHR tiene tres limitaciones que **no** existen en un router real:

| Limitación del CHR | En un RouterBOARD real |
|---|---|
| Sin radio WiFi (el SSID lo pone `hostapd` en tu laptop) | Radio WiFi real, con antenas, MIMO y WPA3 |
| Sin licences → **1 Mbps** por interfaz | Sin ese límite artificial |
| Interfaz Ethernet virtual: no hay switch, ni PoE, ni SFP | Switch real con offload por hardware, PoE, puertos SFP |

Este documento es la **puente** entre las dos cosas: qué comandos del CHR siguen siendo
válidos, cuáles hay que cambiar, y cómo se hace la migración.

**No sustituye la documentación oficial** de tu modelo concreto. Antes de tocar nada,
descarga el *Quick Guide* y el *User Manual* de tu RouterBOARD desde
<https://mikrotik.com/download>.

---

## 2. CHR vs hardware: qué cambia de verdad

### 2.1 Tabla comparativa

| Aspecto | CHR (virtual) | RouterBOARD (real) |
|---|---|---|
| **Nombre de interfaces** | `ether1`, `ether2`… (virtuales) | `ether1`, `ether2`… + `sfp-sfpplus1`, `wifi1`, `wifi2`… |
| **Orden de presentación** | Lo decide QEMU/VMware/VirtualBox | Fijo por hardware (`ether1` = WAN por defecto) |
| **Switch interno** | No existe | Existe, con **offload por hardware** (`hw=yes`) |
| **PoE** | No | Según modelo (`poe-out`, `poe-in`, PoE+ en puertos) |
| **Radio WiFi** | No | Según modelo: 2.4 GHz, 5 GHz, 6 GHz, 60 GHz |
| **Almacenamiento** | Disco `.qcow2` / `.img` | Flash NAND + memoria (archivos ~ en `flash`) |
| **Reinicio** | Apagar/encender la VM | `reboot` de 5-15 s, o botón de reset |
| **Reset de fábrica** | `system reset-configuration` | `system reset-configuration` **o** botón de reset |
| **Pérdida de config** | Se pierde el `.qcow2` | Se puede perder: **haz backups** |
| **Licencia** | CHR: free/P1/P10/P-Unlimited | RouterOS completo incluido, **sin límite de velocidad** |
| **Consola** | Terminal + monitor | **Puerto serie** (RJ45 o USB) — vital si te quedas sin red |
| **Alimentación** | N/A | Fuente + PoE; corte de luz = apagado |
| **Temperatura** | N/A | Monitoriza `/system resource` y `/sensor` |

### 2.2 Lo que **NO** cambia

- Toda la sintaxis de RouterOS.
- Todo el menú `/ip hotspot` (servidor, perfiles, usuarios, walled-garden, ip-binding).
- `/ip firewall`, `/ip dhcp-server`, `/queue simple`, `/ip dns`.
- Los timeouts, las cookies, los scripts on-login/on-logout.
- El flujo de trabajo: **entorno → comandos → verificación**.

> 🔑 **En resumen:** el 90% de lo que aprendiste en el CHR se aplica tal cual. Lo que cambia
> son los **interfaces** (ahora hay radio), el **offload** (hay que activarlo) y la
> **persistencia** (hay que guardar).

---

## 3. Elegir el equipo

### 3.1 Criterios para este proyecto

Para montar un portal cautivo real necesitas:

1. **Radio WiFi** si quieres que el router emita el SSID (o usa un AP externo).
2. **Rendimiento** suficiente para el número de clientes simultáneos.
3. **PoE** si vas a alimentar un AP externo desde el router.
4. **Licencia RouterOS completa**: todos los.RouterBOARD la incluyen de serie.

### 3.2 Modelos habituales para un portal cautivo

| Modelo | Radio | Puertos | Ideal para |
|---|---|---|---|
| **hAP ax²** (C52iG-5HaxD2HaxD) | WiFi 6, 2.4 + 5 GHz | 5× GbE, 1× PoE | Laboratorio doméstico, 10-20 clientes |
| **hAP ax³** (RB53iG) | WiFi 6, 2.4 + 5 GHz | 5× GbE | Similar, más CPU |
| **hAP ac²** (RBC50i-7HacS2HnD) | WiFi 5, 2.4 + 5 GHz | 5× GbE, 1× PoE | Opción barata; admite paquete `wifi-qcom-ac` |
| **hAP ac³** | WiFi 5, 2.4 + 5 GHz | 5× GbE | Similar |
| **RB5009UG+S+** | **Sin radio** | 1× SFP+, 7× 1G, 1× 2.5G | Router de potencia + AP externo |
| **CCR2004-1G-12S+2XS** | **Sin radio** | 12× SFP, 2× SFP+ | Ofensivo, con licences |
| **Audience / hAP ax S** | WiFi 6 | 2× GbE | Portátil |
| **cAP ax** | Solo radio | Solo PoE | **AP puro** para centralizar con CAPsMAN |

> 💡 Si el objetivo es **aprender y hacer pruebas**, el **hAP ax²** es la mejor relación
> calidad/precio: radio WiFi 6, 5 puertos GbE, un puerto PoE y un USB para pruebas.
>
> ⚠️ Si compras un **hAP ac²** (WiFi 5), decide **antes** qué paquete de drivers vas a
> usar, porque `/interface wireless` y `/interface wifi` **no son compatibles** entre sí
> (ver §8).

### 3.3 Radio exterior (para el proyecto Starlink /ubiQUITI)

Si el router va fuera o quieres cobertura amplia:

- **cAP ac / cAP ax**: AP de exterior con PoE, se-centralizan con CAPsMAN.
- **RB5009 + PoE**: router sin radio que alimenta el AP exterior.
- Antenas: **panel** para sector/frontal, **omni** para 360°, **Yagi** para punto a punto.

---

## 4. Primer contacto con el router

### 4.1 Lo que hay en la caja

- RouterBOARD.
- Fuente de alimentación (o PoE).
- Antenas (si tiene radio).
- Manual rápido con la **dirección MAC** y la **clave por defecto**.

### 4.2 Conectarse por primera vez

```
   ┌────────────────┐
   │   RouterBOARD  │
   │                │
   │  ether1  ← WAN (conecta el cable del ISP aquí)   ⚠️ firewalled por defecto
   │  ether2  ← LAN (conecta tu PC aquí)              ✓ abierto
   │  ether3..N
   │  wifi1/2 ← radio (SSID "MikroTik-XXXXXX")
   └────────────────┘
```

1. Conecta el **cable del ISP a `ether1`**.
2. Conecta tu **PC a `ether2`** (o al SSID `MikroTik-XXXXXX` de fábrica).
3. Abre **WinBox** (<https://mt.lv/winbox>) → pestaña **Neighbors** → aparece tu router.
4. Conéctate por **dirección MAC** (funciona aunque la IP no sea la esperada).
5. Usuario `admin`, contraseña **vacía** o **la del sticker** (depende del modelo y de si
   se ha usado QuickSet).

### 4.3 Los métodos de acceso

| Método | Dirección | Notas |
|---|---|---|
| **WinBox por MAC** | — | Funciona **siempre**, incluso sin IP válida. El más fiable para el primer arranque. |
| **WinBox por IP** | `192.168.88.1` | IP de fábrica por defecto. |
| **WebFig** | `http://192.168.88.1` | Interfaz web completa. Requiere cookies. |
| **SSH** | `192.168.88.1` | Puerto 22. |
| **Consola serie** | Puerto RS-232 / USB | **El salvavidas** si rompes la red. |

> 💡 **Activa el puerto serie antes de tocar nada.** En WinBox:
> `Interfaces → Serial → puerto USB o RS-232`. Es la única salida cuando la configuración
> de red te deja fuera. Para ello necesitas el cable correcto (USB-RS232 o el RJ45
> applet de MikroTik con el cable deMikroTik).

### 4.4 El botón de reset

Todos los RouterBOARD tienen un botón RESET:

| Pulsación | Efecto |
|---|---|
| **5 s** | Reinicia el equipo (como `reboot`) |
| **10 s** | Reinicia y **restablece la configuración a fábrica** (IP 192.168.88.1) |
| **20 s** | Restablece y **reinstala RouterOS** por red (netinstall) |

> ⚠️ A los 10-15 s el LED `usr` parpadea. **Suelta antes** si solo querías reiniciar.

---

## 5. Configuración mínima de un router nuevo

Este es el bloque de arranque. Sustituye la config de fábrica.

### 5.1 Cambiar la clave de admin (primero de todo)

```routeros
/user set admin password="UnaClaveFuerteCon12OMasCaracteres"
```

### 5.2 Identidad, hora y DNS

```routeros
/system identity set name=MICRO-LAB
/system clock set time-of-day=12:00:00
/system ntp client set enabled=yes
/system ntp client servers add address=pool.ntp.org
/system ntp client set primary-ntp=pool.ntp.org

/ip dns set servers=1.1.1.1,8.8.8.8 allow-remote-requests=yes
```

### 5.3 Interface lists (buena práctica de MikroTik)

Antes de tocar el firewall, define las listas. Facilita todo lo demás:

```routeros
/interface list add name=WAN
/interface list add name=LAN
/interface list member add list=WAN interface=ether1
/interface list member add list=LAN interface=ether2
/interface list member add list=LAN interface=ether3
/interface list member add list=LAN interface=bridge1
```

### 5.4 WAN por DHCP (o PPPoE, ver §11)

```routeros
/ip dhcp-client add interface=ether1 name=wan1 disabled=no
```

Verifica:

```routeros
/ip address print where interface=ether1
/ip route print where dst-address=0.0.0.0/0
```

### 5.5 LAN con bridge y offload por hardware

```routeros
/interface bridge add name=bridge1
/interface bridge port add bridge=bridge1 interface=ether2 hw=yes
/interface bridge port add bridge=bridge1 interface=ether3 hw=yes
/interface bridge settings set allow-fast-path=yes

/ip address add address=192.168.77.254/24 interface=bridge1 comment="LAN HOTSPOT"
```

### 5.6 DHCP y NAT

```routeros
/ip pool add name=pool-lan ranges=192.168.77.100-192.168.77.199

/ip dhcp-server network add \
  address=192.168.77.0/24 \
  gateway=192.168.77.254 \
  dns-server=1.1.1.1,8.8.8.8

/ip dhcp-server add \
  name=dhcp-lan interface=bridge1 address-pool=pool-lan lease-time=1h disabled=no

/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade comment="NAT salida"
/ip firewall nat add chain=srcnat src-address=192.168.77.0/24 action=masquerade comment="NAT hotspot"
```

### 5.7 Firewall mínimo

En un router **nuevo** MikroTik no trae reglas de firewall por defecto (salvo algunos
modelos). Sin una regla `accept` te quedas sin gestión:

```routeros
/ip firewall filter add chain=input action=accept connection-state=established,related comment="Acepta establecido"
/ip firewall filter add chain=input action=drop connection-state=invalid comment="Descarta invalido"
/ip firewall filter add chain=input action=accept in-interface-list=LAN comment="Acepta LAN"
/ip firewall filter add chain=input action=drop in-interface-list=WAN comment="Bloquea WAN"
/ip firewall filter add chain=forward action=drop connection-state=invalid
/ip firewall filter add chain=forward action=accept connection-state=established,related
/ip firewall filter add chain=forward action=drop in-interface-list=WAN
```

> 💡 La regla `accept` en `chain=input` **desde WAN** es la que te deja administered por
> Internet. **No la añadas** salvo que uses WireGuard/IPsec para la gestión remota.

---

## 6. Actualizar RouterOS y paquetes

### 6.1 Desde el propio router

```routeros
/system package update
/system package install
```

Esto descarga de `upgrade.mikrotik.com` los paquetes de tu **versión exacta** y reinicia.
Necesita salida a Internet.

### 6.2 Manualmente

1. Descarga en <https://mikrotik.com/download> el **RouterOS System Package** (`.npk`) de tu
   **misma versión** y la **Extra packages** de la misma versión.
2. Súbelo por WinBox (`Files`) o por SCP:

```bash
scp admin@192.168.88.1:routeros-7.24.x.npk .
scp routeros-7.24.x.npk admin@192.168.88.1:/
scp wifi-qcom-7.24.x.npk admin@192.168.88.1:/
```

3. En el router:

```routeros
/file print
/system package install file-name=routeros-7.24.x.npk
```

> ⚠️ **El paquete debe ser de la misma versión exacta.** Un `.npk` de otra versión se
> rechaza. Y **cambiar de versión no migra automáticamente** los drivers WiFi: si tienes
> `wireless` y quieres `wifi-qcom`, hay que desinstalar uno e instalar el otro (§8).

### 6.3 Antes de actualizar

```routeros
/system backup save name=pre-upgrade
/file print
```

Y **descárgate el backup al PC** (§17). Si el upgrade sale mal, ese archivo es tu salida.

---

## 7. Interfaces en hardware: bridge y switch por hardware

### 7.1 Por qué el `hw=yes` es obligatorio

En un RouterBOARD, los puertos Ethernet están conectados a un **switch chip** dedicado. Si
pones los puertos en un bridge **sin** offload, todo el tráfico pasa por la CPU del
router: bajas el rendimiento de 1 Gbps a ~100-300 Mbps y la CPU se dispara.

```routeros
/interface bridge port print
```

La columna `H` (hw-offload) debe estar a `yes` en los puertos cableados.

```routeros
/interface bridge port set [find interface=ether2] hw=yes
/interface bridge port set [find interface=ether3] hw=yes
```

### 7.2 FastPath

```routeros
/interface bridge settings set allow-fast-path=yes
```

FastPath mueve el procesamiento de tráfico al plano de datos. En routers con CPU potente
(hAP ax³, RB5009, CCR) la diferencia es notable.

### 7.3 Reglas de la casa

| Regla | Motivo |
|---|---|
| **Nunca** uses `master-port` | Obsoleto desde RouterOS 6.41. Usa bridge. |
| Un solo bridge para toda la LAN | Simplifica DHCP, hotspot y firewall. |
| VLANs en el bridge, no en los puertos | `/interface bridge vlan` es el método moderno. |
| No mezcles un puerto con y sin `hw=yes` en el mismo bridge | El bridge cae a modo software. |

### 7.4 VLANs (si los necesitas)

```routeros
/interface bridge vlan add bridge=bridge1 tagged=bridge1,ether2 vlan-ids=10
/interface bridge port set [find interface=ether2] pvid=10 frame-types=admit-only-untagged-and-priority-tagged
```

### 7.5 PoE

```routeros
/interface ethernet print where poe-out=yes     # puertos con PoE
/interface ethernet set [find name=ether5] poe-out=lte+  # o auto
/interface ethernet monitor ether5 once        # ver consumo
```

---

## 8. WiFi real: `/interface wifi` vs `/interface wireless`

### 8.1 Las dos familias

RouterOS 7 tiene **dos sistemas de WiFi** distintos y **no son compatibles** entre sí:

| Menú | Drivers | Equipos | Características |
|---|---|---|---|
| `/interface wireless` | `wireless` (legacy, MikroTik) | 802.11a/b/g/n, WiFi 5 con CPU MIPS | Nstreme, Nv2, station-bridging, VLAN en la config WiFi |
| `/interface wifi` | `wifi-qcom`, `wifi-qcom-be`, `wifi-mediatek`, `wifi-qcom-ac` | WiFi 6/6E/7 y WiFi 5 en CPU ARM | WPA3, OWE, 802.11r/k/v, MU-MIMO, beamforming, DFS |

> 📌 **Regla para decidir:**
> - Router con **ax/be** en el nombre (hAP ax², hAP ax³, cAP ax, hAP be lite…) → **`/interface wifi`**. No hay otra opción.
> - Router **ac** (hAP ac², hAP ac³, cAP ac) con CPU **ARM** → puedes elegir. **`wifi-qcom-ac`** es lo recomendado (WPA3, roaming rápido).
> - Router **ac** con CPU **MIPS** (RB4011, wAP ac, Cube 60Pro ac) → **solo** `/interface wireless`. `wifi-qcom-ac` no es compatible.
> - Todo lo **n** (802.11n) → solo `/interface wireless`.

Comprueba qué tienes:

```routeros
/system package print
/interface print where name~"wifi"
/interface print where name~"wlan"
```

### 8.2 Migrar de `wireless` a `wifi`

**No hay migración automática.** Hay que hacerlo a mano:

```routeros
# 1. Exporta la config actual por si acaso
/interface wireless export file=wireless-config show-sensitive

# 2. Desinstala el paquete legacy
/system package remove wireless
#   o, marcando para desinstalar en el próximo reinicio:
/system package set wireless disabled=yes

# 3. Instala el nuevo (misma versión exacta)
/file print where name~"wifi-qcom"
/system package install file-name=wifi-qcom-7.24.x.npk

# 4. Reinicia
/system reboot

# 5. Reconfigura desde cero con /interface wifi
```

> ⚠️ **Antes de desinstalar `wireless`**, ten en cuenta que `/caps-man` (CAPsMAN legacy)
> depende de él. Si tienes CAPsMAN configurado, planifica la migración también.

### 8.3 Configurar el WiFi nuevo (`/interface wifi`)

El flujo correcto en RouterOS 7.14+ es el **atajo `/interface wifi network`**, que agrupa
SSID, seguridad, datapath y radio en una sola entidad:

```routeros
# Radio (define canal, ancho de banda y potencia)
/interface wifi radio add \
  name=radio1 \
  band=5ghz-ax \
  channel-width=20/40/80mhz-ax \
  installation=indoor \
  country="colombia" \
  tx-power=20

# Red WiFi completa (SSID + seguridad + bridge)
/interface wifi network add \
  name=red-lab \
  ssid="MIKROTIK-LAB" \
  mode=ap \
  security.passphrase="UnaClaveDeWifiLarga123" \
  security.authentication-types=wpa2-psk,wpa3-psk \
  datapath.bridge=bridge1 \
  datapath.vlan-id=10 \
  radio=radio1
```

> ⚠️ **`country` es obligatorio en equipos vendidos en Europa/Latinoamérica.** Sin él, la
> radio arranca con la potencia y los canales restringidos por defecto, y el cliente se
> desconecta a los pocos minutos. **El error más común en WiFi MikroTik.**

Verificar:

```routeros
/interface wifi radio print
/interface wifi network print
/interface wifi print
```

### 8.4 Configurar el WiFi legacy (`/interface wireless`)

Si tu equipo solo admite el sistema antiguo:

```routeros
/interface wireless security-profiles add \
  name=sec1 \
  mode=dynamic-keys \
  authentication-types=wpa2-psk \
  wpa2-pre-shared-key="UnaClaveDeWifiLarga123"

/interface wireless set [find default-name=wlan2] \
  mode=ap-bridge \
  ssid="MIKROTIK-LAB" \
  security-profile=sec1 \
  band=5ghz-a/n/ac \
  channel-width=20/40/80mhz \
  country="colombia" \
  installation=indoor \
  disabled=no
```

### 8.5 Comparación de sintaxis lado a lado

| Concepto | `/interface wireless` | `/interface wifi` |
|---|---|---|
| SSID | `ssid=` en la interfaz | `ssid=` en `/interface wifi network` |
| Modo AP | `mode=ap-bridge` | `mode=ap` |
| Clave WPA2 | `security-profile=` → `wpa2-pre-shared-key` | `security.passphrase=` directo |
| WPA3 | No disponible | `wpa3-psk` |
| VLAN | `vlan-id=` en la interfaz | `datapath.vlan-id=` |
| Canal | `channel-width=` | `channel-width=` en `/interface wifi radio` |
| País | `country=` | `country=` en `/interface wifi radio` |
| En bridge | `master-port=` (legacy) | `datapath.bridge=` |

---

## 9. Hotspot sobre la radio real

Aquí está la diferencia conceptual clave respecto al CHR: **el hotspot se ata a una interfaz,
y esa interfaz debe ser la LAN**. En el CHR era `ether2`. En un RouterBOARD con radio, es el
**bridge** que incluye el puerto cableado **y** la radio.

### 9.1 Topología recomendada

```
   ISP ──▶ ether1 (WAN, firewall)
                │
          ┌─────┴─────┐
          │  bridge1  │  192.168.77.254/24
          └─────┬─────┘
        ┌───────┼────────┐
     ether2  ether3   wifi1 (radio, SSID MIKROTIK-LAB)
     (cable) (cable)     (inalámbrico)
```

### 9.2 Configuración completa

```routeros
# --- Bridge LAN ---
/interface bridge add name=bridge1
/interface bridge port add bridge=bridge1 interface=ether2 hw=yes
/interface bridge port add bridge=bridge1 interface=ether3 hw=yes
/interface bridge settings set allow-fast-path=yes

# --- Radio en el bridge ---
/interface wifi radio add \
  name=radio1 band=2.4ghz-ax channel-width=20mhz-ax \
  installation=indoor country="colombia"

/interface wifi network add \
  name=red-hotspot \
  ssid="MIKROTIK-LAB" \
  mode=ap \
  security.passphrase="UnaClaveDeWifiLarga123" \
  security.authentication-types=wpa2-psk,wpa3-psk \
  datapath.bridge=bridge1 \
  radio=radio1

# --- IP y DHCP del bridge ---
/ip address add address=192.168.77.254/24 interface=bridge1 comment="LAN HOTSPOT"

/ip pool add name=pool-lan ranges=192.168.77.100-192.168.77.199

/ip dhcp-server network add \
  address=192.168.77.0/24 gateway=192.168.77.254 dns-server=1.1.1.1,8.8.8.8

/ip dhcp-server add \
  name=dhcp-lan interface=bridge1 address-pool=pool-lan lease-time=1h disabled=no

# --- NAT ---
/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade comment="NAT salida"

# --- HOTSPOT ---
/ip hotspot profile add \
  name=hsprof1 \
  hotspot-address=192.168.77.254 \
  dns-name="" \
  html-directory=hotspot

/ip hotspot add \
  name=hotspot1 \
  interface=bridge1 \
  address-pool=pool-lan \
  profile=hsprof1 \
  idle-timeout=5m \
  login-timeout=2m \
  keepalive-timeout=30s \
  disabled=no

# --- Perfiles y usuarios ---
/ip hotspot user profile add \
  name=perfil-gratis shared-users=1 session-timeout=1h idle-timeout=10m \
  keepalive-timeout=30s mac-cookie-timeout=1d rate-limit=512k/2M

/ip hotspot user add name=cliente password=cliente123 profile=perfil-gratis
```

### 9.3 El detalle clave: `interface=bridge1`, no `interface=ether2`

El servidor hotspot **debe** apuntar al bridge (o a la interfaz que tiene la IP del
hotspot). Si lo dejas en `ether2` y la IP está en `bridge1`, la redirección a
`192.168.77.254` no funciona y el portal no aparece.

```routeros
/ip hotspot print
# Comprueba: interface=bridge1  y  profile con hotspot-address=192.168.77.254
/ip address print where address~"192.168.77.254"
```

### 9.4 Clientes cableados y inalámbricos juntos

Como ambos están en `bridge1`, comparten:

- El mismo pool DHCP.
- El mismo portal.
- Las mismas reglas de firewall y colas.

No necesitas dos servidores hotspot ni dos subredes.

### 9.5 Aislamiento entre clientes (opcional)

```routeros
/interface wifi network set [find name=red-hotspot] datapath.client-isolation=yes
```

Los clientes del hotspot no se ven entre sí (típico en redes de hotel).

---

## 10. CAPsMAN: un AP, muchos SSID, muchos clientes

CAPsMAN es el **controlador centralizado** de MikroTik. En vez de configurar cada AP por
separado, los configuras en el controlador y los APs se auto-configuran.

| | CAPsMAN legacy | CAPsMAN v2 (nuevo) |
|---|---|---|
| **Menú** | `/caps-man` | `/interface wifi cap` / `/interface wifi capsman` |
| **Paquete** | `wireless` | `wifi-qcom*` (viene en el core desde 7.13) |
| **Compatible con** | `/interface wireless` | `/interface wifi` |

### 10.1 Configurar el controlador

```routeros
# El router que hace de controlador (puede ser el mismo que da hotspot)
/caps-man configuration add \
  name=cfg-lab \
  ssid="MIKROTIK-LAB" \
  datapath.bridge=bridge1 \
  security.authentication-types=wpa2-psk,wpa3-psk \
  security.passphrase="UnaClaveDeWifiLarga123" \
  radio.band=5ghz-ax \
  radio.channel-width=20/40/80mhz-ax \
  radio.country="colombia"

/caps-man provisioning add \
  action=create-dynamic-enabled \
  master-configuration=cfg-lab \
  name-format=prefix-identity \
  name-prefix=ap-lab
```

### 10.2 Configurar el AP (CAP)

En el RouterBOARD AP:

```routeros
# El AP recibe la configuración del controlador
/interface wifi cap set [find] enabled=yes master-configuration=cfg-lab
```

### 10.3 Verificar

```routeros
/caps-man registration-table print
/interface wifi registration-table print
```

### 10.4 ¿Cuándo usar CAPsMAN?

| Situación | Recomendación |
|---|---|
| 1 solo AP, todo en un router | **No** necesitas CAPsMAN. Configura la radio directamente. |
| Varios APs en un local | **Sí**, CAPsMAN v2. |
| APs de la misma marca y generación | CAPsMAN v2 si son `wifi-qcom*` |
| Necesitas roaming rápido (802.11r) | CAPsMAN v2 obligatorio |

> 💡 **El escenario típico de MikroTik + StarLink + Ubiquiti** (ver la carpeta
> `CONFIGURACIÓN Y COMERCIALIZACIÓN DE INTERNET CON STARLINK Y UBIQUITI` de este repo) es:
> un MikroTik como **router + hotspot** (con radio propia o con un AP Ubiquiti cableado)
> y StarLink como salida a Internet.

---

## 11. WAN: PPPoE, DHCP y Starlink

### 11.1 DHCP (cable, ONT, router de operadora)

```routeros
/ip dhcp-client add interface=ether1 name=wan1 disabled=no
/ip dhcp-client print
```

### 11.2 PPPoE (la mayoría de/providers de fibra)

```routeros
/interface pppoe-client add \
  name=pppoe1 \
  interface=ether1 \
  user=TU_USUARIO \
  password="TU_CONTRASENA" \
  add-default-route=yes \
  use-peer-dns=yes \
  disabled=no

/ip route print where dst-address=0.0.0.0/0
```

Diagnóstico:

```routeros
/interface pppoe-client print
/log print where topics~"ppp"
```

> 💡 La clave del PPPoE queda **en texto plano** en la configuración. Usa
> `/system export show-sensitive` solo cuando **saca** el equipo, y borra ese archivo después.

### 11.3 Starlink

Starlink entrega un router con salida Ethernet (o en la nueva generación, un router PoE con
salida Ethernet). El MikroTik se configura **exactamente igual que un DHCP**:

```
   Starlink (router o dish con PoE)  ──Ethernet──▶  ether1 (WAN del MikroTik)
```

```routeros
/ip dhcp-client add interface=ether1 name=wan1 disabled=no
```

Detalles prácticos:

| Tema | Recomendación |
|---|---|
| **Double NAT** | El MikroTik hace NAT de la red del hotspot y sale con NAT sobre el router de Starlink. Funciona, pero para VPN/port-forwarding es mejor poner el MikroTik en **modo AP/puente** o usar IP estática en Starlink. |
| **IP pública** | Con doble NAT no tienes IP pública en el MikroTik. Para inbound, configura el reenvío de puertos en el router de Starlink **hacia la IP WAN del MikroTik**. |
| **Banda ancha** | Starlink da 20-100+ Mbps de bajada, así que **el límite de 1 Mbps del CHR ya no aplica**. El hardware real rinde de sobra. |
| **Latencia** | Starlink tiene latencia alta (20-60 ms). Afecta a la respuesta del portal, no a la navegación. |
| **IPv6** | Starlink suele delegar IPv6. El hotspot de MikroTik funciona sobre IPv4; no lo mezcles con el cliente. |

### 11.4 Failover (dos salidas)

```routeros
/routing table add name=tabla-wan2 fib
/ip route add dst-address=0.0.0.0/0 gateway=<gw_wan2> routing-table=tabla-wan2
```

(El detalle completo de rutas y failover está en el [doc 01](./01-COMANDOS-MIKROTIK.md#43-rutas).)

---

## 12. Licencias y límites

### 12.1 Hardware

**No necesitas comprar licencia para usar un RouterBOARD.** La licencia de RouterOS viene
completa y sin límite de velocidad en el propio equipo.

Lo que sí tiene coste opcional:

| Servicio | Requiere |
|---|---|
| **IP/Cloud** (dirección IP gestionada de MikroTik) | RouterOS 7 o licencia pagada en los modelos antiguos |
| **RouterOS v6 legacy** (renovación anual) | Solo para licencias v6 compradas antes de v7 |
| **CHR** (el virtual) | Licencia aparte: free / P1 / P10 / P-Unlimited |

### 12.2 Comparativa de límites

| | CHR free | CHR P1 | CHR P10 | CHR P-Unlimited | RouterBOARD |
|---|---|---|---|---|---|
| **Subida por interfaz** | 1 Mbps | 1 Gbps | 10 Gbps | Ilimitada | La del hardware |
| **Precio** | 0 | $45 | $95 | $250 | Incluido |
| **Renovación** | No | Perpétua | Perpétua | Perpétua | — |
| **WiFi** | No | No | No | No | Según modelo |

> 📌 **En el RouterBOARD, la velocidad la pone el switch chip y la CPU**, no una licencia.
> Un hAP ax² con un puerto GbE llega a ~940 Mbps de tránsito.

### 12.3 Verificar la licencia

```routeros
/system license print
/system resource print
```

En un RouterBOARD normal verás `/system license` con la licencia embebida del modelo
(`RB` o `CHR` según el caso). Si aparece `limited-upgrades=yes`, el equipo no se puede
actualizar hasta regularizar la licencia.

---

## 13. Rendimiento real vs CHR

### 13.1 Teorías de throughput

| Equipo | CPU | Throughput firewall (con fastpath) | Puertos |
|---|---|---|---|
| hAP ax² | MediaTek Filogic 830 | ~500-900 Mbps | 5× GbE |
| hAP ax³ | Qualcomm IPQ | ~700-950 Mbps | 5× GbE |
| RB5009 | Marvell 98DX3236 | ~1-2 Gbps (sin offload total) | 1× SFP+ + 7× 1G |
| CCR2004 | Annapurna Alpine | ~2-4 Gbps | 12× SFP |
| hAP ac² | MediaTek 7286 | ~400-700 Mbps | 5× GbE |

> ⚠️ **Cifras orientativas.** El resultado real depende del offload, del número de flujos
> y de si el tráfico pasa por el firewall o no. Mide con `/tool bandwidth-test` o con un
> `iperf3` entre equipos.

### 13.2 El hotspot consume CPU

El portal cautivo **sí** añade carga: cada conexión pasa por las reglas del firewall, el
NAT y la cola. Con muchos clientes simultáneos, el hotspot puede ser el cuello de botella.

```routeros
/system resource print          # CPU en uso
/queue simple print detail       # paquetes en cola
/ip hotspot active print count-only
```

### 13.3 Medir en el propio equipo

```routeros
/tool bandwidth-test \
  address=192.168.77.100 \
  user=admin password="..." \
  duration=10s
```

---

## 14. Migrar la configuración del CHR al hardware

### 14.1 Qué se transfiere y qué no

| Elemento | ¿Se transfiere? | Nota |
|---|---|---|
| `/ip hotspot` (servidor, perfiles, usuarios) | ✅ Sí | Es configuración normal |
| `/ip firewall` (nat, filter, mangle) | ✅ Sí | Cuidado con los nombres de interfaz |
| `/ip dhcp-server`, `/ip pool`, `/ip address` | ✅ Sí | Revisa las interfaces |
| `/queue simple`, `/queue tree` | ✅ Sí | |
| `/ip dns`, `/ip route` | ✅ Sí | |
| `/system identity`, `/system clock` | ✅ Sí | |
| `/system scripts`, `/system scheduler` | ✅ Sí | |
| `/user` | ⚠️ **No** | El export oculta las contraseñas |
| `/interface bridge port` | ⚠️ Revisar | En el CHR no hay switch: no hay `hw=yes` |
| `/interface wireless` / `/interface wifi` | ❌ No | No existe en el CHR; hay que configurarlo desde cero |
| `/interface list` | ⚠️ Revisar | Los nombres de interfaz cambian |
| `/system backup` (binario) | ❌ **No** | Formato específico del CHR x86; no arranca en ARM |

### 14.2 Procedimiento recomendado

```routeros
# 1. EN EL CHR: exportar la configuración
/system export file=migracion-hotspot
/file print where name="migracion-hotspot.rsc"

# 2. Descargarlo al PC
#    (scp -P 2222 admin@127.0.0.1:/migracion-hotspot.rsc ./)
```

En el **RouterBOARD**:

```routeros
# 3. Subir el .rsc
#    (WinBox -> Files, o scp admin@192.168.88.1:/ ./)

# 4. ENSAYAR sin aplicar nada
/import file-name=migracion-hotspot.rsc dry-run=yes

# 5. Aplicar
/import file-name=migracion-hotspot.rsc
```

### 14.3 La lista de ajustes manuales tras importar

```
[ ] Cambiar /ip address: la del CHR (192.168.77.254 en ether2) → en bridge1
[ ] Cambiar /ip dhcp-server: interface=ether2 → interface=bridge1
[ ] Cambiar /ip hotspot: interface=ether2 → interface=bridge1
[ ] Cambiar /ip firewall nat: out-interface=ether1 (sigue igual si el WAN es ether1)
[ ] Crear /interface bridge add name=bridge1 y sus puertos con hw=yes
[ ] Configurar la radio WiFi (/interface wifi network) desde cero
[ ] Cambiar las contraseñas de los usuarios del router
[ ] Crear de nuevo los usuarios del hotspot (el export no trae las contraseñas)
[ ] Revisar /ip firewall filter: las reglas que usan interface-list deben existir
[ ] Verificar /ip dns static (las entradas de wifi.dev siguen valiendo)
```

### 14.4 Atajo: empezar de cero con la config ya entendida

Si la importación genera más problemas de los que resuelve, **reconstruye** la config
siguiendo el §5 + §9 de este documento. Con lo que ya aprendiste en el CHR, son 15 minutos
de trabajo y te queda una config **limpia y nativa** del hardware.

> 💡 **Esta es la opción profesional.** Una config importada arrastra herencias (interfaces
> inexistentes, reglas huérfanas, objetos duplicados) que luego te dan dolor de cabeza.

---

## 15. Diagnóstico en hardware

### 15.1 El kit de 12 prints (mismo que en el CHR)

```routeros
/system resource print
/interface print
/interface bridge port print
/ip address print
/ip route print
/ip arp print
/ip dhcp-server lease print
/ip dns cache print
/ip firewall nat print
/ip firewall filter print
/ip hotspot active print
/queue simple print detail
/log print where topics~"error"
```

### 15.2 Lo específico del hardware

```routeros
# Estado del switch y del offload
/interface bridge port print
#   -> columna H (hw-offload) debe ser yes

# Velocidad y negociación de los puertos
/interface ethernet print
/interface ethernet monitor ether2 once

# Consumo de PoE
/interface ethernet print where poe-out=yes

# Temperatura y voltaje (si el equipo tiene sensores)
/system sensor print

# Estado de la radio
/interface wifi print
/interface wifi radio print
/interface wifi scan
/interface wifi registration-table print
/interface wifi monitor wlan1 once

# Legalidad de la radio: potencia y canalEffective
/interface wifi radio print detail
```

### 15.3 Herramientas de línea de comandos

```routeros
/ping 1.1.1.1 count=4
/ping 192.168.77.254 count=4
/tool traceroute 1.1.1.1
/tool bandwidth-test address=192.168.77.100 duration=10s
/ip packet sniffer stream
/interface monitor-traffic bridge1
```

### 15.4 El paquete de consola serie

Si te quedas sin red, conéctate al **puerto serie** (WinBox → Interfaces → Serial) y
tendrás una terminal a 115200 baudios aunque el router no tenga IP.

```bash
# Linux: screen con el puerto USB-serial
sudo screen /dev/ttyUSB0 115200
```

---

## 16. Seguridad y hardening

### 16.1 Lo mínimo imprescindible

```routeros
# 1. Clave fuerte de admin
/user set admin password="UnaClaveMuyLargaYAleatoria2026"
/password

# 2. Usuario de administración con nombre propio
/user add name=operador password="OtraClaveDistinta456" group=full
#    (verifica que puedes entrar con él ANTES de tocar admin)

# 3. Desactivar o eliminar el admin por defecto
/user disable admin

# 4. Deshabilitar los servicios que no uses
/ip service print
/ip service set [find port=21] disabled=yes     # FTP
/ip service set [find port=23] disabled=yes     # Telnet
/ip service set [find port=80] disabled=yes     # HTTP (usa HTTPS para el hotspot)
#    NO deshabilites: 22 (SSH), 8291 (WinBox), 443 (HTTPS), 8728 (API) si lo usas

# 5. Limitar el acceso por IP
/ip service set [find port=8291] address=192.168.77.0/24
/ip service set [find port=22]   address=192.168.77.0/24

# 6. MAC server (solo para la LAN)
/ip mac-server print
#    Mac-server: se puede limitar a la interfaz bridge1
```

### 16.2 Gestión remota segura

| Opción | Cuándo |
|---|---|
| **WireGuard** | **La recomendada.** `/interface wireguard` (consulta de MikroTik). |
| **IPsec** | Para peers estáticos. |
| **OpenVPN** | Compatibilidad con terceros. |
| **PPPoE server** | Para dar acceso a usuarios remotos. |
| **Port-forward de WinBox a Internet** | ❌ **Nunca.** |

```routeros
# WireGuard básico
/interface wireguard add name=wg0 listen-port=13231
/ip address add address=10.10.10.1/24 interface=wg0
/interface wireguard peers add \
  allowed-address=10.10.10.2/32 \
  interface=wg0 \
  public-key="<clave pública del cliente>"
```

### 16.3 El hotspot como superficie de ataque

| Riesgo | Mitigación |
|---|---|
| Fuerza bruta de usuarios | `login-timeout` corto, `shared-users=1`, límite de intentos por IP |
| Rogue DHCP | El hotspot controla el DHCP de su LAN; desactiva cualquier otro servidor |
| DNS abierto | `allow-remote-requests` solo para la LAN |
| Abuso del walled-garden | Revisa `/ip hotspot walled-garden print` periódicamente |
| Claves por defecto | Cambia la clave del usuario `admin` del hotspot si existe |

```routeros
# Quitar el usuario admin sin clave del hotspot
:if ([:len [/ip hotspot user find name="admin"]] > 0) do={
  /ip hotspot user remove [find name="admin"]
}
```

### 16.4 HTTPS en el portal

```routeros
/certificate add name=cert-hs common-name=wifi.dev days-valid=3650 key-size=2048 \
    key-usage=digital-signature,key-encipherment,tls-server
/certificate sign cert-hs
/ip hotspot profile set [find name=hsprof1] ssl-certificate=cert-hs
```

> ⚠️ En muchos navegadores y móviles, el certificado autofirmado genera avisos. Para un
> laboratorio, `http` es más simple. Para producción, usa un certificado real.

---

## 17. Mantenimiento: backup, netinstall y reset

### 17.1 Backup automático

```routeros
/system script add name=backup-diario source={
  /system backup save name=backup-diario
}

/system scheduler add name=backup-diario \
  interval=1d start-time=03:00:00 \
  on-event="/system script run backup-diario" \
  policy=read,write,test,policy
```

> ⚠️ En hardware, los backups se guardan en la **flash**, que es pequeña. No acumules:
> borra los antiguos.
> ```routeros
> /file remove [find name~"backup-diario.backup"]
> ```

### 17.2 Descargar el backup al PC

```bash
scp admin@192.168.88.1:/backup-diario.backup ./
```

Guárdalo **fuera del router**. Un backup que solo vive en el router se pierde con el router.

### 17.3 Netinstall (reinstalar RouterOS por red)

Útil si actualizas a una versión que no arranca, o si corrompes la configuración:

1. Descarga el **RouterOS System Package** de la versión exacta.
2. Renómbralo a `mikrotik-routeros-<version>.npk`.
3. Ponlo en un servidor HTTP accesible desde el router:

```bash
cd ~/descargas && python3 -m http.server 8000
```

4. En el router, **con el cable de gestión conectado**:

```routeros
/system reset-configuration no-defaults=yes skip-backup=yes
/system netinstall install-file=mikrotik-routeros-7.24.x.npk http-address=192.168.88.10/8000
```

5. El router se reinicia con el nuevo RouterOS. La configuración se conserva (a menos que
   hayas usado `skip-backup=yes` en el reset previo).

### 17.4 Reset a fábrica

```routeros
/system reset-configuration
```

O con el botón: mantener RESET **10 s** (con la fuente conectada).

Después: IP `192.168.88.1`, usuario `admin`, contraseña vacía o la del sticker.

### 17.5 Antes de tocar el firmware

```routeros
/system backup save name=pre-cambio
/file print
```

Y descarga el `.backup` al PC. **Siempre.**

---

## 18. Checklist final

### Encendido y acceso

- [ ] RouterBOARD con la versión de RouterOS **estable y actual**.
- [ ] Consola **serie** configurada y probada.
- [ ] WinBox ve el equipo por **MAC** en la pestaña Neighbors.
- [ ] Contraseña de `admin` cambiada; usuario nuevo probado.
- [ ] SSH, WinBox y (opcional) HTTPS operativos; FTP, Telnet y HTTP cerrados.

### Red

- [ ] `ether1` = WAN, con su cliente (DHCP o PPPoE) y ruta por defecto.
- [ ] `bridge1` con los puertos LAN y `hw=yes`.
- [ ] `allow-fast-path=yes`.
- [ ] IP del LAN, pool DHCP y gateway correctos.
- [ ] NAT en `chain=srcnat` para la salida.
- [ ] Firewall con `accept` desde LAN y `drop` desde WAN.

### WiFi

- [ ] `country` configurado (obligatorio).
- [ ] Canal correcto (evita DFS si no es necesario).
- [ ] SSID y clave WPA2/WPA3 con al menos 8 caracteres.
- [ ] Radio en el mismo bridge que los puertos LAN.
- [ ] `datapath.client-isolation` si es una red de invitados.

### Hotspot

- [ ] `hotspot-address` = IP real de la interfaz del hotspot.
- [ ] `interface=bridge1` en el servidor hotspot.
- [ ] Perfil de usuario con `rate-limit` y timeouts razonables.
- [ ] Sin usuario `admin` sin clave.
- [ ] Walled-garden con lo mínimo imprescindible.
- [ ] Un cliente real se autentica y navega.

### Operación

- [ ] Backup manual descargado al PC.
- [ ] Backup automático programado.
- [ ] `/system clock` correcto y NTP sincronizado.
- [ ] Registro (`/log`) revisado y sin errores.
- [ ] `/system resource print` con CPU y RAM en valores normales.

---

## Documentos relacionados

| Documento | Cuándo leerlo |
|---|---|
| [`00-ENTORNO-Y-PREPARACION.md`](./00-ENTORNO-Y-PREPARACION.md) | El laboratorio virtual: bridge, tap, hostapd. |
| [`01-COMANDOS-MIKROTIK.md`](./01-COMANDOS-MIKROTIK.md) | Catálogo completo de comandos (hotspot, timeouts, NAT, diagnóstico). |
| [`02-COMANDOS-ESENCIALES-MIKROTIK.md`](./02-COMANDOS-ESENCIALES-MIKROTIK.md) | El mínimo imprescindible de RouterOS. |
| [`03-EQUIVALENTES-VMWARE-VIRTUALBOX.md`](./03-EQUIVALENTES-VMWARE-VIRTUALBOX.md) | Si quieres el CHR en VMware o VirtualBox. |
| **Este** | Cuando vas a montar el laboratorio en un router real. |
