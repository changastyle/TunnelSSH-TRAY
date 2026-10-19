# Configuracion del servidor (droplet 68.183.99.3)

Pasos ejecutados en la consola web de DigitalOcean (como root).

Flujo: `https://secure.clinicapp.com.ar` -> nginx:443 -> `127.0.0.1:3300`
-> tunel `ssh -R` -> `localhost:3000` en la PC del cliente.

La conexion SSH sale de la PC del cliente hacia el droplet **por la red
privada de ZeroTier** (droplet = `10.97.9.51`), por lo que NO hace falta
abrir el puerto 22 a internet.

## 1. Usuario `tunnel` + clave autorizada

Usuario sin shell, con la clave restringida a solo reenviar el puerto 3300:

```bash
useradd -m -s /usr/sbin/nologin tunnel
mkdir -p /home/tunnel/.ssh
cat > /home/tunnel/.ssh/authorized_keys <<'EOF'
restrict,port-forwarding,permitlisten="127.0.0.1:3300" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK6DmVbd8maQhGOpxkZ7XjXnv/vpXqQ4mw99uOIKFIid tunel-pc-clinicapp
EOF
chmod 700 /home/tunnel/.ssh
chmod 600 /home/tunnel/.ssh/authorized_keys
chown -R tunnel:tunnel /home/tunnel/.ssh
```

## 2. Habilitar port forwarding solo para `tunnel`

El sshd de este servidor tiene el forwarding deshabilitado globalmente.
Se habilita solo para el usuario del tunel:

```bash
cat >> /etc/ssh/sshd_config <<'EOF'

Match User tunnel
    DisableForwarding no
    AllowTcpForwarding remote
    PermitTTY no
EOF
sshd -t && systemctl reload ssh
```

## 3. nginx (reverse proxy -> puerto del tunel)

```bash
cat > /etc/nginx/sites-available/secure.clinicapp.com.ar <<'EOF'
server {
    listen 80;
    server_name secure.clinicapp.com.ar;

    location / {
        proxy_pass http://127.0.0.1:3300;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        client_max_body_size 50m;
    }
}
EOF
ln -sf /etc/nginx/sites-available/secure.clinicapp.com.ar /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

(Copia local de este archivo: `server/secure.clinicapp.com.ar.conf`)

## 4. HTTPS con Let's Encrypt

```bash
apt update && apt install -y certbot python3-certbot-nginx
certbot --nginx -d secure.clinicapp.com.ar --redirect --agree-tos -m TU_EMAIL@ejemplo.com
```

## Verificacion

```bash
# el puerto del tunel solo debe escuchar en localhost:
ss -tlnp | grep 3300
# trafico de prueba una vez el tunel arriba:
curl -v http://127.0.0.1:3300/
```

## Notas

- La clave lleva `restrict` (apaga todo) + `port-forwarding` (reactiva
  solo el forwarding) + `permitlisten` (limita el -R a 127.0.0.1:3300).
  Sin `port-forwarding`, OpenSSH 9.6 rechaza el forward con
  "Server has disabled port forwarding".
- Si alguna vez se quiere exponer el SSH publico (sin ZeroTier), cambiar
  `server_host` en `tray_tunnel.py` a `68.183.99.3` y abrir el 22 en el
  firewall de DO / ufw.
- Backend alternativo `frpc` (`BACKEND = "frpc"` en tray_tunnel.py):
  requiere instalar `frps` en el servidor y NO funciona en PCs con
  Smart App Control (bloquea el .exe sin firmar).
