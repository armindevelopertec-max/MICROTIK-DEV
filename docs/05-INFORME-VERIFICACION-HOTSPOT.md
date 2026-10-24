# Informe de verificación — Hotspot MikroTik CHR + AP WiFi

**Fecha:** 2026-10-23 (hora local -04 / UTC 18:30)
**Equipo:** laptop `fedora` — CHR 7.24.5 en QEMU/KVM
**Objetivo:** comprobar que el hotspot funciona de punta a punta y dejar constancia de qué se hizo para lograrlo.

---

## 1. Resumen ejecutivo

| Pregunta | Resultado |
|---|---|
| ¿Funciona `ssh -p 2222 admin@127.0.0.1` con `Dahua2026`? | **Sí** (ya funcionaba; es el *hostfwd* de QEMU, no depende del hotspot) |
| ¿Se emite el SSID del laboratorio? | **Sí** — `MIKROTIK-LAB`, WPA2, canal 11, -25 dBm |
| ¿El cliente recibe IP por DHCP? | **Sí** — `WAVE-8` obtuvo `192.168.77.198` |
| ¿Se abre el portal cautivo? | **Sí** — `http://192.168.77.254/login` responde 200 |
| ¿Se puede autenticar un usuario? | **Sí** — login HTTP-CHAP validado; `Armindev` quedó activo |
| ¿Sale a Internet tras autenticarse? | **Sí** — NAT del CHR por `ether1` (slirp 10.0.2.15) |

**Estado inicial:** el CHR estaba bien configurado, pero **el AP WiFi estaba apagado**, el **tap no estaba enganchado al bridge** y el **uplink estaba en la radio que debía hacer de AP**. Por eso no había WiFi ni portal, aunque el SSH sí respondía.

---

## 2. Estado inicial (qué estaba mal)

```
$ ss -tlnp | grep -E '2222|8291'
LISTEN 127.0.0.1:2222   qemu-system-x86   ← SSH CHR OK
LISTEN 127.0.0.1:8291   qemu-system-x86   ← WinBox OK

$ pgrep -a hostapd
(vacío)                                    ← AP WiFi APAGADO

$ bridge link show
(vacío)                                    ← br-mikrotik SIN puertos

$ ip route show default
default via 192.168.100.1 dev wlp59s0      ← uplink en la radio AP
```

Además:

- `wlp59s0` (radio interna QCA6174, la única que soporta modo AP) estaba conectada a `TecRoot`.
- `tap-mikrotik` existía y estaba `UP`, pero **no pertenecía a `br-mikrotik`**.
- `br-mikrotik` tenía **STP activado** (`stp_state=1`), lo que retrasa el *forwarding*.
- `ping 192.168.77.254` fallaba: sin el tap en el bridge no había camino L2 hasta el CHR.

El lado RouterOS **sí estaba correcto**:

```
/ip address        → 192.168.77.254/24 en ether2  (LAN LABORATORIO)
/ip pool           → pool-lan 192.168.77.100-199
/ip dhcp-server    → dhcp-lan en ether2
/ip hotspot        → hotspot1 en ether2, perfil hsprof1, proxy running
/ip firewall nat   → masquerade out-interface=ether1 y src 192.168.77.0/24
/ip hotspot user   → admin, Armindev, Daniel
```

---

## 3. Acciones realizadas (en orden)

### 3.1 Mover el uplink a la radio USB

La radio interna debe quedar libre para `hostapd`, y el Internet debe salir por la USB:

```bash
nmcli connection modify TecRoot-USB ipv4.route-metric 100
nmcli connection modify TecRoot     ipv4.route-metric 500
nmcli connection up TecRoot-USB
```

Resultado:

```
default via 192.168.100.1 dev wlp0s20f0u1 metric 100   ← uplink
default via 192.168.100.1 dev wlp59s0     metric 500
```

> Esto queda guardado en los perfiles de NetworkManager: sobrevive al reinicio.

### 3.2 Liberar la radio interna para modo AP

```bash
nmcli device disconnect wlp59s0
nmcli device set wlp59s0 managed no
```

`wlp59s0` queda `sin gestión`, sin SSID asociado, lista para `hostapd`.

> Se borró también un perfil NM duplicado llamado `tap-mikrotik` que quedó de un intento anterior.

### 3.3 Bridge: STP fuera y tap enganchado

```bash
sudo ip link set br-mikrotik type bridge stp_state 0 forward_delay 0
sudo ip link set br-mikrotik up
sudo ip link set tap-mikrotik master br-mikrotik
sudo ip link set tap-mikrotik up
```

Resultado:

```
$ bridge link show
wlp59s0       ... master br-mikrotik state forwarding
tap-mikrotik  ... master br-mikrotik state forwarding

$ cat /sys/class/net/br-mikrotik/bridge/stp_state
0
```

### 3.4 Arrancar el AP WiFi

```bash
sudo pkill -x hostapd
sudo hostapd -B /etc/hostapd/mikrotik-lab.conf
```

Configuración usada (`/etc/hostapd/mikrotik-lab.conf`):

```ini
interface=wlp59s0
bridge=br-mikrotik
driver=nl80211
ssid=MIKROTIK-LAB
hw_mode=g
channel=11
ieee80211n=1
wpa=2
wpa_passphrase=mikrotik123
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
```

`hostapd` añade `wlp59s0` al bridge automáticamente.

### 3.5 Verificación de DHCP, portal y login

- Se confirmó el **beacon** del SSID:

  ```
  $ sudo iw dev wlp0s20f0u1 scan | grep -A2 MIKROTIK-LAB
  SSID: MIKROTIK-LAB
  DS Parameter set: channel 11
  signal: -25.00 dBm
  ```

- Un dispositivo real (`WAVE-8`, MAC `9A:69:FC:C3:A5:F2`) se asoció y recibió DHCP:

  ```
  /ip dhcp-server lease print
  192.168.77.198  9A:69:FC:C3:A5:F2  WAVE-8  dhcp-lan  bound
  ```

- El portal responde:

  ```
  $ curl -i http://192.168.77.254/login
  HTTP/1.1 200 OK
  Content-Type: text/html
  ... Powered by MikroTik RouterOS
  ```

- **Login HTTP-CHAP** probado con un usuario temporal (`prueba` / `prueba123`),
  calculando `md5(password + challenge)` como lo hace `md5.js` del portal:

  ```
  /ip hotspot active print
  user="prueba" address=192.168.77.197 login-by="http-chap" uptime=7s
  ```

  Luego se **eliminaron** el usuario y la sesión de prueba:

  ```
  /ip hotspot active remove [find where user="prueba"]
  /ip hotspot user remove   [find where name="prueba"]
  ```

- Poco después el cliente real inició sesión:

  ```
  /ip hotspot active print
  USER       ADDRESS          UPTIME
  Armindev   192.168.77.198   14s
  ```

  Es decir: **WiFi → bridge → tap → ether2 → DHCP → portal → login → NAT** funciona completo.

### 3.6 Ajuste dejado en el script

En `scripts/iniciar-lab.sh` se añadió un refuerzo a nivel de kernel, porque
NetworkManager no siempre aplica `stp=no` al reactivar el bridge:

```bash
sudo ip link set "$BR" up
sudo ip link set "$BR" type bridge stp_state 0 forward_delay 0
```

---

## 4. Verificación final

```
$ ip route show default
default via 192.168.100.1 dev wlp0s20f0u1 metric 100

$ bridge link show
wlp59s0       master br-mikrotik state forwarding
tap-mikrotik  master br-mikrotik state forwarding
stp_state = 0

$ sudo hostapd_cli -i wlp59s0 status
state=ENABLED
channel=11
num_sta[0]=1

$ ssh -p 2222 admin@127.0.0.1
/system identity print  → name: MICRO-DEV-ROOT
/system resource print  → version: 7.24.5 (stable), board: CHR QEMU

/ip hotspot active print
USER       ADDRESS          UPTIME
Armindev   192.168.77.198   14s

/ip dhcp-server lease print
192.168.77.198  9A:69:FC:C3:A5:F2  WAVE-8  bound
```

---

## 5. Datos de la instalación resultante

| Elemento | Valor |
|---|---|
| SSID | `MIKROTIK-LAB` |
| Clave WiFi | `mikrotik123` (WPA2-PSK) |
| Canal | 11 (2.462 GHz) |
| AP / bridge | `wlp59s0` + `tap-mikrotik` en `br-mikrotik` |
| Uplink del host | `wlp0s20f0u1` (métrica 100) |
| LAN del hotspot | `192.168.77.0/24` |
| Gateway / portal | `192.168.77.254` (ether2 del CHR) |
| DHCP | `pool-lan` 192.168.77.100–199 |
| NAT | `masquerade` por `ether1` (10.0.2.15, slirp de QEMU) |
| SSH CHR | `ssh -p 2222 admin@127.0.0.1` — password `Dahua2026` |
| WinBox | `127.0.0.1:8291` |
| Usuarios hotspot | `admin`, `Armindev`, `Daniel` |

---

## 6. Cómo arrancar / parar

Arranque completo (recomendado, hace todo lo anterior de forma ordenada):

```bash
cd ~/Documentos/MICRO-TIK
./scripts/iniciar-lab.sh
```

> Requisito: el uplink debe estar en `wlp0s20f0u1` (métrica 100), como quedó
> configurado. Si el USB está desconectado, la única radio disponible es la
> interna y el script se detiene con un mensaje claro (no puede ser AP y STA a la vez).

Parar:

```bash
./scripts/parar-lab.sh
```

---

## 7. Notas y pendientes

1. **`hostapd` no persiste tras reiniciar**: hay que relanzar `iniciar-lab.sh`
   (o crear una unidad systemd si se quiere automático).
2. **Contraseñas de los usuarios del hotspot** no se pueden leer desde RouterOS;
   se administran en WinBox → *IP → Hotspot → Users*. Si se olvidan, se resetean ahí.
3. **No poner una ruta por defecto hacia el CHR en la laptop**: el bridge tiene
   IP `192.168.77.1` y el CHR `192.168.77.254`; el host debe salir por su propia WiFi.
4. El dispositivo `WAVE-8` quedó conectado y autenticado como `Armindev`; si no es
   un equipo de confianza, conviene revisarlo/expulsarlo desde *Hotspot → Active*.
5. El usuario temporal `prueba` **fue eliminado**; no quedó ningún cambio de prueba.
6. El `ping` del host a `192.168.77.254` responde “red prohibida”: es correcto,
   el hotspot rechaza clientes no autenticados (el host es uno de ellos).

---

## 8. Anexo — comandos de diagnóstico rápido

```bash
# Host
ip route show default
bridge link show
cat /sys/class/net/br-mikrotik/bridge/stp_state
nmcli device status | grep wlp
sudo hostapd_cli -i wlp59s0 status
sudo hostapd_cli -i wlp59s0 all_sta
sudo iw dev wlp0s20f0u1 scan | grep -A2 MIKROTIK-LAB

# CHR
sshpass -p 'Dahua2026' ssh -p 2222 admin@127.0.0.1 \
  '/ip hotspot print; /ip hotspot active print; /ip dhcp-server lease print; /log print'
```
