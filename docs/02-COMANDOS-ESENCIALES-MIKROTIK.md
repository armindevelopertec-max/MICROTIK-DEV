# Comandos Esenciales MikroTik — el kit de supervivencia

> **Este es el tercer documento.** El mínimo imprescindible de RouterOS: los comandos que
> **necesitas saber** para no perderte, los que te pueden dejar sin acceso y cómo verificar
> que todo está bien.
> El catálogo completo por menú está en → [`01-COMANDOS-MIKROTIK.md`](./01-COMANDOS-MIKROTIK.md)

**Versión de referencia:** RouterOS 7.24.5 (CHR, x86_64)
**Sintaxis verificada contra:** MikroTik CLI Reference oficial, rama `7.24`

---

## Índice

1. [Para quién es este documento](#1-para-quién-es-este-documento)
2. [Las 12 reglas de oro de la sintaxis RouterOS](#2-las-12-reglas-de-oro-de-la-sintaxis-routeros)
3. [Los 8 comandos que usas el 90% del tiempo](#3-los-8-comandos-que-usas-el-90-del-tiempo)
4. [Bloques de comandos imprescindibles](#4-bloques-de-comandos-imprescindibles)
5. [Safe mode: cómo no dejarte fuera](#5-safe-mode-cómo-no-dejarte-fuera)
6. [Los comandos que nunca debes ejecutar a ciegas](#6-los-comandos-que-nunca-debes-ejecutar-a-ciegas)
7. [Los 12 `print` que te salvan](#7-los-12-print-que-te-salvan)
8. [Backup, export y restore: el ciclo correcto](#8-backup-export-y-restore-el-ciclo-correcto)
9. [Atajos y tips de trabajo](#9-atajos-y-tips-de-trabajo)
10. [Errores frecuentes](#10-errores-frecuentes)
11. [Cheat sheet de una página](#11-cheat-sheet-de-una-página)

---

## 1. Para quién es este documento

Este documento es el **"manual de conducción"** del MikroTik: el conjunto de comandos que debes
memorizar para trabajar con soltura. Está pensado para:

- Quien acaba de abrir un router MikroTik y se siente perdido.
- Quien viene de la línea de comandos de Unix y no entiende la lógica de RouterOS.
- Quien administers el CHR del laboratorio y quiere un resumen a mano.

**No es** un sustituto del [doc 01](./01-COMANDOS-MIKROTIK.md): aquí está el *qué*Commands
esenciales, allá el detalle de cada parámetro.

| Si tu problema es... | Ve a... |
|---|---|
| "No entiendo la sintaxis" | [§2 Reglas de oro](#2-las-12-reglas-de-oro-de-la-sintaxis-routeros) |
| "Me equivoqué y el router no responde" | [§5 Safe mode](#5-safe-mode-cómo-no-dejarte-fuera) |
| "Quiero ver si X está bien" | [§7 Verificación](#7-los-12-print-que-te-salvan) |
| "Quiero guardar el estado" | [§8 Backup/export](#8-backup-export-y-restore-el-ciclo-correcto) |
| "El cliente no navega, ¿qué reviso?" | [§10 Errores frecuentes](#10-errores-frecuentes) + [doc 01 §16](./01-COMANDOS-MIKROTIK.md#16-diagnóstico-y-monitoreo) |

---

## 2. Las 12 reglas de oro de la sintaxis RouterOS

RouterOS **no** es Unix, no es Cisco. Su lógica es otra. Estas 12 reglas explican el 95% de
los errores de un principiante.

### Regla 1 — Todo es una ruta jerárquica

```routeros
/ip/firewall/nat
/ip hotspot/user/profile
```

La barra es un separador de niveles, **no** un divisor de comandos. Puedes escribir la ruta
completa en una sola línea o navegar paso a paso.

### Regla 2 — `print` es el verbo universal de lectura

```routeros
/ip/hotspot/print          # qué hay y cómo está
/ip/hotspot/print detail   # con TODOS los campos, incluso los vacíos
```

`print detail` es tu mejor amigo: muestra los campos que `print` esconde porque están en
valor por defecto. Úsalo siempre que dudes de algo.

### Regla 3 — `add` crea, `set` modifica, `remove` borra, `enable`/`disable` apaga/enciende

```routeros
/ip/hotspot/user/add name=cliente password=123 profile=perfil-gratis
/ip/hotspot/user/set [find name=cliente] profile=perfil-premium
/ip/hotspot/user/disable [find name=cliente]
/ip/hotspot/user/remove [find name=cliente]
```

> `disable` es **reversible**; `remove` **no lo es**. Ante la duda, `disable`.

### Regla 4 — `find` devuelve un *set*, no un objeto

```routeros
/ip/hotspot/user/print where name=cliente
```

`where` filtra. `find` **selecciona**. Y la diferencia es crítica:

```routeros
/ip/hotspot/user/set [find name=cliente] profile=premium
```

- `find` → devuelve el **índice interno** (`.id`) de todo lo que coincide.
- `set` / `disable` / `remove` / `print` lo aceptan entre corchetes `[ ]`.
- `where` → devuelve un **filtro booleano** que se usa dentro de `print`.

> ⚠️ Si `find` devuelve **más de un** elemento, el comando actúa sobre **todos**. Por eso
> `remove [find ...]` sin filtro preciso es letal. Comprueba siempre antes:
> `/ip/hotspot/user/print [find name=cliente]`

### Regla 5 — Las comillas solo cuando hay espacios o caracteres especiales

```routeros
/ip hotspot user add name=cliente1 password=abc123        # sin comillas, OK
/ip hotspot user add name="Cliente Uno" password="a b c"   # con comillas, obligatorio
```

Y **siempre** entre comillas en un `where` o `find` si el valor tiene espacios:

```routeros
/ip hotspot user print where name~"Cliente"
```

### Regla 6 — Un valor = una propiedad. No hay `=` dentro del valor

```routeros
/ip address add address=192.168.77.254/24 interface=ether2    # correcto
/ip address add address=192.168.77.254/24 interface=ether2 name="LAN"  # correcto
```

Si necesitas un valor con `=`, envuélvelo en comillas.

### Regla 7 — Las comillas dobles undergo expansión de variables; las simples no

```routeros
:local miVar "ether2"
/interface print where name=$miVar        # doble: expande $miVar -> ether2
/interface print where name='$miVar'      # simple: busca literalmente $miVar
```

En scripts, esta diferencia es la causa más común de "no funciona y no sé por qué".

### Regla 8 — Los valores booleanos son `yes`/`no`

```routeros
/ip hotspot set [find name=hotspot1] disabled=no
/interface bridge port set [find interface=ether2] hw=yes
```

`true`/`false`, `1`/`0` no se aceptan en la mayoría de propiedades.

### Regla 9 — El tiempo se escribe `1h`, `30m`, `10s`, `1d`, `5m30s`

```routeros
/ip hotspot set idle-timeout=5m
/ip hotspot user profile set session-timeout=1h
```

Formato: `<n><unidad>`. Las unidades válidas: `s` (segundos), `m` (minutos), `h` (horas),
`d` (días), `w` (semanas). Puedes combinar: `1h30m`.

### Regla 10 — El rango de IPs también tiene su formato

```routeros
/ip pool add name=pool ranges=192.168.77.100-192.168.77.199
```

Y un prefijo de red se escribe con `/`:

```routeros
/ip address add address=192.168.77.254/24 interface=ether2
```

### Regla 11 — `print` acepta `proplist` para ver solo algunos campos

```routeros
/ip hotspot/print proplist=name,idle-timeout
/ip address/print proplist=address,interface
```

Ideal para tablas largas con muchos elementos.

### Regla 12 — Cada comando de escritura se puede deshacer con `undo` (a veces)

```routeros
/undo
```

RouterOS guarda un historial corto de los cambios. Funciona sobre todo para `add`/`set`.
**No** es un sustituto de un backup, pero te salva de un `remove` accidental.

---

## 3. Los 8 comandos que usas el 90% del tiempo

Si solo memorizas ocho cosas, que sean estas.

```routeros
print                  # ver el contenido del menú actual
print detail          # ver TODO, incluidos los valores por defecto
find                  # seleccionar elementos (siempre entre [])
add / set / remove    # crear / modificar / borrar
where                 # filtrar dentro de print
undo                  # deshacer el último cambio
export                # volcar la configuración a texto
```

Y el comando de supervivencia, que es un atajo, no un verbo:

```routeros
[admin@MICRO-DEV-ROOT] > /ip/hotspot/user/print where name=cliente
```

---

## 4. Bloques de comandos imprescindibles

Cada bloque es autocontenido. Cópialo, pégalo y adapta los valores.

### 4.1 Ver el estado general del router

```routeros
/system resource print          # CPU, RAM, disco, uptime, versión
/system identity print           # nombre del router
/system license print            # nivel de licencia (CHR)
/interface print                 # interfaces y su estado
/ip address print                # IPs asignadas
/ip route print                  # tabla de rutas
/log print where topics~"error"  # últimos errores
```

### 4.2 Usuarios del router (no del hotspot)

Estos son los que te permiten entrar al equipo. **Cámbialos el primer día.**

```routeros
/user print                                   # ver los usuarios
/user set admin password="UnaClaveLarga123"   # cambiar la clave de admin

# Crear un usuario de solo lectura para monitorizar
/user add name=monitor password="OtraClave456" group=read

# Desactivar el admin por defecto (solo tras crear el tuyo)
/user disable admin
```

> ⚠️ **La clave de `admin` es la puerta al router.** Si la pierdes, la única salida es
> reiniciar el equipo (y en un CHR, ripear el disco). Haz un backup después de cambiarla.

### 4.3 Identidad, hora y NTP

La hora mal puesta rompe los logs, los certificados y las cookies del hotspot.

```routeros
/system identity set name=MICRO-DEV-ROOT
/system clock set time-of-day=12:00:00

# NTP (el CHR debe tener salida a Internet para sincronizar)
/system ntp client set enabled=yes
/system ntp client servers add address=pool.ntp.org
/system ntp client set primary-ntp=pool.ntp.org
```

### 4.4 Interfaces y direcciones IP

```routeros
/interface print                          # ver interfaces
/interface ethernet print detail          # ver todo (speed, mtu, mac)
/interface set [find name=ether2] disabled=no

# Asignar una IP
/ip address add address=192.168.77.254/24 interface=ether2 comment="LAN HOTSPOT"

/ip address print
/ip address remove [find address=192.168.77.254/24]
```

### 4.5 DHCP — servidor

MikroTik trae un **asistente** que hace el 90% del trabajo. Úsalo primero:

```routeros
/ip dhcp-server setup
```

El asistente pregunta, en este orden:

1. Interfaz del servidor DHCP → `ether2`
2. Red → `192.168.77.0/24`
3. Gateway → `192.168.77.254`
4. Rango a entregar → `192.168.77.100-192.168.77.199`
5. Servidores DNS → `192.168.77.254` o `1.1.1.1`
6. Tiempo de concesión → `1h`

Ocho de cada diez problemas de "el cliente no coge IP" son un DNS o un gateway mal puesta.

Equivalente manual, para entenderlo o automatizarlo:

```routeros
/ip pool add name=pool-lan ranges=192.168.77.100-192.168.77.199

/ip dhcp-server network add \
  address=192.168.77.0/24 \
  gateway=192.168.77.254 \
  dns-server=192.168.77.254

/ip dhcp-server add \
  name=dhcp-lan \
  interface=ether2 \
  address-pool=pool-lan \
  lease-time=1h \
  disabled=no

# Ver quién está conectado
/ip dhcp-server lease print
```

### 4.6 DNS

```routeros
/ip dns print
/ip dns set servers=1.1.1.1,8.8.8.8 allow-remote-requests=yes

# Entrada estática (útil para el nombre del portal)
/ip dns static add name=wifi.dev address=192.168.77.254 ttl=1d

# Cache
/ip dns cache print
```

### 4.7 NAT y firewall

En MikroTik, **NAT y firewall son dos menús distintos**:

- `/ip firewall nat` → **traduce direcciones** (quién sale a Internet con qué IP).
- `/ip firewall filter` → **decide** qué paquetes se permiten o se bloquean.

```routeros
# NAT de salida
/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade comment="NAT salida"

/ip firewall nat add chain=srcnat src-address=192.168.77.0/24 action=masquerade comment="NAT hotspot"

# Regla de input: permitir todo desde la LAN
/ip firewall filter add chain=input in-interface=ether2 action=accept comment="Acepta LAN"

/ip firewall nat print
/ip firewall filter print
```

> 💡 En una config nueva de MikroTik **no hay reglas de firewall por defecto** (salvo en
> algunos modelos). Sin una regla `accept` en `chain=input`, te quedas sin acceso al router
> aunque la IP esté bien. Es el error nº 1.

### 4.8 Bridge (agrupar puertos)

Necesario en hardware real para poner varios puertos LAN en el mismo segmento.

```routeros
/interface bridge add name=bridge1
/interface bridge port add bridge=bridge1 interface=ether2
/interface bridge port add bridge=bridge1 interface=ether3
/ip address add address=192.168.77.254/24 interface=bridge1
```

En hardware con switch, añade `hw=yes` para que el tráfico no salga a la CPU:

```routeros
/interface bridge port set [find interface=ether3] hw=yes
```

### 4.9 Hotspot — versión mínima funcional

```routeros
# 1. Perfil del servidor
/ip hotspot profile add \
  name=hsprof1 \
  hotspot-address=192.168.77.254 \
  dns-name="" \
  html-directory=hotspot

# 2. Servidor hotspot
/ip hotspot add \
  name=hotspot1 \
  interface=ether2 \
  address-pool=pool-lan \
  profile=hsprof1 \
  idle-timeout=5m \
  login-timeout=2m \
  keepalive-timeout=30s \
  disabled=no

# 3. Perfil de usuario
/ip hotspot user profile add \
  name=perfil-gratis \
  shared-users=1 \
  session-timeout=1h \
  idle-timeout=10m \
  keepalive-timeout=30s \
  mac-cookie-timeout=1d \
  rate-limit=512k/2M

# 4. Usuario
/ip hotspot user add \
  name=cliente \
  password=cliente123 \
  profile=perfil-gratis

# 5. Verificar
/ip hotspot print
/ip hotspot user print
/ip hotspot active print
```

> 💡 **`hotspot-address` debe ser exactamente la IP que tiene la interfaz del hotspot.**
> Si no coincide, el portal no carga y el error típico es "no se puede encontrar wifi.dev".

### 4.10 Colas de ancho de banda

```routeros
# Lo más simple: límite en el perfil del hotspot
/ip hotspot user profile set [find name=perfil-gratis] rate-limit=512k/2M

# Lo flexible: simple queue por IP
/queue simple add name=q-cliente target=192.168.77.100 max-limit=2M/8M

/queue simple print
/queue simple print detail
```

> ⚠️ **El orden rx/tx se invierte entre menús.** En `rate-limit` (hotspot) es
> rx/tx **desde la vista del router** = subida/bajada del cliente.
> En `/queue simple`, `max-limit` es **upload/download** del cliente.
> Detalle completo en [doc 01 §10](./01-COMANDOS-MIKROTIK.md#10-límites-de-ancho-de-banda).

### 4.11 Registro y logs

```routeros
/log print                       # todo
/log print where topics~"hotspot"
/log print where message~"error"

/system logging action set [find name=memory] memory-lines=1000
```

---

## 5. Safe mode: cómo no dejarte fuera

Es la red de seguridad de RouterOS. **Actívalo SIEMPRE antes de tocar la red.**

### Qué hace

Al entrar en safe mode, RouterOS aplica automáticamente una reversión de todos los cambios
de configuración made en los 4 minutos anteriores si pierdes la conexión.

### Cómo se activa

```routeros
[admin@MICRO-DEV-ROOT] > <CTRL+X>
```

Aparecerá:

```
[Safe Mode taken]
[admin@MICRO-DEV-ROOT] <CTRL+X>
```

### Cómo se sale

```routeros
[admin@MICRO-DEV-ROOT] <CTRL+X>
```

Sale del safe mode **sin** revertir nada.

### Cuándo usarlo

| Situación | ¿Safe mode? |
|---|---|
| Cambias la IP del router | ✅ Sí |
| Añades reglas de firewall | ✅ Sí |
| Tocas el bridge o las interfaces | ✅ Sí |
| Mueves la red del hotspot | ✅ Sí |
| Creas usuarios del hotspot | ❌ No hace falta |
| Copias y pegas configuración | ❌ No hace falta |

> 💡 En SSH, `Ctrl+X` puede ser interpretado por el terminal. Si no funciona, envíalo como
> `Ctrl+Shift+X` o activa safe mode desde el propio router:
> `/system/safe-mode` no existe como menú; la vía alternativa es
> **WinBox** (el botón de la barra superior) o **WebFig**.

> ⚠️ Safe mode **no** protege contra un `remove` accidental de un usuario o de un perfil de
> hotspot: eso no rompe la conectividad y por tanto no se revierte.

---

## 6. Los comandos que nunca debes ejecutar a ciegas

| Comando | Por qué es peligroso | Cómo hacerlo bien |
|---|---|---|
| `/system reset-configuration` | Borra **todo**. En un CHR te deja en el prompt de instalación. | Solo con un backup verificado. |
| `/user remove admin` | Te quedas sin acceso. | Crea otro usuario `group=full` y **prueba a entrar** con él antes. |
| `/ip firewall filter remove [find]` sin filtro | Borra reglas de golpe. | `print` primero, `disable` en vez de `remove`. |
| `/ip hotspot user remove [find name~""]` | Borra todos los usuarios. | Filtra siempre por un valor concreto. |
| `/interface bridge remove [find]` | Rompe la red y el hotspot. | `disable` primero, comprueba, y luego borra. |
| `/file remove [find]` | Borra el backup que creaste. | Lista los archivos antes. |
| `/system reboot` | Corta la sesión. | Útil, pero no lo hagas dentro de un script que estés probando. |

**Regla general:** ante la duda, `disable` en lugar de `remove`. Todo se puede volver a
habilitar; nada se puede recuperar de un `remove`.

---

## 7. Los 12 `print` que te salvan

Este es tu kit de diagnóstico. Con estos doce comandos sabes casi todo del estado del router.

```routeros
# 1. Recursos: CPU, RAM, disco, versión, uptime
/system resource print

# 2. Interfaces: cuáles existen y cuáles están vivas
/interface print

# 3. Direcciones IP asignadas
/ip address print

# 4. Rutas: por dónde sale el tráfico
/ip route print

# 5. Vecinos ARP: quién está en la red local
/ip arp print

# 6. Servidor DHCP y sus arrendamientos
/ip dhcp-server lease print

# 7. DNS: qué resuelve y qué está cacheado
/ip dns cache print

# 8. Reglas de NAT activas
/ip firewall nat print

# 9. Reglas de firewall (input, forward)
/ip firewall filter print

# 10. El hotspot: servidores, usuarios, sesiones
/ip hotspot print
/ip hotspot user print
/ip hotspot active print

# 11. Colas y ancho de banda en uso
/queue simple print detail

# 12. Logs y errores recientes
/log print where topics~"error"
```

###pings de verificación rápida

```routeros
/ping 1.1.1.1 count=4              # ¿salgo a Internet?
/ping 192.168.77.254 count=4        # ¿respondo yo mismo?
/tool traceroute 1.1.1.1            # ¿por dónde sale?
/ip firewall connection print       # ¿qué conexiones hay abiertas?
/interface monitor-traffic ether2  # ¿pasa tráfico por aquí?
```

---

## 8. Backup, export y restore: el ciclo correcto

### El flujo correcto de trabajo

```
   CONFIGURAR  ──▶  EXPORT (texto, para guardar y comparar)
        │                    │
        │                    ▼
        │              BACKUP .backup (binario, con contraseñas)
        │                    │
        ▼                    ▼
   VERIFICAR   ◀────  GUARDAR COPIA FUERA DEL ROUTER
```

### Export (texto legible, sin contraseñas)

```routeros
/system export file=backup-lab
/file print where name="backup-lab.rsc"
```

### Backup binario (incluye contraseñas — trátalo como un secreto)

```routeros
/system backup save name=backup-lab
/file print where name="backup-lab.backup"
```

### Restaurar

```routeros
# Texto (puede pedir confirmación de cada línea)
/import file-name=backup-lab.rsc

# Ensayo sin aplicar nada
/import file-name=backup-lab.rsc dry-run=yes

# Binario: reinicia el router
/system backup load name=backup-lab
/system reboot
```

### Bajar las copias al host

```bash
scp -P 2222 admin@127.0.0.1:/backup-lab.backup ./
scp -P 2222 admin@127.0.0.1:/backup-lab.rsc ./
```

> ⚠️ El `.backup` **contiene las contraseñas en claro**. No lo subas a un repositorio
> público ni lo mandes por correo sin cifrar.

---

## 9. Atajos y tips de trabajo

### En la terminal

| Atajo | Qué hace |
|---|---|
| `Ctrl+X` | Entrar/salir de safe mode |
| `Ctrl+C` | Interrumpir el comando actual |
| `Ctrl+D` | Terminar la sesión (o `quit`) |
| `Tab` | Autocompletar |
| `Ctrl+R` | Historial de comandos (en SSH, `↑` también) |
| `Ctrl+Q` | Cancelar la línea actual |

### En la línea de comandos

| Tip | Ejemplo |
|---|---|
| Encadenar rutas | `/ip/firewall/nat/print` |
| Filtrar por texto | `print where name~"cli"` (`~` = contiene) |
| Filtrar por número | `print where name~"^cl"` (`^` = empieza por) |
| Contar | `print count-only` |
| Ver solo un campo | `print proplist=name,disabled` |
| Describir un comando | `add ?` (muestra todas las propiedades) |

### Comprobaciones cruzadas que evitan el 80% de los errores

```routeros
# ¿Existe ya un objeto con ese nombre?
/ip hotspot user print where name=cliente

# ¿Qué IP tiene realmente la interfaz del hotspot?
/ip address print where interface=ether2

# ¿El pool coincide con la subred del DHCP?
/ip pool print
/ip dhcp-server network print

# ¿Hay conflictos de IP en la LAN?
/ip arp print where address=192.168.77.254
```

---

## 10. Errores frecuentes

| Error / síntoma | Causa real | Solución |
|---|---|---|
| `no such command` | Ruta mal escrita o el menú no existe | `print` en el nivel anterior; revisa `/` (raíz) |
| `not enough parameters` | Falta una propiedad obligatoria | `add ?` para ver qué pide |
| `invalid value for argument address` | IP sin prefijo o con prefijo inválido | `192.168.77.254/24` |
| `already have such entry` | El objeto existe | `print where name=...` y `set` en vez de `add` |
| `cannot set ... , no such item` | El `find` no devolvió nada | Revisa el nombre; `print` antes de `set` |
| WinBox no conecta | Interfaz de gestión equivocada o firewall | `print where interface=ether2`; regla `accept` en `chain=input` |
| SSH no conecta | Servicio SSH deshabilitado | `/ip service print` → `set [find port=22] disabled=no` |
| El portal no carga | `hotspot-address` ≠ IP real de la interfaz | Compara con `/ip address print` |
| El portal no carga en Android | DNS privado / DoT del móvil | `dns-name=""` en el perfil del hotspot |
| El cliente no coge IP | DNS o gateway mal en `dhcp-server network` | `/ip dhcp-server network print` |
| El cliente coge IP pero no navega | Falta NAT en `chain=srcnat` | `/ip firewall nat print` |
| `rate-limit` invertido | Confundiste rx/tx con upload/download | Ver [doc 01 §10](./01-COMANDOS-MIKROTIK.md#10-límites-de-ancho-de-banda) |
| Sesión cae a los 2 minutos | `idle-timeout` corto o `keepalive-timeout` mal | Ver la tabla maestra en [doc 01 §9](./01-COMANDOS-MIKROTIK.md#9-tiempos-timeouts) |
| SSH se corta al cambiar la IP | Cambiaste la gestión por la interfaz equivocada | Safe mode (`Ctrl+X`) antes de tocar la IP |

---

## 11. Cheat sheet de una página

```routeros
# ═══ NAVEGAR ═══
/ip/hotspot/user              # ir a una ruta
/                             # ir a la raíz
..                            # subir un nivel
print                         # listar
print detail                  # listar todo
print count-only              # contar
print where name~"cli"        # filtrar (contiene)
print where name~"^cli"       # filtrar (empieza por)
print proplist=name,disabled  # solo algunos campos

# ═══ SELECCIONAR ═══
[find name=cliente]           # por atributo
[find where name~"cli"]       # por filtro
[0]                           # el primero
[$id]                         # por id
0                            # el primero (índice)

# ═══ ESCRIBIR ═══
add name=x value=y
set [find name=x] value=y
remove [find name=x]
enable [find name=x]
disable [find name=x]
undo                          # deshacer

# ═══ TIEMPOS ═══
30s   5m   1h   1d   1w   1h30m

# ═══ VERIFICAR ═══
/system resource print
/interface print
/ip address print
/ip route print
/ip arp print
/ip dhcp-server lease print
/ip dns cache print
/ip firewall nat print
/ip firewall filter print
/ip hotspot active print
/queue simple print detail
/log print where topics~"error"

/ping 1.1.1.1 count=4
/tool traceroute 1.1.1.1

# ═══ SEGURIDAD ═══
<CTRL+X>                      # safe mode
<CTRL+X>                      # salir de safe mode
/user set admin password="ClaveFuerte"
/ip service print              # SSH, WinBox, API

# ═══ RESPALDO ═══
/system export file=cfg
/system backup save name=cfg
/file print
/import file-name=cfg.rsc
```

---

## Documentos relacionados

| Documento | Cuándo leerlo |
|---|---|
| [`00-ENTORNO-Y-PREPARACION.md`](./00-ENTORNO-Y-PREPARACION.md) | Antes de todo: preparar el laboratorio. |
| [`01-COMANDOS-MIKROTIK.md`](./01-COMANDOS-MIKROTIK.md) | Catálogo completo por menú. |
| **Este** | Cuando necesitas el mínimo imprescindible a mano. |
| [`03-EQUIVALENTES-VMWARE-VIRTUALBOX.md`](./03-EQUIVALENTES-VMWARE-VIRTUALBOX.md) | Si quieres el CHR en VMware o VirtualBox. |
| [`04-MIKROTIK-FISICO.md`](./04-MIKROTIK-FISICO.md) | Si vas a montar esto en un router real. |
