# Comandos MikroTik — RouterOS 7.24.5 (CHR)

> **Este es el segundo documento.** Catálogo de comandos RouterOS para configurar el hotspot,
> los **tiempos (timeouts)**, perfiles, cuotas, límites de ancho de banda y diagnóstico.
> Antes de leerlo, ten el entorno listo → [`00-ENTORNO-Y-PREPARACION.md`](./00-ENTORNO-Y-PREPARACION.md)

**Versión de referencia:** RouterOS 7.24.5 (CHR, x86_64)
**Sintaxis verificada contra:** MikroTik CLI Reference oficial, rama `7.24`
**Acceso:** `ssh -p 2222 admin@127.0.0.1` · WinBox `127.0.0.1:8291`

---

## Índice

1. [Acceso y modo de trabajo](#1-acceso-y-modo-de-trabajo)
2. [Sintaxis RouterOS esencial](#2-sintaxis-routeros-esencial)
3. [Comandos base del sistema](#3-comandos-base-del-sistema)
4. [Red: interfaces, IP, DHCP, DNS](#4-red-interfaces-ip-dhcp-dns)
5. [NAT y firewall](#5-nat-y-firewall)
6. [Hotspot: servidor y perfil](#6-hotspot-servidor-y-perfil)
7. [Hotspot: perfiles de usuario](#7-hotspot-perfiles-de-usuario)
8. [Hotspot: usuarios](#8-hotspot-usuarios)
9. [Tiempos (timeouts)](#9-tiempos-timeouts)
10. [Límites de ancho de banda](#10-límites-de-ancho-de-banda)
11. [Walled-garden](#11-walled-garden)
12. [IP binding](#12-ip-binding)
13. [Cookies y sesiones](#13-cookies-y-sesiones)
14. [Scripts on-login / on-logout](#14-scripts-on-login--on-logout)
15. [RADIUS](#15-radius)
16. [Diagnóstico y monitoreo](#16-diagnóstico-y-monitoreo)
17. [Backup, export e import](#17-backup-export-e-import)
18. [Script completo del laboratorio](#18-script-completo-del-laboratorio)
19. [Cheat sheet](#19-cheat-sheet)

---

## 1. Acceso y modo de trabajo

### 1.1 Entrar

```bash
# SSH
ssh -p 2222 admin@127.0.0.1

# WinBox
#   abres WinBox → New Connection → 127.0.0.1:8291
```

### 1.2 Prompt de RouterOS

```
[admin@MICRO-DEV-ROOT] > /ip hotspot
[admin@MICRO-DEV-ROOT] /ip/hotspot> print
```

- `>` = nivel raíz
- La ruta actual se muestra entre `[` y `]`
- `?` al final de un comando lista las propiedades disponibles
- `Tab` autocompleta

### 1.3 Atajos imprescindibles

| Atajo | Efecto |
|---|---|
| `Ctrl+X` | **Cancelar** la línea actual y volver al inicio. Salva de errores. |
| `Ctrl+C` | Interrumpir el comando en curso. |
| `Ctrl+D` | Salir del directorio actual (subir un nivel). |
| `Ctrl+R` | Repetir el último comando. |
| `Ctrl+U` | Borrar la línea completa. |
| `?` | Ver todas las propiedades del comando. |
| `Shift+Tab` | Autocompletar. |
| `print detail` | Ver todos los campos (no solo los no-default). |
| `print stats` | Ver contadores de bytes/paquetes. |

> 💡 `print` **oculta** las propiedades con valor por defecto. Usa `print detail` cuando dudes si algo
> está realmente configurado.

### 1.4 Scripting por SSH (no interactivo)

```bash
sshpass -p 'TU_CLAVE' ssh -p 2222 admin@127.0.0.1 '/ip/hotspot/active/print'
```

```bash
# Enviar un .rsc
sshpass -p 'TU_CLAVE' scp -P 2222 hotspot-lab.rsc admin@127.0.0.1:/
sshpass -p 'TU_CLAVE' ssh -p 2222 admin@127.0.0.1 '/import file-name=hotspot-lab.rsc'
```

> ⚠️ `sshpass` deja la clave en el historial del shell. Para producción usa claves SSH:
> ```bash
> ssh-keygen -t ed25519 -f ~/.ssh/mikrotik_chr
> # en el CHR: /user ssh-keys import file-name=pubkey user=admin
> ```

---

## 2. Sintaxis RouterOS esencial

### 2.1 Estructura de un comando

```
/ruta/menú  add  propiedad=valor  propiedad2="valor con espacios"
      │        │      │                │
      │        │      │                └── comillas si hay espacios o caracteres especiales
      │        │      └── el verbo
      │        └── el menú
      └── ruta completa
```

### 2.2 Verbos principales

| Verbo | Qué hace |
|---|---|
| `print` | Lista entradas del menú. |
| `print detail` | Lista con todos los campos. |
| `print stats` | Lista con contadores. |
| `add` | Crea una entrada nueva. |
| `set` | Modifica entradas existentes. |
| `remove` | Borra entradas. |
| `find` | Selecciona entradas por criterio. |
| `enable` / `disable` | Activa/desactiva sin borrar. |
| `export` / `import` | Serializa / restaura configuración. |
| `monitor` | Muestra en vivo (Ctrl+C para salir). |

### 2.3 `find` — el cuantificador más usado

```routeros
# Buscar por nombre
/ip hotspot print where name="hotspot1"

# Modificar por búsqueda
/ip hotspot set [find name="hotspot1"] idle-timeout=10m

# Eliminar por búsqueda
/ip hotspot user remove [find name="cliente"]

# Encadenar condiciones
/ip firewall filter print where chain=input && action=accept

# Filtrar por contenido parcial
/ip address print where address~"192.168.77"
```

> 💡 **`[find ...]` entre corchetes** es lo que devuelve una "referencia" a las entradas que coinciden.
> Es la forma idiomática de hacer scripts robustos.

### 2.4 `remove` con selección múltiple

```routeros
# Quitar todas las leases DHCP expiradas
/ip dhcp-server lease remove [find expires-before="1d"]

# Quitar todas las entradas dinámicas del hotspot
/ip hotspot host remove [find dynamic]
```

### 2.5 Variables y comentarios

```routeros
:local miVar 10
:global contador 0
# comentario con almohadilla
```

### 2.6 Comillas: cuándo hacen falta

```routeros
name="mi nombre"          # con espacio
password="clave;con;punto" # con punto y coma
comment=sin_espacios      # sin comillas si no hay caracteres especiales
```

---

## 3. Comandos base del sistema

### 3.1 Identidad y usuarios

```routeros
/system identity set name=MICRO-DEV-ROOT

# Cambiar la contraseña del admin
/user set admin password="TU_CLAVE_SEGURA"

# Crear un usuario de solo lectura para monitorización
/user add name=monitor group=read password="CLAVE" address=192.168.77.0/24
```

### 3.2 Fecha y hora (importante para logs y para el hotspot)

```routeros
/system clock set time=14:30:00 date=2026-10-21
/system clock print

# NTP
/system ntp client set enabled=yes servers=time.pool.ubuntu.com
/system ntp client print
```

> Sin hora correcta, los logs y los tiempos del hotspot son inútiles.

### 3.3 Logging

```routeros
/log print                          # todo
/log print where topics~"hotspot"   # solo hotspot
/log print where message~"login"
/log print where topics~"error"

/system logging action set memory=yes
/system logging print
```

### 3.4 Scripts y scheduler

```routeros
# Crear un script
/system script add name=reporte source={ :put "Clientes activos: [:len [/ip hotspot active find]]" }

/system script print
/system script run reporte

# Programarlo
/system scheduler add name=reporte-diario interval=1d start-time=08:00:00 \
    on-event="/system script run reporte" policy=read,write,test,policy
```

### 3.5 Reinicio y apagado

```routeros
/system reboot
/system shutdown
```

### 3.6 Safe mode (tu red de seguridad)

Antes de un cambio grande, en la terminal SSH:

```
Ctrl+X
```

RouterOS registra todo lo que escribas. Si pierdes la conexión, **revierte automáticamente** al hacer
desconexión. Para salir del safe mode: `Ctrl+X` de nuevo.

---

## 4. Red: interfaces, IP, DHCP, DNS

### 4.1 Interfaces

```routeros
/interface print
/interface ethernet print
/interface print detail

# Ver estado en vivo
/interface monitor-traffic ether2 once
/interface print stats
```

### 4.2 Direcciones IP

```routeros
/ip address print
/ip address print detail

/ip address add address=192.168.77.254/24 interface=ether2 comment="LAN HOTSPOT"

/ip address remove [find interface=ether2]
```

### 4.3 Rutas

```routeros
/ip route print
/ip route print detail

# Ruta estática
/ip route add dst-address=10.10.0.0/16 gateway=192.168.77.1
```

### 4.4 DHCP — pool

```routeros
/ip pool print
/ip pool print detail

/ip pool add name=pool-lan ranges=192.168.77.100-192.168.77.199
/ip pool remove [find name="pool-lan"]
```

### 4.5 DHCP — servidor

```routeros
/ip dhcp-server print
/ip dhcp-server print detail

/ip dhcp-server add \
  name=dhcp-lan \
  interface=ether2 \
  address-pool=pool-lan \
  lease-time=1h \
  disabled=no

/ip dhcp-server set [find name="dhcp-lan"] lease-time=30m
```

### 4.6 DHCP — configuración de red (gateway, DNS)

```routeros
/ip dhcp-server network print

/ip dhcp-server network add \
  address=192.168.77.0/24 \
  gateway=192.168.77.254 \
  dns-server=1.1.1.1,8.8.8.8

# Cambiar el DNS que se entrega a los clientes (para usar el DNS interno)
/ip dhcp-server network set [find address="192.168.77.0/24"] dns-server=192.168.77.254
```

### 4.7 DHCP — leases

```routeros
/ip dhcp-server lease print
/ip dhcp-server lease print detail

# Ver qué IP tiene un cliente concreto
/ip dhcp-server lease print where address~"192.168.77.1"

/# Hacer una lease estática
/ip dhcp-server lease add address=192.168.77.150 mac-address=AA:BB:CC:DD:EE:FF \
    address-lists="estaticos" comment="Cliente fijo"

/# Liberar una lease
/ip dhcp-server lease remove [find address="192.168.77.150"]
```

### 4.8 DHCP — cliente (WAN)

```routeros
/ip dhcp-client print
/ip dhcp-client add interface=ether1 name=client1 disabled=no
/ip dhcp-client set [find name="client1"] use-peer-dns=no
```

### 4.9 DNS

```routeros
/ip dns print
/ip dns static print

# Servidores del router
/ip dns set servers=1.1.1.1,8.8.8.8 allow-remote-requests=yes

# Entrada estática local (para el modo B)
/ip dns static add name=wifi.dev address=192.168.77.254

# Flush de la cache
/ip dns cache flush
```

### 4.10 ARP

```routeros
/ip arp print
/ip arp print where interface=ether2
```

---

## 5. NAT y firewall

### 5.1 NAT — masquerade (salida a Internet)

```routeros
/ip firewall nat print

# NAT de salida por la WAN
/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade comment="NAT salida"

/# NAT del hotspot (red → Internet)
/ip firewall nat add chain=srcnat src-address=192.168.77.0/24 action=masquerade comment="NAT hotspot"
```

> 💡 El `masquerade` de la salida (`out-interface=ether1`) **ya cubre** a los clientes del hotspot,
> porque su tráfico sale por `ether1`. El segundo NAT es una capa extra que solo aplica si tienes
> varias subredes. No es obligatorio en este montaje.

### 5.2 NAT — port forwarding (dst-nat)

```routeros
# Publicar un servicio del CHR en la WAN
/ip firewall nat add chain=dstnat protocol=tcp dst-port=8080 \
    in-interface=ether1 action=dst-nat to-ports=80 to-addresses=192.168.77.254
```

### 5.3 Filtrado

```routeros
/ip firewall filter print
/ip firewall filter print stats

# Bloquear el acceso de la WAN al CHR
/ip firewall filter add chain=input in-interface=ether1 action=drop comment="Bloquear WAN"

/# Bloquear el acceso entre la LAN del hotspot y el resto
/ip firewall filter add chain=forward \
    in-interface=ether2 out-interface=ether2 action=drop comment="Aislar hotspot"
```

### 5.4 Address lists

```routeros
/ip firewall address-list print

/ip firewall address-list add list=permitidos address=192.168.77.100-192.168.77.199
/ip firewall address-list add list=bloqueados address=203.0.113.5 timeout=1h

/ip firewall filter add chain=forward src-address-list=bloqueados action=drop
```

### 5.5 Mangle (marking para QoS)

```routeros
/ip firewall mangle print

# Marcar el tráfico de subida de los clientes del hotspot
/ip firewall mangle add chain=prerouting \
    in-interface=ether2 action=mark-packet new-packet-mark=hs-upload passthrough=yes

# Marcar la bajada
/ip firewall mangle add chain=prerouting \
    out-interface=ether2 action=mark-packet new-packet-mark=hs-download passthrough=yes
```

### 5.6 Raw (anti-DoS rápido)

```routeros
/ip firewall raw add chain=prerouting action=notrack \
    in-interface=ether2 protocol=tcp port=80 comment="No rastrear HTTP"
```

---

## 6. Hotspot: servidor y perfil

### 6.1 `/ip hotspot` — el servidor

```routeros
/ip hotspot print
/ip hotspot print detail
```

| Propiedad | Tipo | Default | Significado |
|---|---|---|---|
| `name` | texto | — | Nombre del servidor. |
| `interface` | interfaz | obligatorio | Interfaz donde escucha el hotspot. |
| `address-pool` | nombre/none | none | Pool desde el que se reasigna IP a clientes mal configurados. |
| `profile` | nombre | default | Perfil del servidor. |
| `idle-timeout` | tiempo/none | **5m** | Inactividad **de clientes no autorizados**. |
| `keepalive-timeout` | tiempo/none | none | Cuánto puede estar el host inalcanzable antes de borrarse. |
| `login-timeout` | tiempo/none | none | Tiempo para que un host se autentique antes de ser borrado de la tabla. |
| `addresses-per-mac` | entero/unlimited | **2** | IPs por MAC (múltiples dispositivos detrás de un router). |

```routeros
/ip hotspot add \
  name=hotspot1 \
  interface=ether2 \
  address-pool=pool-lan \
  profile=hsprof1 \
  idle-timeout=5m \
  disabled=no

/ip hotspot set [find name="hotspot1"] idle-timeout=10m
/ip hotspot remove [find name="hotspot1"]
```

> 📌 **Solo un hotspot por interfaz.** Si el cliente no se autentica nunca, su entrada en
> `/ip hotspot host` se queda ahí para siempre: usa `login-timeout` para limpiar.

### 6.2 `/ip hotspot profile` — el perfil del servidor

```routeros
/ip hotspot profile print
/ip hotspot profile print detail
```

| Propiedad | Tipo | Default | Significado |
|---|---|---|---|
| `name` | texto | — | Nombre del perfil. |
| `hotspot-address` | IP | — | **Debe ser la IP de la interfaz del hotspot.** |
| `dns-name` | texto | — | Nombre del portal. `""` = usar solo IP. |
| `html-directory` | file | hotspot | Directorio de plantillas HTML. |
| `html-directory-override` | file | — | Sobrescribe solo un archivo. |
| `login-by` | múltiples | cookie,http-chap,https,http-pap,mac-cookie,mac | Métodos de login admitidos. |
| `mac-auth-mode` | mac-as-username \| mac-as-username-and-password | mac-as-username | Cómo se interpreta la MAC en login por MAC. |
| `mac-auth-password` | texto | — | Contraseña para `mac-as-username-and-password`. |
| `http-cookie-lifetime` | tiempo | 1h | Duración de la cookie de sesión. |
| `split-user-domain` | sí/no | no | Separa `usuario@dominio` en usuario y dominio. |
| `use-radius` | sí/no | no | Delega la autenticación a RADIUS. |
| `radius-accounting` | sí/no | no | Envía Accounting-Start/Stop. |
| `radius-interim-update` | tiempo/received | received | Frecuencia de Interim-Update. |
| `trial-uptime-limit` | tiempo | — | Tiempo de los usuarios de prueba (`trial`). |
| `trial-uptime-reset` | tiempo | — | Cada cuánto se reinicia el tiempo de prueba. |
| `trial-user-profile` | nombre | — | Perfil asignado a los usuarios `trial`. |
| `install-hotspot-queue` | sí/no | no | Instala una cola automática para el hotspot. |
| `rate-limit` | texto | — | Límite global del portal (todas las sesiones). |
| `ssl-certificate` | none | none | Certificado para login por HTTPS. |
| `http-proxy` | IP:puerto | — | Proxy externo para las páginas del portal. |
| `smtp-server` | IP | — | Servidor SMTP para los avisos por correo. |

```routeros
/ip hotspot profile add \
  name=hsprof1 \
  hotspot-address=192.168.77.254 \
  dns-name="" \
  html-directory=hotspot

# Cambiar a login por cookie + https, con vida de cookie de 2 horas
/ip hotspot profile set [find name="hsprof1"] login-by=cookie,https http-cookie-lifetime=2h
```

> 🔴 **`hotspot-address` debe coincidir con la IP de `ether2`** o el portal no cargará.
> 🔴 **`dns-name=""` es intencional en este laboratorio.** Ver §11.6 de
> [`00-ENTORNO-Y-PREPARACION.md`](./00-ENTORNO-Y-PREPARACION.md).

### 6.3 Login por HTTPS (recomendado en producción)

```routeros
/certificate add name=hs-cert common-name=wifi.local days-valid=3650 \
    key-size=2048 private-key=yes
/certificate sign hs-cert
/ip hotspot profile set hsprof1 ssl-certificate=hs-cert
```

---

## 7. Hotspot: perfiles de usuario

### 7.1 `/ip hotspot user profile` — los grupos de usuario

Aquí se define **toda la política** de cada tipo de cliente.

```routeros
/ip hotspot user profile print
/ip hotspot user profile print detail
```

| Propiedad | Tipo | Default | Significado |
|---|---|---|---|
| `name` | texto | — | Nombre del perfil. |
| `session-timeout` | tiempo | **0s** (=ilimitado) | Duración máxima de la sesión. |
| `idle-timeout` | tiempo/none | none | Desconexión por inactividad. |
| `keepalive-timeout` | tiempo/none | none | Verifica que el cliente siga vivo. |
| `shared-users` | entero/unlimited | **1** | Sesiones simultáneas con el mismo usuario. |
| `rate-limit` | texto | — | Límite de velocidad (ver §10.1). |
| `address-list` | texto | — | Lista donde se mete la IP del usuario (útil para colas). |
| `incoming-filter` | cadena | — | Cadena de firewall para el tráfico de entrada. |
| `outgoing-filter` | cadena | — | Cadena de firewall para el tráfico de salida. |
| `incoming-packet-mark` | texto | — | Marca mangle de entrada. |
| `outgoing-packet-mark` | texto | — | Marca mangle de salida. |
| `on-login` | script | — | Script ejecutado al autenticar. |
| `on-logout` | script | — | Script ejecutado al desconectar. |
| `transparent-proxy` | sí/no | sí | Proxy HTTP transparente para los autorizados. |
| `add-mac-cookie` | sí/no | sí | Añade cookie MAC para auto-reconexión. |
| `mac-cookie-timeout` | tiempo | **3d** | Validez de la cookie MAC. |
| `open-status-page` | always \| http-login | always | Abre la página de estado tras login por MAC. |
| `status-autorefresh` | tiempo/none | none | Auto-refresco de la página de estado. |
| `advertise` | sí/no | no | Popups de publicidad forzados. |
| `advertise-url` | lista | — | URLs del popup. |
| `advertise-interval` | lista de tiempos | 30m,10m | Cada cuánto salta el popup. |
| `advertise-timeout` | tiempo/immediately/never | 1m | Cuánto se muestra antes de cortar el acceso. |
| `address-pool` | nombre/none | none | Pool para forzar IP a clientes mal configurados. |

### 7.2 Crear perfiles típicos

```routeros
# Perfil gratuito: 2 Mbps, sesión de 1 hora, 1 dispositivo
/ip hotspot user profile add \
  name=perfil-gratis \
  shared-users=1 \
  session-timeout=1h \
  idle-timeout=10m \
  rate-limit=2M/4M

# Perfil premium: 20 Mbps, sesión de 8 horas, 3 dispositivos
/ip hotspot user profile add \
  name=perfil-premium \
  shared-users=3 \
  session-timeout=8h \
  idle-timeout=20m \
  keepalive-timeout=2m \
  rate-limit=10M/20M

# Perfil por tiempo (para pruebas): 30 minutos, sin límite de velocidad
/ip hotspot user profile add \
  name=perfil-prueba \
  session-timeout=30m \
  idle-timeout=5m
```

### 7.3 Modificar y eliminar

```routeros
/ip hotspot user profile set [find name="perfil-gratis"] rate-limit=3M/6M
/ip hotspot user profile remove [find name="perfil-prueba"]
```

---

## 8. Hotspot: usuarios

### 8.1 `/ip hotspot user`

```routeros
/ip hotspot user print
/ip hotspot user print detail
```

| Propiedad | Tipo | Significado |
|---|---|---|
| `name` | texto | Nombre de usuario (obligatorio). |
| `password` | texto | Contraseña. |
| `profile` | nombre | Perfil de usuario al que pertenece. |
| `server` | enum/all | Servidor de hotspot donde se autentica. |
| `address` | IP | Fija la IP del usuario. |
| `mac-address` | MAC | Vincula la MAC (auto-login). |
| `limit-uptime` | tiempo | Tiempo máximo de uso **de este usuario**. |
| `limit-bytes-in` | entero | Bytes máximos que puede **subir**. |
| `limit-bytes-out` | entero | Bytes máximos que puede **descargar**. |
| `limit-bytes-total` | entero | Bytes máximos totales (subida + bajada). |
| `email` | texto | Correo del usuario. |
| `routes` | texto | Rutas estáticas para el cliente. |
| `otp-secret` | texto | Secreto TOTP (2FA). |

### 8.2 Crear usuarios

```routeros
/ip hotspot user add \
  name=cliente \
  password=cliente123 \
  profile=default \
  comment="Usuario de prueba"

/ip hotspot user add \
  name=cliente-premium \
  password=claveSegura \
  profile=perfil-premium \
  limit-uptime=2h

# Usuario con cuota de datos: 500 MB totales (bytes)
/ip hotspot user add \
  name=cliente-quota \
  password=claveSegura \
  profile=perfil-gratis \
  limit-bytes-total=524288000

# Usuario auto-conectado por MAC
/ip hotspot user add \
  name=auto-mac \
  profile=perfil-gratis \
  mac-address=AA:BB:CC:DD:EE:FF
```

### 8.3 Gestión

```routeros
# Cambiar la contraseña
/ip hotspot user set [find name="cliente"] password=nuevaClave

# Mover un usuario a otro perfil
/ip hotspot user set [find name="cliente"] profile=perfil-premium

# Quitar un usuario
/ip hotspot user remove [find name="cliente"]

# Desactivar sin borrar
/ip hotspot user set [find name="cliente"] disabled=yes
```

### 8.4 Endpoint de API (integración web)

```routeros
# Crear un usuario vía API (solo desde la LAN)
/ip hotspot user add name=invitado password=tmp profile=perfil-gratis

# Ver todos los usuarios con su tráfico
/ip hotspot user print detail
```

> El CHR expone la API REST en `https://<ip>/rest/`. El certificado es autofirmado, así que el
> cliente debe configurarse para no validarlo (solo en laboratorio).

---

## 9. Tiempos (timeouts)

Esta es la tabla de referencia de **todos** los tiempos del hotspot y dónde se configuran.

### 9.1 Resumen

| Timeout | Dónde | Default | Afecta a | Qué pasa al expirar |
|---|---|---|---|---|
| `idle-timeout` | `/ip hotspot` | **5m** | Clientes **no autorizados** | El host sale de la tabla de hotspots; se libera su IP. |
| `keepalive-timeout` | `/ip hotspot` | none | Todos | El host es borrado si no responde. |
| `login-timeout` | `/ip hotspot` | none | No autenticados | El host se borra de la tabla y puede volver a intentar. |
| `session-timeout` | `/ip hotspot user profile` | **0s** (ilimitado) | **Autenticados** | Cierre incondicional de la sesión. El usuario debe re-autenticarse. |
| `idle-timeout` | `/ip hotspot user profile` | none | **Autenticados** | Cierre por inactividad (sin tráfico). |
| `keepalive-timeout` | `/ip hotspot user profile` | none | **Autenticados** | Cierre si el cliente deja de responder. |
| `mac-cookie-timeout` | `/ip hotspot user profile` | **3d** | Cookie MAC | El dispositivo pierde la autoconexión y vuelve al portal. |
| `http-cookie-lifetime` | `/ip hotspot profile` | **1h** | Cookie HTTP | La sesión se "olvida": hay que volver a loguearse. |
| `status-autorefresh` | `/ip hotspot user profile` | none | Página de estado | Refresco automático de la página. |
| `advertise-timeout` | `/ip hotspot user profile` | 1m | Popups | Si el popup no se muestra, se corta el acceso. |
| `advertise-interval` | `/ip hotspot user profile` | 30m,10m | Popups | Cada cuánto se fuerza el popup. |
| `limit-uptime` | `/ip hotspot user` | 0 (sin límite) | Un usuario concreto | Cierre al alcanzar el tiempo. |
| `trial-uptime-limit` | `/ip hotspot profile` | — | Usuarios `trial` | Fin del tiempo de prueba. |

### 9.2 La diferencia clave: `session-timeout` vs `idle-timeout`

```
    sesión del usuario
    ├────────────────────────── session-timeout (8h) ──────────────────────────┤
    │                                                                             │
    │   actividad  ████░░░███████░░░░██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
    │              ↑           ↑              ↑                                   │
    │           traffic    traffic        traffic                                │
    │                                                                             │
    │      ┌──── idle-timeout (20m) ────┐                                        │
    │      │  se reinicia con cada traffic                                        │
    │      └────────────────────────────┘                                        │
    │                                                                             │
    └─────────────────────────────────────────────────────────────────────────────┘
                                                                                   ▼
                                                                    cierre + re-login
```

- **`session-timeout`**: reloj de pared. Cierra **a los 8 horas** aunque el usuario esté todo el rato
  descargando. Es el "ticket" del día.
- **`idle-timeout`**: temporizador de inactividad. **Se reinicia con cada paquete**. Cierra tras 20 min
  sin tráfico (navegador cerrado, móvil bloqueado).

> 💡 **Regla práctica:** pon siempre un `session-timeout` (corta la sesión infinita) y un
> `idle-timeout` (libera recursos de usuarios dormidos). Sin `idle-timeout`, un móvil en la mesa
> ocupa su IP y su sesión indefinidamente.

### 9.3 Configuración recomendada

```routeros
# En el SERVIDOR: hosts que nunca se autentican se limpian solos
/ip hotspot set [find name="hotspot1"] \
  idle-timeout=5m \
  login-timeout=2m \
  keepalive-timeout=30s

# En el PERFIL: política de los usuarios autenticados
/ip hotspot user profile set [find name="perfil-gratis"] \
  session-timeout=1h \
  idle-timeout=10m \
  keepalive-timeout=30s \
  mac-cookie-timeout=1d

/ip hotspot user profile set [find name="perfil-premium"] \
  session-timeout=8h \
  idle-timeout=20m \
  keepalive-timeout=2m \
  mac-cookie-timeout=3d

# Cookie HTTP: 2 horas de sesión sin re-login
/ip hotspot profile set [find name="hsprof1"] http-cookie-lifetime=2h
```

### 9.4 Ver los tiempos efectivos de una sesión

```routeros
/ip hotspot active print detail
```

Muestra `uptime`, `session-time-left`, `idle-time`, `idle-timeout` y `keepalive-timeout` **calculados
para esa sesión concreta**. Es la forma de confirmar que el perfil se aplicó bien.

### 9.5 Probar los tiempos

```routeros
# Cerrar la sesión de un usuario concreto
/ip hotspot active remove [find user="cliente"]

# Ver quién está conectado y desde cuándo
/ip hotspot active print

# Cerrar todas las sesiones
/ip hotspot active remove [find]
```

### 9.6 Nota sobre `keepalive-timeout`

El `keepalive-timeout` funciona con **ICMP**. Si un cliente bloquea los pings, RouterOS lo considerará
inalcanzable y lo expulsará. Por eso:

- No pongas `keepalive-timeout` muy corto (< 30s).
- Si los clientes son móviles con ahorro de energía, `2m` es más seguro que `30s`.

---

## 10. Límites de ancho de banda

Hay **tres** mecanismos distintos. No los confundas.

| Mecanismo | Dónde | Granularidad | Cuándo usarlo |
|---|---|---|---|
| `rate-limit` del perfil hotspot | `/ip hotspot user profile` | Por perfil | Límite simple por tipo de usuario. |
| `rate-limit` del usuario | `/ip hotspot user` | Por usuario | Excepción puntual. |
| Simple Queue | `/queue simple` | Por IP/objetivo | Límite fino por cliente. |
| Queue Tree | `/queue tree` | Por packet-mark | QoS avanzado con prioridad. |

### 10.1 `rate-limit` en el perfil — el más simple

**Formato (punto de vista del router):**

```
rx-rate[/tx-rate] [rx-burst/tx-burst] [rx-threshold/tx-threshold] [rx-time/tx-time] [priority] [rx-min/tx-min]
```

> 🔴 **Trampa clásica:** en `rate-limit`, el **primer valor es `rx` = subida del cliente** y el
> **segundo es `tx` = bajada del cliente**. Es decir, **el orden es subida/bajada**, *opuesto* al de
> `max-limit` en las colas.

| Quiero | Escribo |
|---|---|
| 2 Mbps de bajada, 512 kbps de subida | `rate-limit=512k/2M` |
| 10 Mbps bajada, 5 Mbps subida | `rate-limit=5M/10M` |
| Igual en ambos sentidos | `rate-limit=5M/5M` |

```routeros
/ip hotspot user profile set [find name="perfil-gratis"] rate-limit=512k/2M
/ip hotspot user profile set [find name="perfil-premium"] rate-limit=5M/20M
```

### 10.2 `rate-limit` con burst

```
rx-rate/tx-rate  rx-burst/tx-burst  rx-threshold/tx-threshold  rx-time/tx-time  priority  rx-min/tx-min
```

```routeros
# 5M/10M normal, con ráfaga hasta 8M/16M cuando el promedio baja de 4M/8M durante 10s
rate-limit=5M/10M 8M/16M 4M/8M 10s
```

### 10.3 Límite por usuario concreto

```routeros
/ip hotspot user set [find name="cliente"] rate-limit=256k/512k
```

> 💡 En RouterOS 7 el valor del **perfil** y el del **usuario** son independientes. El del usuario
> **no** hereda del perfil: si no lo pones, el usuario usa el del perfil. Ponlo explícitamente
> cuando quieras una excepción.

### 10.4 Simple Queue — límite fino por IP

> 🔴 En `/queue simple`, `max-limit` y `limit-at` van en orden **subida/bajada** (upload/download),
> y el **objetivo** se interpreta así: si la **IP origen** coincide con el target, es **subida**;
> si coincide el **destino**, es **bajada**.

```routeros
/queue simple print
/queue simple print stats

# Limitar un cliente concreto
/queue simple add \
  name=limite-cliente \
  target=192.168.77.100/32 \
  max-limit=1M/5M \
  limit-at=512k/2M

# Limitar toda la red del hotspot
/queue simple add \
  name=limite-hs \
  target=192.168.77.0/24 \
  max-limit=5M/20M

# Cola de reserva (deja ancho de banda libre)
/queue simple add name=reserva target=0.0.0.0/0 max-limit=20M/40M
```

> ⚠️ **Orden importa:** las simple queues se evalúan de arriba abajo y gana la **primera** que
> coincide. Pon siempre la regla específica **antes** de la general, o la general se comerá todo el
> tráfico.

### 10.5 Queue Tree — QoS con prioridad

```routeros
/queue type add name=pcq-down kind=pcq pcq-rate=1M pcq-classifier=dst-address
/queue type add name=pcq-up   kind=pcq pcq-rate=512k pcq-classifier=src-address

/queue tree add parent=global queue=pcq-up packet-mark=hs-upload
/queue tree add parent=global queue=pcq-down packet-mark=hs-download
```

### 10.6 Ver el consumo real

```routeros
/queue simple print stats
/queue tree print stats
/queue simple print stats where name="limite-cliente"
```

---

## 11. Walled-garden

El walled-garden es la lista de destinos **accesibles sin autenticarse** (típicamente los servidores
de DNS, NTP y actualización del portal).

### 11.1 Sintaxis

```routeros
/ip hotspot walled-garden print
/ip hotspot walled-garden print detail
```

| Propiedad | Significado |
|---|---|
| `dst-host` | Dominio o IP de destino. |
| `dst-port` | Puerto(s) de destino. |
| `src-address` | IP/rango de origen que puede acceder. |
| `method` | Método HTTP (GET, POST, CONNECT...). |
| `path` | Ruta URL. |
| `action` | **allow** (permitir) o **deny** (bloquear). |
| `server` | Servidor de hotspot al que aplica. |

### 11.2 Ejemplos

```routeros
# Permitir DNS del MikroTik
/ip hotspot walled-garden add dst-host=192.168.77.254 action=allow

# Permitir DNS público
/ip hotspot walled-garden add dst-host=1.1.1.1 dst-port=53 action=allow
/ip hotspot walled-garden add dst-host=8.8.8.8 dst-port=53 action=allow

# Permitir NTP
/ip hotspot walled-garden add dst-host=pool.ntp.org dst-port=123 action=allow

# Bloquear un sitio problemático
/ip hotspot walled-garden add dst-host=anuncios.trafico-suspecho.com action=deny
```

### 11.3 Walled-garden por IP (con listas de direcciones)

```routeros
/ip firewall address-list add list=permitidos-dns address=1.1.1.1
/ip firewall address-list add list=permitidos-dns address=8.8.8.8

/ip hotspot walled-garden add src-address=192.168.77.0/24 \
  dst-address=1.1.1.1-1.1.1.1 dst-port=53 action=allow
```

### 11.4 Ver qué se está usando

```routeros
/ip hotspot walled-garden print
# La columna 'hits' muestra cuántas veces se акivó cada regla
```

---

## 12. IP binding

Vincula permanentemente una MAC a una IP, o la marca como **bypassed** (salta el portal) o **blocked**.

```routeros
/ip hotspot ip-binding print
```

| Propiedad | Significado |
|---|---|
| `mac-address` | MAC a vincular. |
| `address` | Rango de IP de origen. |
| `to-address` | IP a asignar. |
| `type` | **regular** / **bypassed** / **blocked**. |
| `server` | Servidor de hotspot. |

```routeros
# MAC fija con IP fija
/ip hotspot ip-binding add \
  mac-address=AA:BB:CC:DD:EE:FF \
  address=192.168.77.150 \
  to-address=192.168.77.150 \
  type=regular

# Dispositivo que debe saltarse el portal (impresora, cámara IP)
/ip hotspot ip-binding add mac-address=11:22:33:44:55:66 type=bypassed

# Bloquear un dispositivo
/ip hotspot ip-binding add mac-address=99:88:77:66:55:44 type=blocked

/ip hotspot ip-binding remove [find mac-address="AA:BB:CC:DD:EE:FF"]
```

> 💡 `bypassed` es muy útil en un laboratorio: una impresora o una cámara no debería ver el portal.

---

## 13. Cookies y sesiones

### 13.1 Ver cookies

```routeros
/ip hotspot cookie print
/ip hotspot cookie print detail
```

### 13.2 Invalidar cookies (forzar re-login de todos)

```routeros
/ip hotspot cookie remove [find]
```

### 13.3 Forzar re-login de un usuario

```routeros
/ip hotspot active remove [find user="cliente"]
/ip hotspot cookie remove [find user="cliente"]
```

### 13.4 Ver sesiones activas

```routeros
/ip hotspot active print
/ip hotspot active print detail
/ip hotspot active print stats
```

| Columna | Significado |
|---|---|
| `user` | Usuario autenticado. |
| `address` | IP del cliente. |
| `mac-address` | MAC del cliente. |
| `login-by` | Método usado (cookie, http-chap, mac...). |
| `uptime` | Tiempo desde el login. |
| `session-time-left` | Tiempo restante de sesión. |
| `idle-time` | Tiempo sin tráfico. |
| `bytes-in/out` | Tráfico de la sesión. |

### 13.5 Ver todos los hosts (autorizados y no)

```routeros
/ip hotspot host print
/ip hotspot host print detail
```

---

## 14. Scripts on-login / on-logout

Se configuran en el **perfil de usuario** y se ejecutan automáticamente.

### 14.1 Variables disponibles

| Variable | Contenido |
|---|---|
| `$user` / `$username` | Nombre del usuario. |
| `$address` | IP del cliente. |
| `$mac-address` | MAC del cliente. |
| `$interface` | Interfaz donde se conectó. |
| `$cause` | Causa de la desconexión (solo en on-logout). |
| `$uptime-secs` | Duración final de la sesión (solo on-logout). |
| `$bytes-in` / `$bytes-out` | Bytes transferidos (solo on-logout). |
| `$packets-in` / `$packets-out` | Paquetes transferidos (solo on-logout). |

### 14.2 Ejemplos

```routeros
# on-login: log simple
/ip hotspot user profile set [find name="perfil-gratis"] on-login={:log info "Login: $user desde $address ($mac-address)"}

# on-login: poner la IP en una address-list para las colas
/ip hotspot user profile set [find name="perfil-premium"] on-login={:log info "Login: $user desde $address ($mac-address)"}

# on-login: apagar una interfaz para clientes de pago
/ip hotspot user profile set [find name="perfil-premium"] on-login={/interface disable ether3}

# on-logout: log con estadísticas
/ip hotspot user profile set [find name="perfil-gratis"] on-logout={:log info "Logout: $user, causa=$cause, duracion=$uptime-secs s, descargado=$bytes-out B"}
```

### 14.3 Script avanzado con address-list

```routeros
/ip hotspot user profile add name=perfil-markado on-login={
  :local ip $address
  /ip firewall address-list add list=premium address=$ip timeout=8h
}
```

---

## 15. RADIUS

Para producción, delega la autenticación a un servidor RADIUS (FreeRADIUS, MikroTik Identity, etc.).

### 15.1 Activar RADIUS en el hotspot

```routeros
/ip hotspot profile set [find name="hsprof1"] use-radius=yes radius-accounting=yes
```

### 15.2 Configurar el cliente RADIUS

```routeros
/radius add address=192.168.77.10 secret=CLAVE_RADIUS src-address=192.168.77.254 \
    service=hotspot,ppp

/radius print
/radius print detail
```

### 15.3 Ajustar los tiempos por RADIUS

El servidor RADIUS puede sobrescribir los tiempos del perfil mediante los atributos:

| Atributo RADIUS | Efecto |
|---|---|
| `Session-Timeout` | Sobrescribe `session-timeout`. |
| `Idle-Timeout` | Sobrescribe `idle-timeout`. |
| `Mikrotik-Rate-Limit` | Sobrescribe el límite de velocidad. |
| `Port-Limit` | Sobrescribe `shared-users`. |

```routeros
# El hotspot aplica los valores que llegan del RADIUS; el perfil queda como default
/ip hotspot profile set hsprof1 use-radius=yes
```

### 15.4 Atributos MikroTik útiles con RADIUS

| Atributo | Uso |
|---|---|
| `Mikrotik-Rate-Limit` | Límite de velocidad por suscriptor. |
| `Mikrotik-Recv-Limit` / `Mikrotik-Xmit-Limit` | Cuotas de bytes. |
| `Mikrotik-Group` | Perfil de hotspot local que se aplica. |
| `WISPr-Redirection-URL` | Redirección tras login. |
| `WISPr-Bandwidth-Max-Down` / `-Up` | Ancho de banda máximo. |

---

## 16. Diagnóstico y monitoreo

### 16.1 Estado general del router

```routeros
/system resource print
/system identity print
/interface print
/ip address print
/ip route print
```

### 16.2 Ver el tráfico en vivo

```routeros
/interface monitor-traffic ether2 once
/interface monitor-traffic ether2
```

### 16.3 Diagnóstico de red

```routeros
/ping 1.1.1.1 count=3
/ping 192.168.77.254 count=3
/ping 192.168.77.100 count=3 src-address=192.168.77.254

/tool fetch url="http://neverssl.com" mode=http dst-path=test.html
/file print where name=test.html
/file remove [find name="test.html"]
```

### 16.4 Test de velocidad

```routeros
/tool speed-test address=speedtest.example.net
/tool bandwidth-test address=speedtest.example.net direction=both
```

> ⚠️ En el CHR **sin licencia** el test está limitado a 1 Mbps. Es normal.

### 16.5 Logs del hotspot

```routeros
/log print where topics~"hotspot"
/log print where message~"cliente"
/log print where topics~"firewall"
```

### 16.6 Diagnóstico por síntoma

| Síntoma | Comando de diagnóstico | Causa probable |
|---|---|---|
| El celular no ve el SSID | `iw dev wlp59s0 info` (host) | Problema de hostapd, no del CHR. Ver doc 00 §12.1 |
| Se conecta pero sin IP | `/ip dhcp-server lease print` | DHCP del CHR no corre, o pool agotado. |
| El portal no carga | `curl -I http://192.168.77.254/login` (host) | `dns-name` mal configurado, o hotspot parado. |
| El login no hace nada | `/ip hotspot profile print detail` | El formulario apunta a un `dns-name` que no resuelve. |
| Autentica pero no navega | `/ping 1.1.1.1 count=3` | Falta NAT de salida, o el CHR no tiene Internet. |
| Se desconecta solo | `/ip hotspot active print detail` | `idle-timeout` o `keepalive-timeout` demasiado agresivos. |
| Va lento | `/queue simple print stats` | Colas mal configuradas o límite de la licencia CHR. |

### 16.7 Comandos de inspección profunda

```routeros
# Ver las reglas NAT dinámicas que crea el hotspot
/ip firewall nat print where dynamic=yes

# Ver la tabla de conexión
/ip firewall connection print count-only

# Ver los marcadores mangle
/ip firewall mangle print stats

# Ver qué reglas del firewall están contando
/ip firewall filter print stats

# Ver todos los DHCP leases con detalle
/ip dhcp-server lease print detail

# Ver el estado de los servicios
/ip service print

# Ver los puertos abiertos desde fuera
/ip firewall filter print where chain=input
```

---

## 17. Backup, export e import

### 17.1 Export de configuración (texto)

```routeros
/system export
```

Guardar a archivo:

```routeros
/system export file=backup-lab
/file print where name="backup-lab.rsc"
```

> El export **omite contraseñas** (`hide-sensitive`). Al importar, las contraseñas no se restauran.

### 17.2 Backup binario (sí incluye contraseñas)

```routeros
/system backup save name=backup-lab
/file print where name="backup-lab.backup"

/# Restaurar (requiere reboot)
/system backup load name=backup-lab
/system reboot
```

### 17.3 Importar

```routeros
/import file-name=backup-lab.rsc
```

Opcionalmente en modo simulación para ver qué haría:

```routeros
/import file-name=backup-lab.rsc dry-run=yes
```

### 17.4 Automatizar un backup diario

```routeros
/system script add name=backup-diario source={
  /system backup save name=backup-diario
  /file print where name="backup-diario.backup"
}

/system scheduler add name=backup-diario \
    interval=1d start-time=03:00:00 \
    on-event="/system script run backup-diario" \
    policy=read,write,test,policy
```

### 17.5 Descargar el backup al host

```bash
scp -P 2222 admin@127.0.0.1:/backup-lab.backup ./
```

---

## 18. Script completo del laboratorio

Guárdalo como `hotspot-lab.rsc` y ejecútalo en un CHR limpio con
`/import file-name=hotspot-lab.rsc`.

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

# --- Perfil del servidor hotspot ---
/ip hotspot profile add \
  name=hsprof1 \
  hotspot-address=192.168.77.254 \
  dns-name="" \
  html-directory=hotspot

# --- Servidor hotspot ---
/ip hotspot add \
  name=hotspot1 \
  interface=ether2 \
  address-pool=pool-lan \
  profile=hsprof1 \
  idle-timeout=5m \
  login-timeout=2m \
  keepalive-timeout=30s \
  disabled=no

# --- Perfiles de usuario ---
/ip hotspot user profile add \
  name=perfil-gratis \
  shared-users=1 \
  session-timeout=1h \
  idle-timeout=10m \
  keepalive-timeout=30s \
  mac-cookie-timeout=1d \
  rate-limit=512k/2M

/ip hotspot user profile add \
  name=perfil-premium \
  shared-users=3 \
  session-timeout=8h \
  idle-timeout=20m \
  keepalive-timeout=2m \
  mac-cookie-timeout=3d \
  rate-limit=5M/20M

# --- Usuario de prueba ---
/ip hotspot user add \
  name=cliente \
  password=cliente123 \
  profile=perfil-gratis \
  comment="Usuario de prueba"

# --- Quitar admin de hotspot sin clave (si existe) ---
:if ([:len [/ip hotspot user find name="admin"]] > 0) do={
  /ip hotspot user remove [find name="admin"]
}

# --- Walled garden ---
/ip hotspot walled-garden add dst-host=192.168.77.254 action=allow
/ip hotspot walled-garden add dst-host=1.1.1.1 dst-port=53 action=allow
/ip hotspot walled-garden add dst-host=8.8.8.8 dst-port=53 action=allow

# --- Opcional: DNS con nombre wifi.dev (ver doc 00, seccion 12.4) ---
# /ip dns set allow-remote-requests=yes servers=1.1.1.1,8.8.8.8
# /ip dns static add name=wifi.dev address=192.168.77.254
# /ip dhcp-server network set [find address="192.168.77.0/24"] dns-server=192.168.77.254
```

---

## 19. Cheat sheet

### Ver estado

```routeros
/ip hotspot print detail          /ip hotspot active print detail
/ip hotspot user print           /ip hotspot host print
/ip hotspot profile print        /ip hotspot user profile print
/ip hotspot cookie print         /ip hotspot walled-garden print
/ip hotspot ip-binding print     /ip dhcp-server lease print
/log print where topics~"hotspot"
```

### Gestionar sesiones

```routeros
/ip hotspot active remove [find user="cliente"]   # cerrar la sesion de uno
/ip hotspot active remove [find]                  # cerrar todas
/ip hotspot cookie remove [find]                  # invalidar todas las cookies
/ip hotspot host remove [find dynamic]            # limpiar hosts huerfanos
```

### Cambiar tiempos (lo más frecuente)

```routeros
# Duracion maxima de sesion
/ip hotspot user profile set [find name="perfil-premium"] session-timeout=8h

# Desconectar por inactividad
/ip hotspot user profile set [find name="perfil-premium"] idle-timeout=20m

# Tiempo que un no-autenticado ocupa una IP
/ip hotspot set [find name="hotspot1"] idle-timeout=5m

# Cookie del portal
/ip hotspot profile set [find name="hsprof1"] http-cookie-lifetime=2h
```

### Velocidad

```routeros
# Perfil (orden: subida/bajada)
/ip hotspot user profile set [find name="perfil-premium"] rate-limit=5M/20M

# Usuario concreto
/ip hotspot user set [find name="cliente"] rate-limit=256k/512k

# Simple queue (orden: subida/bajada)
/queue simple set [find name="limite-cliente"] max-limit=1M/5M
```

### Diagnóstico rápido

```routeros
/ping 1.1.1.1 count=3
/tool fetch url="http://neverssl.com" mode=http
/interface monitor-traffic ether2 once
/ip firewall nat print where dynamic=yes
```

### Apagado seguro

```routeros
/system backup save name=antes-de-cambiar
/system export file=antes-de-cambiar
```
