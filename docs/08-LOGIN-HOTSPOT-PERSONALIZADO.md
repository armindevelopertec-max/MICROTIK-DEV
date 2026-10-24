# 08 - Login del Hotspot MikroTik personalizado

Este documento describe las páginas HTML del hotspot MikroTik, la personalización realizada y cómo restaurarlas si fuera necesario.

## 1. ¿Dónde se encuentran?

Los archivos del portal cautivo se encuentran en el router MikroTik en:

```text
/hotspot/
```

Desde el laboratorio con acceso por SSH/API también se pueden descargar con `scp`:

```bash
scp -P 2222 admin@127.0.0.1:/hotspot/login.html ./login.html
scp -P 2222 admin@127.0.0.1:/hotspot/css/style.css ./style.css
```

## 2. Páginas existentes

### Páginas principales (`/hotspot/`)

| Archivo | Cuándo se muestra | Descripción |
|---|---|---|
| `login.html` | Sin autenticar / al acceder al portal | Formulario de login. Aquí se introduce el código del ticket (usuario) y la contraseña. Es el que se ve al escanear el QR de acceso. |
| `alogin.html` | Tras autenticación correcta | Página "autenticado". Normalmente redirige automáticamente a `$(link-redirect)` o a la web original solicitada. |
| `status.html` | Ya autenticado, al abrir `http://<hotspot-address>/` | Estado de sesión: tiempo conectado (`$(uptime)`), tráfico (`$(bytes-in-nice) / $(bytes-out-nice)`), IP/MAC, botón de desconexión (`$(link-logout)`). |
| `logout.html` | Al cerrar sesión | Confirmación tras desconectarse del hotspot. |
| `error.html` | Error de autenticación | Se muestra cuando usuario/contraseña son incorrectos, ticket caducado o límite alcanzado. |
| `redirect.html` | Redirección forzada sin login | Suele redirigir a `login.html` cuando se intenta navegar sin estar autenticado. |
| `rlogin.html` | Redirección intermedia | Transición entre páginas. Raramente visible para el usuario. |
| `radvert.html` | Publicidad (advertise) | Solo aparece si está activado `advertise` en el perfil hotspot. En este laboratorio no se utiliza. |

### Versiones XML (`/hotspot/xml/`)

Existen copias para clientes **WISPr**:

- `login.html`, `alogin.html`, `error.html`, `rlogin.html`, `flogout.html`, `logout.html`, `WISPAccessGatewayParam.xsd`

Estas son para autenticación XML/WISPr (clientes móviles corporativos, algunos routers). Con un navegador web normal **no se visualizan**.

## 3. Variables MikroTik (plantillas)

Los archivos HTML usan variables que RouterOS sustituye al servirlos:

| Variable | Uso |
|---|---|
| `$(link-login-only)` | URL para enviar formulario de login |
| `$(link-logout)` | URL para desconectar |
| `$(link-orig)` | Página original que intentaba abrir el usuario |
| `$(link-redirect)` | URL de redirección tras login correcto |
| `$(username)` | Usuario introducido / pre-rellenado |
| `$(error)` | Mensaje de error |
| `$(chap-id)`, `$(chap-challenge)` | Usados por `md5.js` para `http-chap` |
| `$(uptime)`, `$(bytes-in-nice)`, `$(bytes-out-nice)` | Datos de sesión en `status.html` |
| `$(trial)` | Indica si hay acceso de prueba |

## 4. Personalización realizada

### Fecha
23/10/2026

### Objetivo
Darle un aspecto más limpio y acorde al **Panel Web de Tickets QR** creado para `MIKROTIK-LAB`.

### Archivos modificados

| Archivo | Acción |
|---|---|
| `hotspot/login.html` | **Reemplazado** por versión personalizada con estilo oscuro/azul |
| `hotspot/css/style.css` | **Reemplazado** por CSS propio del nuevo diseño |

### Diseño aplicado

- Fondo oscuro con gradiente radial
- Tarjeta centrada con borde sutil y brillo azul
- Cabecera con punto luminoso y texto `MIKROTIK-LAB / ACCESO POR TICKET QR`
- Campos "Código del ticket" y "Contraseña" más claros
- Botón "Conectar" con gradiente azul
- Pie con texto: *"Escanea el QR WiFi primero y luego el QR de acceso"*
- Soporta el flujo `http-chap` (mantiene `md5.js` y el formulario `sendin` oculto)
- Compatible con autologin por URL (`login?username=...&password=...`) gracias a `http-pap` activado

### Backups creados

Se guardaron copias del estado original antes de sustituirlos:

```text
/tmp/login.html.bak
/tmp/style.css.bak
```

También se guardaron en el repositorio:

```text
files/login-mikrotik-original.html
files/login-style-original.css
files/hotspot-login-mejorado/login.html
files/hotspot-login-mejorado/css/style.css
```

## 5. Cómo restaurar el login original

Si se desea volver al diseño por defecto de MikroTik:

```bash
cd /home/armintec/Documentos/MICRO-TIK
sshpass -p 'Dahua2026' scp -P 2222 -o StrictHostKeyChecking=no /tmp/login.html.bak admin@127.0.0.1:/hotspot/login.html
sshpass -p 'Dahua2026' scp -P 2222 -o StrictHostKeyChecking=no /tmp/style.css.bak admin@127.0.0.1:/hotspot/css/style.css
```

O desde RouterOS directamente con WinBox/File List copiando los `.bak`.

## 6. Recomendaciones para unificar el resto

Para que todo el portal tenga la misma identidad visual, se recomienda personalizar:

| Archivo | Prioridad | Razón |
|---|---|---|
| `alogin.html` | Alta | Aparece justo tras loguearse correctamente |
| `status.html` | Alta | Más consultado. Muestra tiempo/tráfico y desconexión |
| `error.html` | Media-Alta | Aparece con errores de ticket/contraseña |
| `logout.html` | Media | Aparece al desconectarse |

El resto (`redirect.html`, `rlogin.html`, `radvert.html`) son mayoritariamente transitorios y apenas se ven.

## 7. Comprobación

Tras subir los archivos, probar con:

1. Conectarse a `MIKROTIK-LAB`
2. Abrir `http://192.168.77.254/login` → debe aparecer el nuevo diseño
3. Probar autologin con QR (`/login?username=...&password=...`) → debe autenticar correctamente
4. Probar login manual con código + contraseña del ticket → debe funcionar
