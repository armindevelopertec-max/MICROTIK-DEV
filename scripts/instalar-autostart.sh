#!/usr/bin/env bash
# ============================================================
# instalar-autostart.sh
#
# Instala (o quita) el arranque automático del laboratorio al
# iniciar sesión en el escritorio, mediante ~/.config/autostart.
#
# Uso:
#   ./scripts/instalar-autostart.sh            # instalar
#   ./scripts/instalar-autostart.sh --quitar   # desinstalar
#
# Nota: el arranque abre una terminal para pedir la contraseña
# de sudo (hostapd y el bridge necesitan root). Si quieres que
# no pregunte, añade una regla NOPASSWD para preparar-red.sh;
# está explicado en docs/07-ARRANQUE-AUTOMATICO-Y-WEB.md
# ============================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
DESTINO="$AUTOSTART_DIR/mikrotik-lab.desktop"

if [[ "${1:-}" == "--quitar" ]]; then
  rm -f "$DESTINO"
  echo "Arranque automático eliminado: $DESTINO"
  exit 0
fi

mkdir -p "$AUTOSTART_DIR"
chmod +x "$BASE_DIR/scripts/arrancar-todo.sh" "$BASE_DIR/scripts/preparar-red.sh"

cat >"$DESTINO" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=MikroTik Lab
Comment=Levanta el hotspot MikroTik CHR, el AP WiFi y el panel web
Exec=$BASE_DIR/scripts/arrancar-todo.sh
Path=$BASE_DIR
Terminal=true
Icon=network-wireless
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=10
EOF
chmod +x "$DESTINO"

echo "Arranque automático instalado:"
echo "  $DESTINO"
echo
echo "Se ejecutará al iniciar sesión. Si quieres probarlo ahora:"
echo "  $BASE_DIR/scripts/arrancar-todo.sh"
