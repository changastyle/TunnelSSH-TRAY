# Proceso: App de bandeja con tunel inverso a droplet DigitalOcean

Conversacion de desarrollo (15-19 oct 2026).

## Objetivo

App Python con icono de bandeja (Windows) que mantiene un tunel inverso
hacia el droplet `68.183.99.3`, de modo que al llamar a una URL publica
el servidor reenvie el trafico a `localhost:3000` de la PC — equivalente
self-hosted de Cloudflare Tunnel usando el propio droplet.

## Decisiones iniciales

- Tecnologia: inicialmente **frp** (frps + frpc), equivalente directo de cloudflared.
- Puerto local a exponer: **3000**.
- Acceso al servidor: root + clave, pero solo via **consola web de DigitalOcean**
  (puerto 22 filtrado para esta IP).
- URL publica: `https://secure.clinicapp.com.ar` (DNS ya apuntaba a 68.183.99.3),
  con HTTPS via certbot/Let's Encrypt.

## Problema 1: Smart App Control bloquea frpc.exe

Windows 11 con **Smart App Control = On** bloqueo `frpc.exe`
("aplicacion potencialmente no deseada", binario sin firma). SAC no admite
exclusiones ni "ejecutar de todos modos"; desactivarlo es permanente.

**Decision: cambiar a `ssh -R`** con el OpenSSH integrado de Windows
(`C:\Windows\System32\OpenSSH\ssh.exe`, firmado por Microsoft).
Beneficio extra: no hay que instalar nada en el servidor (sshd ya corre ahi).

## Problema 2: el puerto 22 no respondia desde la IP publica

El usuario descubrio que el 22 funcionaba "desde una VPN" — resulto ser
**ZeroTier**: el droplet tiene IP de overlay `10.97.9.51` y la PC `10.97.9.149`.
El trafico ZT va cifrado por UDP/9993 y esquiva el firewall publico.

**Decision: el tunel apunta a `10.97.9.51`** — no hace falta abrir el 22 a internet.

## Arquitectura final

```
Chrome → https://secure.clinicapp.com.ar
      → nginx :443/:80 (droplet)
      → 127.0.0.1:3300 (droplet, escuchado por sshd)
      → tunel SSH -R sobre ZeroTier (10.97.9.51)
      → localhost:3000 (PC del usuario)
```

Quien inicia la conexion es **la PC** (saliente, hacia el droplet); el
servidor reusa ese canal en sentido inverso. Por eso funciona detras de
NAT/CGNAT sin abrir puertos en el router.

### Codigo (lado PC)

- `tunnel_backends.py` — interfaz `TunnelBackend` (ABC) con `command()`,
  `classify()`, `availability_error()`; implementaciones `SSHTunnel` y
  `FRPTunnel` (frpc queda disponible para maquinas sin SAC).
- `tray_tunnel.py` — supervisor + pystray: elige backend con `BACKEND`,
  icono por estado, menu Estado/Abrir URL/Reconectar/Salir, log en
  `tunnel.log`, backoff de reintento hasta 60s. Iconos dibujados por
  `UTILS/ICON-DRAWER.py` (importlib por el nombre con guion; busca junto
  al exe y luego en el bundle `_MEIPASS`).
- `tunnel_key` / `tunnel_key.pub` — par ed25519 sin passphrase, generado con
  `ssh-keygen -t ed25519 -N '""'`.
- `build.bat` — `pyinstaller --noconsole --onefile --name ClinicTunnel
  --add-data "UTILS;UTILS" tray_tunnel.py` + copia `tunnel_key` a `dist\`.

### Config (lado servidor) — `server/README-CONFIG-SERVER.md`

1. Usuario `tunnel` (shell `nologin`) con `authorized_keys`:
   `restrict,port-forwarding,permitlisten="127.0.0.1:3300" <pubkey>`
2. `sshd_config` — `Match User tunnel` con `DisableForwarding no`,
   `AllowTcpForwarding remote`, `PermitTTY no` + `systemctl reload ssh`.
3. nginx vhost `secure.clinicapp.com.ar` → `proxy_pass http://127.0.0.1:3300`
   (con headers de websocket/X-Forwarded).
4. `certbot --nginx -d secure.clinicapp.com.ar --redirect`.

## Incidencias resueltas durante el setup

1. **authorized_keys truncado (0 bytes)** — un heredoc mal pegado vacio el
   archivo a las 15:07; los intentos pasaban de "Accepted publickey" a
   "Connection reset [preauth]". Se recreo el archivo.

2. **"Server has disabled port forwarding"** pese a `Match User tunnel` con
   `AllowTcpForwarding remote` (verificado via `sshd -T -C`). La causa real:
   la opcion `restrict` de authorized_keys deshabilita todo forwarding y
   `permitlisten` sola NO lo reactiva en OpenSSH 9.6. **Fix: agregar
   `port-forwarding` entre `restrict` y `permitlisten`.**

   Resultado: `remote forward success for: listen 127.0.0.1:3300`.

3. **frpc descartado** por SAC; la interfaz de backends deja la opcion
   abierta (`BACKEND = "frpc"`) para otras maquinas.

## Estado final verificado

- Tunel arriba: `remote forward success`, icono verde.
- End-to-end: `http://secure.clinicapp.com.ar` devolvia el `http.server`
  de prueba corriendo en `localhost:3000` (listado de la carpeta).
- **Pendiente:** certbot (paso 4) para `https://` con candado valido; el
  servidor de prueba en el 3000 se apaga cuando la app real use el puerto.

## Seguridad

- La clave del tunel solo permite el `-R` a `127.0.0.1:3300` (sin shell,
  sin `-L` — `AllowTcpForwarding remote` lo bloquea a nivel sshd).
- SSH viaja por la red privada ZeroTier: el puerto 22 publico sigue cerrado.
- Token/clave: la privada queda solo en la PC (`tunnel_key`, junto al exe).
