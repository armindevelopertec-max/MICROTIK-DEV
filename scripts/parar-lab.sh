#!/usr/bin/env bash
# ============================================================
# parar-lab.sh
# Detiene el laboratorio MikroTik CHR + Hotspot WiFi de forma ordenada.
#
# Uso:
#   ./parar-lab.sh          # detiene y restaura la laptop
#   ./parar-lab.sh --full   # ademas borra el tap y el bridge
# ============================================================
set -euo pipefail

BR="${BR:-br-mikrotik}"
TAP="${TAP:-tap-mikrotik}"
AP_IF="${AP_IF:-}"
UPLINK_IF="${UPLINK_IF:-}"

log()  { printf '\n\033[1;36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[AVISO]\033[0m %s\n' "$*"; }

FULL=0
[[ "${1:-}" == "--full" ]] && FULL=1

sudo -v

log "Cerrando QEMU"
pkill -f qemu-system-x86_64 2>/dev/null && log "QEMU detenido" || warn "QEMU no estaba corriendo"

log "Deteniendo panel web"
pkill -f "web/app.py" 2>/dev/null && log "Panel web detenido" || warn "Panel web no estaba corriendo"

# Descubrir que interfaz era el AP ANTES de matar hostapd
if [[ -z "$AP_IF" ]]; then
  AP_IF="$(sudo hostapd_cli status 2>/dev/null | awk -F= '/^interface=/{print $2}')" || true
fi

log "Deteniendo hostapd"
sudo pkill -x hostapd 2>/dev/null && log "hostapd detenido" || warn "hostapd no estaba corriendo"

if [[ -n "$AP_IF" ]]; then
  log "Devolviendo $AP_IF a NetworkManager"
  sudo nmcli device set "$AP_IF" managed yes 2>/dev/null || true
  sudo nmcli device connect "$AP_IF" 2>/dev/null || true
fi

if [[ -n "$UPLINK_IF" ]]; then
  log "Reconectando $UPLINK_IF"
  sudo nmcli device connect "$UPLINK_IF" 2>/dev/null || true
fi

if [[ $FULL -eq 1 ]]; then
  log "Eliminando $TAP"
  sudo ip link del "$TAP" 2>/dev/null || true
  log "Eliminando $BR"
  sudo nmcli connection down "$BR" 2>/dev/null || true
  sudo nmcli connection delete "$BR" 2>/dev/null || true
fi

log "Listo"
