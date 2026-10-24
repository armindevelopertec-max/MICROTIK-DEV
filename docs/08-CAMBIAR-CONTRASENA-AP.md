# 08 — Cambiar la contraseña del AP (o dejarlo sin contraseña)

**Situación actual:** el AP `MIKROTIK-LAB` usa WPA2-PSK con la clave
`mikrotik123`.

**Objetivo de esta guía:** dejar el AP **sin contraseña** (red abierta) y,
además, saber cómo poner otra clave o revertir el cambio.

> ⚠️ **Leer antes de aplicar.** Una red WiFi abierta permite que **cualquiera**
> se asocie al AP y capture el tráfico de la red inalámbrica. El portal del
> hotspot sigue pidiendo usuario y contraseña, así que **no** se pierde el
> control de acceso a Internet, pero la capa WiFi deja de estar cifrada.
> Úsalo solo en un laboratorio o red controlada.

---

## 1. Dónde está la contraseña (y qué más hay que tocar)

| Dónde | Qué contiene | ¿Hay que cambiarlo? |
|---|---|---|
| `/etc/hostapd/mikrotik-lab.conf` | `wpa_passphrase=mikrotik123` | **Sí** (es la clave real del AP) |
| `.env` (`MIKROTIK_WIFI_PASSWORD`) | Clave que se imprime en los QR | Sí, si usas tickets QR |
| `scripts/ticket_qr.py` | Valor por defecto `mikrotik123` y formato del QR WiFi | Sí para que el QR sea válido en red abierta |
| `scripts/arrancar-todo.sh` | Texto del resumen final | Opcional (solo informativo) |
| Docs 00, 05, 06, 07 | Referencias a `mikrotik123` | Opcional (documentación) |

En hostapd **no existe** “contraseña vacía”. Para una red abierta hay que
cambiar el modo de seguridad:

- `wpa=2` + `wpa_passphrase=...` → WPA2 con clave.
- `wpa=0` (sin `wpa_passphrase`, `wpa_key_mgmt` ni `rsn_pairwise`) → **red abierta**.

Si dejas `wpa=2` y borras la clave, hostapd **no arranca**.

---

## 2. Opción A — Dejar el AP sin contraseña (red abierta)

### Paso 1. Hacer copia de seguridad

```bash
sudo cp /etc/hostapd/mikrotik-lab.conf /etc/hostapd/mikrotik-lab.conf.bak
```

### Paso 2. Editar la configuración

```bash
sudo nano /etc/hostapd/mikrotik-lab.conf
```

Deja el archivo **exactamente** así (los valores de país/canal son los actuales
de este equipo):

```ini
interface=wlp59s0
bridge=br-mikrotik
driver=nl80211
ssid=MIKROTIK-LAB
country_code=ES
ieee80211d=1
hw_mode=g
channel=11
ieee80211n=0
wmm_enabled=1
auth_algs=1
ignore_broadcast_ssid=0
wpa=0
ctrl_interface=/var/run/hostapd
ctrl_interface_group=0
```

Cambios respecto al archivo original:

```diff
-wpa=2
-wpa_passphrase=mikrotik123
-wpa_key_mgmt=WPA-PSK
-rsn_pairwise=CCMP
+wpa=0
```

> `auth_algs=1` es autenticación abierta; es lo correcto para una red sin clave.

### Paso 3. Reiniciar hostapd

```bash
sudo pkill -x hostapd
sleep 1
sudo hostapd -B /etc/hostapd/mikrotik-lab.conf
```

O, si prefieres el arranque completo del laboratorio:

```bash
./scripts/arrancar-todo.sh
```

### Paso 4. Verificar que quedó abierta

```bash
# Estado del AP
sudo hostapd_cli -i wlp59s0 status | grep -E 'state|ssid|channel'

# Debe mostrar wpa=0 y ningún key_mgmt
sudo hostapd_cli -i wlp59s0 get_config | grep -E '^(ssid|wpa|key_mgmt|rsn_pairwise_cipher)='

# La red debe aparecer SIN seguridad (-- / abierta)
nmcli -f SSID,SECURITY device wifi list ifname wlp0s20f0u1 | grep MIKROTIK-LAB
```

Resultado esperado:

```
state=ENABLED
ssid[0]=MIKROTIK-LAB
wpa=0
MIKROTIK-LAB    --
```

### Paso 5. Conectar un cliente

1. En el móvil, **olvida** la red `MIKROTIK-LAB` si ya la tenías guardada
   (si no, seguirá intentando usar la clave antigua).
2. Vuelve a conectarte: debe entrar **sin pedir contraseña**.
3. Abre el navegador; el portal debe salir solo o entrando a:
   `http://192.168.77.254/login`
4. Autentícate con un usuario del hotspot (`admin`, `Armindev`, `Daniel`, etc.).

---

## 3. Actualizar los tickets QR (importante si los usas)

Los QR de WiFi se generan en `scripts/ticket_qr.py`. La función actual **siempre**
genera un QR WPA:

```python
def wifi_qr_payload(ssid: str, password: str) -> str:
    return f"WIFI:T:WPA;S:{escapar_wifi(ssid)};P:{escapar_wifi(password)};;"
```

Con la red abierta eso sería incorrecto: el móvil intentaría conectarse con
WPA y una clave vacía. El formato correcto para red abierta es
`WIFI:T:nopass;S:MIKROTIK-LAB;;`.

### 3.1 Editar `scripts/ticket_qr.py`

Sustituye la función por:

```python
def wifi_qr_payload(ssid: str, password: str) -> str:
    if not password:
        return f"WIFI:T:nopass;S:{escapar_wifi(ssid)};;"
    return f"WIFI:T:WPA;S:{escapar_wifi(ssid)};P:{escapar_wifi(password)};;"
```

### 3.2 Editar `.env`

```bash
cp .env.example .env        # si aún no existe
nano .env
```

Deja la variable **vacía**:

```ini
MIKROTIK_WIFI_PASSWORD=
```

Si no existe `.env`, el programa usa el valor por defecto
`mikrotik123` de `scripts/ticket_qr.py`; en ese caso cambia también el valor
por defecto de `Config.wifi_password` (línea ~152) a `""`.

### 3.3 Verificar el QR

```bash
./scripts/ticket-qr crear -n 1 -t 1h
# Abre el PNG generado y comprueba que el QR WiFi dice:
# WIFI:T:nopass;S:MIKROTIK-LAB;;
```

---

## 4. Opción B — Poner otra contraseña (seguir con WPA2)

Si en el futuro quieres una clave distinta (no vacía), el mínimo de WPA2-PSK
es **8 caracteres** y el máximo 63.

```bash
# Generar una clave aleatoria de 16 caracteres
NUEVA=$(openssl rand -base64 12 | tr -d '/+=' | cut -c1-16)
echo "Nueva clave: $NUEVA"
```

Edita `/etc/hostapd/mikrotik-lab.conf`:

```ini
wpa=2
wpa_passphrase=LA_NUEVA_CLAVE
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
```

Reinicia y verifica:

```bash
sudo pkill -x hostapd && sleep 1
sudo hostapd -B /etc/hostapd/mikrotik-lab.conf
sudo hostapd_cli -i wlp59s0 get_config | grep -E '^wpa'
```

Actualiza también `.env` (`MIKROTIK_WIFI_PASSWORD=LA_NUEVA_CLAVE`) para que los
QR se generen con la clave correcta. Con contraseña no hace falta tocar la
función `wifi_qr_payload`.

---

## 5. Revertir al estado anterior

```bash
sudo cp /etc/hostapd/mikrotik-lab.conf.bak /etc/hostapd/mikrotik-lab.conf
sudo pkill -x hostapd
sleep 1
sudo hostapd -B /etc/hostapd/mikrotik-lab.conf
```

Verifica que volvió WPA2:

```bash
sudo hostapd_cli -i wlp59s0 get_config | grep -E '^(wpa|key_mgmt)='
# wpa=2
# key_mgmt=WPA-PSK
```

Y restaura `MIKROTIK_WIFI_PASSWORD=mikrotik123` en `.env`.

---

## 6. Resumen “cópialo y pégalo” (dejar sin contraseña)

```bash
# 1. Copia de seguridad
sudo cp /etc/hostapd/mikrotik-lab.conf /etc/hostapd/mikrotik-lab.conf.bak

# 2. Red abierta (wpa=0 y sin líneas de clave)
sudo sed -i \
  -e 's/^wpa=.*/wpa=0/' \
  -e '/^wpa_passphrase=/d' \
  -e '/^wpa_key_mgmt=/d' \
  -e '/^rsn_pairwise=/d' \
  /etc/hostapd/mikrotik-lab.conf

# 3. Reiniciar
sudo pkill -x hostapd; sleep 1
sudo hostapd -B /etc/hostapd/mikrotik-lab.conf

# 4. Verificar
sudo hostapd_cli -i wlp59s0 get_config | grep -E '^(ssid|wpa)='
nmcli -f SSID,SECURITY device wifi list ifname wlp0s20f0u1 | grep MIKROTIK-LAB
```

---

## 7. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| hostapd no arranca y sale `Invalid WPA passphrase` | Quedó `wpa=2` sin clave válida (8–63 caracteres) | Usa `wpa=0` para red abierta o una clave de 8+ caracteres |
| hostapd no arranca: `wpa_passphrase` vacío | Misma causa | Borra la línea y pon `wpa=0` |
| El móvil no se conecta | Guardó la red con la clave antigua | “Olvidar red” y volver a conectar |
| El móvil conecta pero no sale el portal | Caché de portal o DNS privado | Abrir `http://192.168.77.254/login`; desactivar DNS privado |
| El QR WiFi no conecta | Sigue generándose como `T:WPA` | Aplicar §3.1 y dejar `MIKROTIK_WIFI_PASSWORD=` |
| `get_config` muestra `wpa=2` | No se reinició hostapd | `sudo pkill -x hostapd` y arrancarlo de nuevo |
| El resumen de `arrancar-todo.sh` sigue diciendo `mikrotik123` | Es texto fijo | Editar la línea del resumen o ignorarlo |

---

## 8. Seguridad y alcance

- El **portal del hotspot sigue autenticando**: sin usuario válido no hay
  Internet, aunque la WiFi esté abierta.
- La diferencia es que el tráfico **WiFi** viaja sin cifrar: alguien cerca
  podría capturarlo. Para producción, mantén WPA2/WPA3.
- Si el AP está abierto, cualquiera puede intentar fuerza bruta contra el
  portal. Usa usuarios con claves fuertes y revisa `/ip hotspot active`
  periódicamente.
- En RouterOS puedes añadir además `ip-binding` o límites por usuario para
  reducir el riesgo.
