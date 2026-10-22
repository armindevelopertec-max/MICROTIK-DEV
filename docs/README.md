# Documentación del laboratorio MikroTik CHR + Hotspot

> Índice de la documentación separada del laboratorio. **Empieza por el doc 00** si el
> entorno aún no está preparado, y por el doc 01 cuando ya quieras configurar el hotspot.

---

## Mapa de documentos

```
   ┌─────────────────────────────────────────────────────────────┐
   │  00  ENTORNO Y PREPARACIÓN        ¿Qué es y cómo se monta  │
   │      (bridge, tap, QEMU, hostapd)                          │
   └───────────────────────────┬─────────────────────────────────┘
                               │
   ┌───────────────────────────▼─────────────────────────────────┐
   │  01  COMANDOS MIKROTIK            Catálogo completo        │
   │      (hotspot, timeouts, NAT, diagnóstico)                 │
   └───────────────────────────┬─────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
┌───────▼────────┐  ┌──────────▼─────────┐  ┌─────────▼────────┐
│ 02 ESENCIALES  │  │ 03 VMWARE / VBOX   │  │ 04 MIKROTIK      │
│ el kit mínimo  │  │ el CHR fuera de    │  │    FÍSICO        │
│ de RouterOS    │  │ QEMU               │  │ el router real   │
└────────────────┘  └────────────────────┘  └──────────────────┘
```

---

## Los documentos

| # | Documento | Contenido | Cuándo leerlo |
|---|---|---|---|
| **00** | [`00-ENTORNO-Y-PREPARACION.md`](./00-ENTORNO-Y-PREPARACION.md) | Propósito, arquitectura, requisitos, preparación del host (Fedora), del CHR (QEMU) y del AP (hostapd), arranque/parada, verificación por capas C1–C7, troubleshooting y seguridad. | **Primero.** Antes de tocar nada. |
| **01** | [`01-COMANDOS-MIKROTIK.md`](./01-COMANDOS-MIKROTIK.md) | Sintaxis RouterOS, sistema, red/DHCP/DNS, NAT y firewall, hotspot (servidor, perfil, usuarios), **tabla maestra de timeouts**, ancho de banda, walled-garden, ip-binding, cookies, scripts on-login/logout, RADIUS, diagnóstico, backup/export/import, script completo. | Cuando el entorno ya está arriba y quieres configurar el hotspot. |
| **02** | [`02-COMANDOS-ESENCIALES-MIKROTIK.md`](./02-COMANDOS-ESENCIALES-MIKROTIK.md) | Las 12 reglas de oro de la sintaxis, los 8 comandos del 90%, bloques de comandos imprescindibles por área, safe mode, comandos peligrosos, los 12 `print` de diagnóstico, backup/export/restore, cheat sheet de una página. | Como referencia rápida. Lo que debes **saber de memoria**. |
| **03** | [`03-EQUIVALENTES-VMWARE-VIRTUALBOX.md`](./03-EQUIVALENTES-VMWARE-VIRTUALBOX.md) | Tabla de equivalencias QEMU ↔ VMware ↔ VirtualBox, imágenes CHR oficiales, import del OVA, configuración de red (NAT / host-only / bridged), reenvío de puertos, conversión de imagen con `qemu-img`, reconexión del AP, rendimiento. | Si quieres el CHR en VMware o VirtualBox en lugar de QEMU. |
| **04** | [`04-MIKROTIK-FISICO.md`](./04-MIKROTIK-FISICO.md) | CHR vs hardware, elección de equipo, primer arranque, actualización de RouterOS, bridge y offload por hardware, **`/interface wifi` vs `/interface wireless`**, hotspot sobre la radio real, CAPsMAN, WAN (PPPoE / DHCP / Starlink), licencias, migración de la config del CHR al hardware, hardening, netinstall y reset. | Si vas a montar esto en un RouterBOARD real. |

---

## Documento original

| Documento | Estado |
|---|---|
| [`../DOCUMENTACION-HOTSPOT-CHR.md`](../DOCUMENTACION-HOTSPOT-CHR.md) | Documento narrativo original del proyecto. Se conserva como referencia histórica; los docs 00–04 lo sustituyen y lo ordenan. |

---

## Scripts

| Script | Para qué |
|---|---|
| [`../scripts/iniciar-lab.sh`](../scripts/iniciar-lab.sh) | Levanta todo el laboratorio: bridge `br-mikrotik`, tap `tap-mikrotik`, `hostapd` y el CHR en QEMU con el reenvío de puertos. |
| [`../scripts/parar-lab.sh`](../scripts/parar-lab.sh) | Lo para todo y deja el host limpio. |

```bash
# Uso
./scripts/iniciar-lab.sh     # arrancar
./scripts/parar-lab.sh       # parar
```

---

## Valores de referencia del laboratorio

| Parámetro | Valor |
|---|---|
| **RouterOS** | 7.24.5 (CHR, x86_64) |
| **Bridge del host** | `br-mikrotik` — 192.168.77.1/24 — STP desactivado |
| **Tap** | `tap-mikrotik` |
| **AP (hostapd)** | SSID `MIKROTIK-LAB` — canal 11 |
| **WAN del CHR** | `ether1` — DHCP (salida por el NAT de QEMU) |
| **LAN del hotspot** | `ether2` — 192.168.77.254/24 |
| **Pool DHCP** | 192.168.77.100–192.168.77.199 |
| **Portal** | `http://192.168.77.254/login` |
| **Acceso al CHR** | `ssh -p 2222 admin@127.0.0.1` · WinBox `127.0.0.1:8291` |

---

## Ruta de aprendizaje recomendada

1. **Doc 00** → dejar el laboratorio funcionando y comprobar las capas C1–C7.
2. **Doc 01 §6–§8** → configurar el hotspot y crear el primer usuario.
3. **Doc 01 §9** → entender los timeouts (la tabla que más confunde).
4. **Doc 02** → repasar lo esencial y tener el cheat sheet a mano.
5. **Doc 03** → si quieres replayar el CHR en VMware o VirtualBox.
6. **Doc 04** → cuando dares el salto al RouterBOARD real.

---

## Advertencia

Este entorno es **educativo**. El portal cautivo de RouterOS no trae facturación, cobros ni
panel de cliente: no es un producto comercializable tal cual. Sin licencia CHR, el límite es
**1 Mbps** de subida por interfaz.
