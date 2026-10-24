#!/usr/bin/env bash
# ============================================================
# preparar-red.sh  (requiere root)
#
# Deja lista la parte privilegiada del laboratorio:
#   1. Comprueba que hay ruta a Internet por el uplink (USB)
#   2. Libera la radio interna para modo AP
#   3. Prepara br-mikrotik (STP off) y tap-mikrotik
#   4. Arranca hostapd (SSID MIKROTIK-LAB)
#
# NO arranca QEMU ni el panel web: de eso se encarga
# arrancar-todo.sh como usuario normal.
#
# Uso:
#   sudo ./scripts/preparar-red.sh
#
# Variables opcionales:
#   AP_IF=wlp59s0  UPLINK_IF=wlp0s20f0u1  BR=br-mikrotik  TAP=tap-mikrotik
#   AP_CONF=/etc/hostapd/mikrotik-lab.conf
# ============================================================
set -euo pipefail

[[ ${EUID:-$(id -u)} -eq 0 ]] || {
  echo "ERROR: ejecuta este script con sudo." >&2
  exit 1
}

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BR="${BR:-br-mikrotik}"
TAP="${TAP:-tap-mikrotik}"
AP_IF="${AP_IF:-wlp59s0}"
UPLINK_IF="${UPLINK_IF:-wlp0s20f0u1}"
AP_CONF="${AP_CONF:-/etc/hostapd/mikrotik-lab.conf}"
USUARIO="${SUDO_USER:-${USUARIO:-armintec}}"

log()  { printf '\033[1;36m[red]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[red]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[red]\033[0m %s\n' "$*" >&2; exit 1; }

[[ -f "$AP_CONF" ]] || die "No existe $AP_CONF"

ruta_actual() {
  ip route show default 2>/dev/null |
    awk '/^default/{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}'
}

# ------------------------------------------------------------
log "Comprobando salida a Internet"
for _ in $(seq 1 20); do
  [[ -n "$(ruta_actual)" ]] && break
  nmcli device connect "$UPLINK_IF" >/dev/null 2>&1 || true
  sleep 1
done

UP_NOW="$(ruta_actual)"
[[ -n "$UP_NOW" ]] || die "No hay ruta por defecto. Conecta Internet por $UPLINK_IF."

if [[ "$UP_NOW" == "$AP_IF" ]]; then
  warn "La ruta por defecto está en $AP_IF (la radio que debe ser AP)."
  warn "Intentando pasar el uplink a $UPLINK_IF..."
  nmcli device connect "$UPLINK_IF" >/dev/null 2>&1 || true
  for _ in $(seq 1 15); do
    UP_NOW="$(ruta_actual)"
    [[ "$UP_NOW" != "$AP_IF" ]] && break
    sleep 1
  done
  [[ "$UP_NOW" != "$AP_IF" ]] || die \
    "El uplink sigue en $AP_IF. Conecta el adaptador USB a la red con Internet."
fi
log "Uplink: $UP_NOW"

# ------------------------------------------------------------
log "Liberando $AP_IF para modo AP"
nmcli device disconnect "$AP_IF" >/dev/null 2>&1 || true
nmcli device set "$AP_IF" managed no >/dev/null 2>&1 || true
sleep 1

# ------------------------------------------------------------
log "Preparando bridge $BR"
ip link set "$BR" type bridge stp_state 0 forward_delay 0 2>/dev/null || true
ip link set "$BR" up

# ------------------------------------------------------------
log "Preparando tap $TAP"
if ! ip link show "$TAP" >/dev/null 2>&1; then
  ip tuntap add dev "$TAP" mode tap user "$USUARIO" persist on
  log "Tap creado (propietario: $USUARIO)"
else
  log "Tap ya existente; se reutiliza (no se destruye para no romper QEMU)"
fi
ip link set "$TAP" up
ip link set "$TAP" master "$BR"

# ------------------------------------------------------------
log "Arrancando hostapd ($AP_IF)"
if pgrep -x hostapd >/dev/null 2>&1; then
  pkill -x hostapd || true
  sleep 1
fi
hostapd -B "$AP_CONF"

# hostapd añade la interfaz al bridge; esperamos forwarding
for _ in $(seq 1 20); do
  bridge link show 2>/dev/null | grep -q "^[^:]*$AP_IF.*state forwarding" && break
  sleep 1
done

ESTADO_AP="$(hostapd_cli -i "$AP_IF" status 2>/dev/null | awk -F= '/^state=/{print $2}')"
[[ "$ESTADO_AP" == "ENABLED" ]] || die "hostapd no quedó habilitado (estado: ${ESTADO_AP:-desconocido})"

log "Bridge:"
bridge link show | sed 's/^/    /'
log "AP $AP_IF: ENABLED (SSID MIKROTIK-LAB)"
