#!/usr/bin/env bash
# ============================================================
# arrancar-todo.sh
#
# Levanta TODO el laboratorio de una sola vez:
#   1. Red + bridge + tap + hostapd  (con sudo, vía preparar-red.sh)
#   2. CHR en QEMU (SSH 2222, WinBox 8291, API 8728)
#   3. Panel web de tickets en Python (Flask, 127.0.0.1:5000)
#
# Es idempotente: si algo ya está corriendo, no lo duplica.
#
# Uso:
#   ./scripts/arrancar-todo.sh
#
# Al final imprime un resumen con URLs y comandos.
# Logs en ./logs/
# ============================================================
set -uo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DISK="${DISK:-$BASE_DIR/chr-disk.qcow2}"
LOG_DIR="$BASE_DIR/logs"
MEM="${MEM:-512}"
CPUS="${CPUS:-2}"
WEB_PORT="${WEB_PORT:-5000}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
mkdir -p "$LOG_DIR"

log()  { printf '\033[1;36m[lab]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[lab]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[lab]\033[0m %s\n' "$*" >&2; exit 1; }

puerto_abierto() { ss -ltn 2>/dev/null | grep -q ":$1[[:space:]]"; }

esperar_puerto() {
  local puerto="$1" segundos="${2:-60}"
  for _ in $(seq 1 "$segundos"); do
    puerto_abierto "$puerto" && return 0
    sleep 1
  done
  return 1
}

[[ -f "$DISK" ]] || die "No existe el disco $DISK"

# ------------------------------------------------------------
# 1. Parte privilegiada: red, bridge, tap y hostapd
# ------------------------------------------------------------
log "Preparando red y AP WiFi (pide sudo)"
sudo "$BASE_DIR/scripts/preparar-red.sh" || die "Falló la preparación de red"

# ------------------------------------------------------------
# 2. CHR en QEMU
# ------------------------------------------------------------
if pgrep -f "qemu-system-x86_64.*$(basename "$DISK")" >/dev/null 2>&1; then
  log "QEMU ya estaba corriendo"
else
  if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    DISPLAY_OPT=(-display gtk)
  else
    DISPLAY_OPT=(-display none)
    warn "Sin entorno gráfico: QEMU arranca sin ventana"
  fi

  log "Arrancando QEMU (CHR)"
  nohup qemu-system-x86_64 \
    -enable-kvm \
    -machine type=pc \
    -cpu host \
    -smp "$CPUS" \
    -m "$MEM" \
    -drive file="$DISK",format=qcow2 \
    -boot c \
    -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:2222-:22,hostfwd=tcp:127.0.0.1:8291-:8291,hostfwd=tcp:127.0.0.1:8728-:8728 \
    -netdev tap,id=lan0,ifname=tap-mikrotik,script=no,downscript=no \
    -device virtio-net-pci,netdev=lan0 \
    "${DISPLAY_OPT[@]}" \
    >>"$LOG_DIR/qemu.log" 2>&1 &
fi

if esperar_puerto 2222 60 && esperar_puerto 8728 20; then
  log "CHR arriba: SSH 2222, WinBox 8291, API 8728"
else
  die "QEMU no abrió los puertos. Revisa $LOG_DIR/qemu.log"
fi

# ------------------------------------------------------------
# 3. Panel web (Flask)
# ------------------------------------------------------------
if pgrep -f "web/app.py" >/dev/null 2>&1; then
  log "Panel web ya estaba corriendo"
else
  if [[ ! -x "$BASE_DIR/.venv/bin/python" ]]; then
    warn "No existe .venv; el panel web no se arranca."
    warn "Créalo con: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  else
    log "Arrancando panel web"
    nohup env WEB_HOST="$WEB_HOST" WEB_PORT="$WEB_PORT" \
      "$BASE_DIR/scripts/admin-web" \
      >>"$LOG_DIR/admin-web.log" 2>&1 &
  fi
fi

if esperar_puerto "$WEB_PORT" 30; then
  log "Panel web arriba"
else
  warn "El panel web no abrió el puerto $WEB_PORT. Revisa $LOG_DIR/admin-web.log"
fi

# ------------------------------------------------------------
# 4. Resumen
# ------------------------------------------------------------
cat <<EOF

$(log "Laboratorio listo")

  SSID WiFi      : MIKROTIK-LAB  (clave: mikrotik123)
  Portal         : http://192.168.77.254/login
  Panel web      : http://$WEB_HOST:$WEB_PORT
  CHR SSH        : ssh -p 2222 admin@127.0.0.1
  CHR WinBox     : 127.0.0.1:8291
  CHR API        : 127.0.0.1:8728
  Logs           : $LOG_DIR/

  Para parar todo : ./scripts/parar-lab.sh

EOF
