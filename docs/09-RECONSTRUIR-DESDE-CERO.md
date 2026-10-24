# 09 — Reconstruir el CHR desde cero tras un reset

> Después de `/system reset-configuration` el CHR se queda **sin configuración y sin IP**.
> Esta guía lo devuelve a un estado funcional (WAN + LAN + DHCP + hotspot + API para los
> tickets QR) usando un único script:
> [`../mikrotik-lab-desde-cero.rsc`](../mikrotik-lab-desde-cero.rsc).

---

## Qué se pierde y qué se conserva con el reset

| Se pierde | Se conserva |
|---|---|
| Direcciones IP, rutas, DHCP, NAT | Los **archivos** del CHR (`/file print`), incluido `hotspot/login.html` personalizado |
| Hotspot, usuarios, perfiles | La licencia CHR |
| Usuario admin y su contraseña (vuelve a vacía) | Los discos de la VM |
| Servicios y firewall | — |

> `reset-configuration` **no borra archivos**. Si personalizaste el login del hotspot, sigue
> en `/file` dentro de la carpeta `hotspot/`.

---

## Paso 1 — Recuperar el acceso (consola de la VM)

Tras el reset, `ether1` se queda sin IP y el reenvío `127.0.0.1:2222` deja de funcionar.
Entra por la **ventana de la VM** (QEMU GTK, VirtualBox o VMware):

```text
Login: admin
Password: (vacía, solo Enter)
```

Y pega el arranque mínimo para recuperar WAN + gestión:

```routeros
/system identity set name=MICRO-DEV-ROOT
/user set [find name=admin] password="Dahua2026"
/ip dhcp-client add interface=ether1 disabled=no
/ip service enable ssh,winbox,api
```

Comprueba que `ether1` tomó IP:

```routeros
/ip address print
```

Debe aparecer `10.0.2.15/24` (QEMU/VirtualBox) o la IP del NAT de VMware.

---

## Paso 2 — Aplicar el script completo

### Opción A — subirlo e importarlo (recomendada)

Desde el host:

```bash
cd /home/armintec/Documentos/MICRO-TIK
scp -P 2222 mikrotik-lab-desde-cero.rsc admin@127.0.0.1:/
ssh -p 2222 admin@127.0.0.1
```

Dentro del CHR:

```routeros
/import file-name=mikrotik-lab-desde-cero.rsc
```

### Opción B — pegar el contenido

```bash
ssh -p 2222 admin@127.0.0.1
```

Abre `mikrotik-lab-desde-cero.rsc`, copia todo y pégalo en la terminal. Es largo pero
funciona igual.

> ⚠️ Antes de ejecutarlo, revisa la **sección 0** del script: contraseña, zona horaria e IPs.
> La contraseña debe coincidir con `MIKROTIK_PASSWORD` de tu `.env` (por defecto `Dahua2026`).

---

## Paso 3 — Verificar por capas

```routeros
/system identity print
/ip address print
/ip route print
/ip dhcp-server print
/ip hotspot print
/ip hotspot active print
/ip firewall nat print
/ping 1.1.1.1 count=4
```

Resultado esperado:

| Comprobación | Esperado |
|---|---|
| `ether1` | `10.0.2.15/24` (o IP del NAT) |
| `ether2` | `192.168.77.254/24` |
| Ruta por defecto | vía `10.0.2.2` o tu gateway |
| `dhcp-lan` | `disabled=no` |
| `hotspot1` | `disabled=no` |
| `ping 1.1.1.1` | responde |

Desde el host:

```bash
ping -c 3 192.168.77.254
curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://192.168.77.254/login   # HTTP 200
```

Y el portal debe apuntar a la IP, no a `wifi.dev`:

```bash
curl -sS http://192.168.77.254/login | grep -E 'form name="(sendin|login)"'
```

---

## Paso 4 — Reconectar el panel y los tickets QR

El panel usa la **API 8728** con `admin` + `MIKROTIK_PASSWORD`. Si cambiaste la clave en el
script, actualiza `.env`:

```bash
cp -n .env.example .env    # si aún no existe
# edita MIKROTIK_PASSWORD para que coincida
```

Comprueba la API desde el CHR:

```routeros
/ip service print where name=api
/ip firewall filter print
```

Y desde el host, reinicia el panel si estaba corriendo:

```bash
./scripts/parar-lab.sh
./scripts/arrancar-todo.sh
```

Prueba a generar un ticket:

```bash
./scripts/ticket-qr --ayuda
```

---

## Repetir el script (limpieza previa)

El script asume un CHR limpio. Si ya hay configuración parcial y quieres volver a aplicarlo,
borra solo los objetos del laboratorio (**no** toques `ether1` ni el DHCP client de la WAN):

```routeros
/ip hotspot remove [find]
/ip hotspot profile remove [find]
/ip hotspot user profile remove [find]
/ip hotspot walled-garden remove [find]
/ip dhcp-server remove [find]
/ip pool remove [find name="pool-lan"]
/ip address remove [find address="192.168.77.254/24"]
/ip firewall nat remove [find comment~"NAT"]
/ip firewall filter remove [find comment~"Establecidas"]
/ip firewall filter remove [find comment~"Invalidas"]
/ip firewall filter remove [find comment~"ICMP"]
/ip firewall filter remove [find comment~"Desde la LAN"]
/ip firewall filter remove [find comment~"Gestion VM"]
/ip firewall filter remove [find comment~"Drop resto"]
```

> Si `remove [find]` se queja porque hay dependencias, borra primero el hotspot y luego el
> DHCP/pool.

---

## Si usas VirtualBox o VMware en Windows

El script es el mismo; solo cambia la VM:

| | VirtualBox | VMware |
|---|---|---|
| Imagen | CHR **VDI** | CHR **VMDK** u **OVA** |
| Adaptador 1 (WAN) | NAT | NAT |
| Adaptador 2 (LAN) | Red interna / host-only | VMnet host-only / personalizada |
| Gestión | WinBox a la IP de la VM | WinBox a la IP de la VM |

- En VirtualBox el NAT da `10.0.2.15/24`, igual que QEMU: el script funciona tal cual.
- En VMware el NAT suele dar `192.168.x.128/24`: añade esa subred a
  `ssh/winbox/api address=` o conéctate desde la LAN del hotspot.
- Si no tienes reenvío de puertos, entra por **WinBox → Neighbors** usando la MAC.

---

## Problemas rápidos

| Síntoma | Causa | Solución |
|---|---|---|
| No puedo entrar por SSH 2222 tras el reset | `ether1` sin IP | Usa la consola de la VM y el Paso 1 |
| El celular no recibe IP | `ether2` sin IP o DHCP caído | `/ip address print`, `/ip dhcp-server print` |
| El portal no abre | Hotspot caído | `/ip hotspot print` |
| El login "no hace nada" | `dns-name` con nombre | `/ip hotspot profile set hsprof1 dns-name=""` |
| El panel no conecta | API deshabilitada o clave distinta | `/ip service print where name=api` y revisa `.env` |
| Autentica pero no navega | Falta NAT o WAN sin Internet | `/ip firewall nat print`, `/ping 1.1.1.1` |

---

## Siguiente paso

- Configuración del hotspot en detalle → [`01-COMANDOS-MIKROTIK.md`](./01-COMANDOS-MIKROTIK.md)
- Tickets QR y panel → [`06-TICKETS-QR.md`](./06-TICKETS-QR.md) · [`07-ARRANQUE-AUTOMATICO-Y-WEB.md`](./07-ARRANQUE-AUTOMATICO-Y-WEB.md)
