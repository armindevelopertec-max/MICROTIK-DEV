#!/usr/bin/env bash
# ============================================================
# iniciar-lab.sh
# Levanta el laboratorio MikroTik CHR + Hotspot WiFi.
#
#   1. Asegura Internet por un adaptador (uplink)
#   2. Prepara el bridge br-mikrotik y el tap tap-mikrotik
#   3. Libera el adaptador WiFi para modo AP y arranca hostapd
#   4. Arranca QEMU con el CHR (SSH 2222, API 8728 y WinBox 8291 en localhost)
#
# Uso:
#   ./iniciar-lab.sh
#
# Variables de entorno (opcionales) para forzar interfaces:
#   AP_IF=wlp59s0        interfaz que se usara como Access Point
#   UPLINK_IF=wlp0s20f0u1  interfaz que dara salida a Internet
#   DISK=chr-disk.qcow2  imagen de disco del CHR
#   AP_CONF=/etc/hostapd/mikrotik-lab.conf
# ============================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DISK="${DISK:-$BASE_DIR/chr-disk.qcow2}"
AP_CONF="${AP_CONF:-/etc/hostapd/mikrotik-lab.conf}"
BR="${BR:-br-mikrotik}"
TAP="${TAP:-tap-mikrotik}"
AP_IF="${AP_IF:-}"
UPLINK_IF="${UPLINK_IF:-}"
MEM="${MEM:-512}"
CPUS="${CPUS:-2}"

log()  { printf '\n\033[1;36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[AVISO]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

# ------------------------------------------------------------
log "Comprobando privilegios"
sudo -v
[[ -f "$DISK" ]]    || die "No existe el disco $DISK"
[[ -f "$AP_CONF" ]] || die "No existe $AP_CONF (ver docs/00-ENTORNO-Y-PREPARACION.md)"

# ------------------------------------------------------------
# Descubre que interfaces soportan modo AP
#
# 'iw dev' indenta con tabulador, por eso el patron es $1=="Interface"
# y no /^Interface/.
# ------------------------------------------------------------
wifi_aps() {
  local phy phyid phyindex iface wiphy
  # 'iw dev' lista los phys como 'phy#0', pero 'iw phy' espera 'phy0' (sin '#')
  for phy in $(iw dev 2>/dev/null | awk '$1 ~ /^phy#/{print $1}'); do
    phyid="${phy//\#/}"        # 'phy#0' -> 'phy0'  (argumento valido de 'iw phy')
    phyindex="${phyid#phy}"    # 'phy0'  -> '0'
    iw phy "$phyid" info 2>/dev/null | grep -qE '^[[:space:]]+\*[[:space:]]+AP$' || continue
    for iface in $(wifi_ifaces); do
      # 'iw dev <iface> info' reporta 'wiphy N', no 'phy#N'
      wiphy="$(iw dev "$iface" info 2>/dev/null | awk '$1=="wiphy"{print $2; exit}')"
      [[ "$wiphy" == "$phyindex" ]] || continue
      echo "$iface"
    done
  done
}

detect_uplink() {
  # interfaz que hoy tiene la ruta por defecto
  ip route show default 2>/dev/null | awk '/^default/{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}'
}

detect_aps() { wifi_aps | sort -u; }

# Todas las interfaces WiFi, sin importar el modo
wifi_ifaces() {
  iw dev 2>/dev/null | awk '$1=="Interface"{print $2}'
}

# ------------------------------------------------------------
log "Detectando interfaces"
UPLINK_IF="${UPLINK_IF:-$(detect_uplink)}"
mapfile -t APS < <(detect_aps)

if [[ -z "$AP_IF" ]]; then
  # Preferir un AP que NO sea el uplink
  for i in "${APS[@]}"; do
    [[ "$i" == "$UPLINK_IF" ]] && continue
    AP_IF="$i"; break
  done
  # Si no hay ninguno libre, coger el primero disponible
  if [[ -z "$AP_IF" && ${#APS[@]} -gt 0 ]]; then
    AP_IF="${APS[0]}"
  fi
fi

log "Uplink (Internet): ${UPLINK_IF:-<none>}"
log "AP (hostapd):      ${AP_IF:-<none>}"
log "Soportan modo AP:  ${APS[*]:-<ninguna>}"

[[ -n "$UPLINK_IF" ]] || die "No hay interfaz con ruta por defecto (conectate a Internet primero)"
[[ -n "$AP_IF" ]]      || die "Ninguna interfaz WiFi soporta modo AP. Conecta un adaptador compatible."

if [[ "$AP_IF" == "$UPLINK_IF" ]]; then
  die "La unica radio WiFi ($AP_IF) es a la vez uplink y AP.
     El driver no soporta AP+STA simultaneos ('Operation already in progress').
     Conecta un SEGUNDO adaptador WiFi USB y repite, o usa un AP externo por Ethernet."
fi

# ------------------------------------------------------------
log "Preparando bridge $BR"
if ! nmcli -t -f NAME connection show | grep -qx "$BR"; then
  sudo nmcli connection add type bridge ifname "$BR" con-name "$BR"
fi
# STP desactivado: los puertos pasan a 'forwarding' de inmediato
sudo nmcli connection modify "$BR" \
  ipv4.method manual \
  ipv4.addresses 192.168.77.1/24 \
  ipv6.method disabled \
  bridge.stp no
sudo nmcli connection up "$BR" 2>/dev/null || true
sudo ip link set "$BR" up
# Refuerzo en el kernel: NetworkManager no siempre aplica stp=no al reactivar
sudo ip link set "$BR" type bridge stp_state 0 forward_delay 0

# ------------------------------------------------------------
log "Preparando tap $TAP"
if ! ip link show "$TAP" &>/dev/null; then
  sudo ip tuntap add dev "$TAP" mode tap user "${SUDO_USER:-$USER}" persist on
fi
sudo ip link set "$TAP" up
sudo ip link set "$TAP" master "$BR"

# ------------------------------------------------------------
log "Asegurando Internet por $UPLINK_IF"
if ! ip route | grep -q '^default'; then
  sudo nmcli device connect "$UPLINK_IF" 2>/dev/null || true
fi
ip route | grep -q '^default' || die "No hay ruta por defecto tras intentar conectar $UPLINK_IF"

# ------------------------------------------------------------
log "Liberando $AP_IF para modo AP"
sudo nmcli device disconnect "$AP_IF" 2>/dev/null || true
sudo nmcli device set "$AP_IF" managed no 2>/dev/null || true

# ------------------------------------------------------------
log "Arrancando hostapd"
if pgrep -x hostapd >/dev/null; then
  sudo pkill -x hostapd || true
  sleep 1
fi
sudo hostapd -B "$AP_CONF"

# ------------------------------------------------------------
log "Esperando a que $TAP pase a forwarding"
for _ in $(seq 1 30); do
  bridge link show 2>/dev/null | grep -q "$TAP.*state forwarding" && break
  sleep 1
done
bridge link show 2>/dev/null | grep -q "$TAP.*state forwarding" \
  || warn "$TAP sigue sin 'forwarding'. Revisa STP del bridge (debe ser 'no')."

# ------------------------------------------------------------
log "Arrancando QEMU (CHR)"
if pgrep -f "qemu-system-x86_64.*$DISK" >/dev/null; then
  warn "QEMU ya estaba corriendo con $DISK"
else
  qemu-system-x86_64 \
    -enable-kvm \
    -machine type=pc \
    -cpu host \
    -smp "$CPUS" \
    -m "$MEM" \
    -drive file="$DISK",format=qcow2 \
    -boot c \
    -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:2222-:22,hostfwd=tcp:127.0.0.1:8291-:8291,hostfwd=tcp:127.0.0.1:8728-:8728 \
    -netdev tap,id=lan0,ifname="$TAP",script=no,downscript=no \
    -device virtio-net-pci,netdev=lan0 \
    -display gtk &
  sleep 3
fi

cat <<EOF

$(log "Laboratorio arrancado")

  AP (SSID)      : $(sudo hostapd_cli -i "$AP_IF" status 2>/dev/null | awk -F= '/^ssid=/{print $2}' || grep -E '^ssid=' "$AP_CONF" | cut -d= -f2)
  Uplink         : $UPLINK_IF
  Bridge         : $BR (192.168.77.1/24)
  Tap            : $TAP
  CHR SSH        : ssh -p 2222 admin@127.0.0.1
  CHR API        : 127.0.0.1:8728
  CHR WinBox     : 127.0.0.1:8291
  Portal         : http://192.168.77.254/login

  Para detener:  ./scripts/parar-lab.sh
EOF
