# ============================================================================
#  MICRO-TIK - Configuracion completa del CHR desde cero
#  RouterOS 7.x (probado en 7.24.5) - Laboratorio Hotspot + Tickets QR
# ============================================================================
#
#  QUE HACE
#    1. Identidad, contrasena de admin, NTP y servicios (SSH/WinBox/API)
#    2. WAN   : ether1 por DHCP (NAT de QEMU / NAT de VirtualBox / NAT de VMware)
#    3. LAN   : ether2 = 192.168.77.254/24
#    4. DHCP  : pool 192.168.77.100-199 + servidor en ether2
#    5. NAT   : salida a Internet por ether1
#    6. Hotspot: perfil + servidor + usuarios + walled-garden
#    7. Firewall de entrada minimo
#    8. Guarda backup y config exportada
#
#  ANTES DE EJECUTAR
#    - El CHR debe estar recien reseteado:
#         /system reset-configuration no-defaults=yes skip-backup=yes
#    - Ajusta la seccion 0 (PASSWORD, nombre, zona horaria).
#    - Si ya hay configuracion, ejecuta antes el bloque "LIMPIEZA" de
#      docs/09-RECONSTRUIR-DESDE-CERO.md
#
#  USO
#    Opcion A (recomendada): scp + /import file-name=mikrotik-lab-desde-cero.rsc
#    Opcion B: pegar todo esto en la terminal del CHR
#
#  ORDEN DE INTERFACES (igual en QEMU, VirtualBox y VMware)
#    ether1 = WAN (primera NIC, con NAT)
#    ether2 = LAN (segunda NIC, hacia el AP/hostapd o red interna)
# ============================================================================


# ============================================================================
# 0. PARAMETROS  <-- cambia esto si hace falta
# ============================================================================
# La contrasena debe coincidir con MIKROTIK_PASSWORD de tu archivo .env
# (el panel de tickets QR usa usuario admin + esta clave por la API 8728).
#
#   Identidad ......... MICRO-DEV-ROOT
#   Password admin .... Dahua2026
#   Red LAN ........... 192.168.77.0/24
#   IP del CHR (LAN) .. 192.168.77.254
#   Pool DHCP ......... 192.168.77.100 - 192.168.77.199
#   Portal ............ http://192.168.77.254/login
# ============================================================================


# ============================================================================
# 1. SISTEMA: identidad, usuario, hora, servicios
# ============================================================================
/system identity set name=MICRO-DEV-ROOT

# Contrasena del admin (la que usa tambien el panel por API)
/user set [find name=admin] password="Dahua2026"

# Zona horaria: descomenta y ajusta la tuya
# /system clock set time-zone-name=America/Mexico_City

# NTP (hora correcta = logs y sesiones del hotspot correctos)
/system ntp client set enabled=yes
/system ntp client servers add address=pool.ntp.org
/system ntp client servers add address=time.cloudflare.com

# Servicios de gestion. Se limitan a la LAN del hotspot y al enlace de
# gestion de la VM (10.0.2.0/24 en QEMU; en VirtualBox/VMware el NAT suele
# ser 10.0.2.0/24 o 192.168.x.0/24: agrega tu subred si hace falta).
/ip service disable telnet,ftp,www,api-ssl
/ip service enable ssh,winbox,api
/ip service set ssh     address=10.0.2.0/24,192.168.77.0/24
/ip service set winbox  address=10.0.2.0/24,192.168.77.0/24
/ip service set api     address=10.0.2.0/24,192.168.77.0/24 port=8728


# ============================================================================
# 2. WAN: ether1 por DHCP
#    QEMU (slirp) entrega 10.0.2.15/24, gw 10.0.2.2
#    VirtualBox NAT entrega 10.0.2.15/24
#    VMware NAT entrega normalmente 192.168.x.128/24
# ============================================================================
/ip dhcp-client add interface=ether1 disabled=no comment="WAN DHCP"

# Si tu WAN fuera IP fija en vez de DHCP, comenta la linea de arriba y usa:
# /ip address add address=TU_IP/MASCARA interface=ether1 comment="WAN fija"
# /ip route add gateway=TU_GATEWAY comment="Ruta por defecto"


# ============================================================================
# 3. LAN: ether2
# ============================================================================
/ip address add address=192.168.77.254/24 interface=ether2 comment="LAN HOTSPOT"


# ============================================================================
# 4. DHCP: pool + servidor + red
# ============================================================================
/ip pool add name=pool-lan ranges=192.168.77.100-192.168.77.199

/ip dhcp-server network add \
    address=192.168.77.0/24 \
    gateway=192.168.77.254 \
    dns-server=1.1.1.1,8.8.8.8 \
    comment="Red del hotspot"

/ip dhcp-server add \
    name=dhcp-lan \
    interface=ether2 \
    address-pool=pool-lan \
    lease-time=1h \
    disabled=no \
    comment="DHCP hotspot"


# ============================================================================
# 5. NAT: salida a Internet por ether1
# ============================================================================
/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade comment="NAT salida WAN"
/ip firewall nat add chain=srcnat src-address=192.168.77.0/24 action=masquerade comment="NAT hotspot"


# ============================================================================
# 6. HOTSPOT
# ============================================================================

# --- Perfil del servidor hotspot ---
# dns-name="" es intencional: el portal se abre por IP y evita el problema
# del DNS privado (DoT) de Android. Ver docs/00 seccion 12.4.
/ip hotspot profile add \
    name=hsprof1 \
    hotspot-address=192.168.77.254 \
    dns-name="" \
    html-directory=hotspot \
    login-by=http-chap,http-pap \
    http-cookie-lifetime=2h

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
    rate-limit=512k/2M \
    comment="Acceso basico"

/ip hotspot user profile add \
    name=perfil-premium \
    shared-users=3 \
    session-timeout=8h \
    idle-timeout=20m \
    keepalive-timeout=2m \
    mac-cookie-timeout=3d \
    rate-limit=5M/20M \
    comment="Acceso ampliado"

# Perfil que usa el generador de tickets QR (ticket_qr.py).
# Debe llamarse igual que MIKROTIK_PROFILE del .env.
/ip hotspot user profile add \
    name=qr-ticket \
    shared-users=1 \
    idle-timeout=10m \
    keepalive-timeout=2m \
    session-timeout=0s \
    add-mac-cookie=yes \
    comment="Tickets QR (limite por limit-uptime)"

# --- Usuario de prueba manual ---
/ip hotspot user add \
    name=cliente \
    password=cliente123 \
    profile=perfil-gratis \
    comment="Usuario de prueba"

# --- Quitar el usuario admin del hotspot si quedo sin contrasena ---
:if ([:len [/ip hotspot user find name="admin"]] > 0) do={
    /ip hotspot user remove [find name="admin"]
}

# --- Walled garden: lo que se permite SIN autenticarse ---
/ip hotspot walled-garden add dst-host=192.168.77.254 action=allow comment="Portal"
/ip hotspot walled-garden add dst-host=1.1.1.1 dst-port=53 action=allow comment="DNS 1"
/ip hotspot walled-garden add dst-host=8.8.8.8 dst-port=53 action=allow comment="DNS 2"


# ============================================================================
# 7. FIREWALL DE ENTRADA (minimo)
#    - El hotspot gestiona el forward de los clientes por si solo.
#    - Aqui solo protegemos el propio router.
#    - Si algo dejara de responder, desactiva/borra la ultima regla (drop).
# ============================================================================
/ip firewall filter add chain=input action=accept connection-state=established,related comment="Establecidas"
/ip firewall filter add chain=input action=drop connection-state=invalid comment="Invalidas"
/ip firewall filter add chain=input action=accept protocol=icmp comment="ICMP"
/ip firewall filter add chain=input action=accept in-interface=ether2 comment="Desde la LAN"
/ip firewall filter add chain=input action=accept src-address=10.0.2.0/24 comment="Gestion VM"
/ip firewall filter add chain=input action=drop comment="Drop resto de entrada"


# ============================================================================
# 8. RESPALDO INICIAL
# ============================================================================
/system backup save name=lab-inicial
/export file=lab-inicial


# ============================================================================
# 9. COMPROBACION
#    Revisa que TODO lo siguiente salga como se indica.
# ============================================================================
# /system identity print              -> name: MICRO-DEV-ROOT
# /ip address print                   -> ether1 10.0.2.15/24 (o la IP del NAT)
#                                        ether2 192.168.77.254/24
# /ip route print                     -> 0.0.0.0/0 via 10.0.2.2 (o tu gateway)
# /ip dhcp-server print               -> dhcp-lan disabled=no
# /ip hotspot print                   -> hotspot1 disabled=no
# /ip hotspot profile print           -> hsprof1
# /ip hotspot user print              -> cliente
# /ip hotspot user profile print      -> perfil-gratis, perfil-premium, qr-ticket
# /ip firewall nat print              -> 2 reglas masquerade
# /ping 1.1.1.1 count=4               -> 4 recibidos
#
# Desde el host (laptop):
#   ping -c 3 192.168.77.254
#   curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://192.168.77.254/login
#   -> debe responder HTTP 200
#
# Prueba de la API (la que usa el panel de tickets):
#   /ip service print where name=api   -> port 8728, enabled
#
# ============================================================================
:put "=========================================================="
:put " Configuracion aplicada. Revisa la seccion 9 del script."
:put " Portal: http://192.168.77.254/login"
:put "=========================================================="
