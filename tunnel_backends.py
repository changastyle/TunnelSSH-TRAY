"""Backends de tunel inverso: interfaz comun + implementaciones ssh y frpc.

Un backend sabe tres cosas:
  - command():  la linea de proceso que levanta el tunel
  - classify(): interpreta una linea de salida del proceso -> estado del tunel
  - availability_error(): por que no puede correr en esta maquina (o None)
"""
import os
import shutil
from abc import ABC, abstractmethod


class TunnelBackend(ABC):
    name = "base"

    def __init__(self, cfg):
        self.cfg = cfg  # ver CFG en tray_tunnel.py

    def availability_error(self):
        """Devuelve un mensaje de error si falta un prerequisito, o None."""
        return None

    @abstractmethod
    def command(self):
        """Lista de argumentos del subproceso."""

    @abstractmethod
    def classify(self, line):
        """-> (estado|None, detalle). estado in {'connected','disconnected'}."""


class SSHTunnel(TunnelBackend):
    """ssh -R del OpenSSH de Windows (firmado por MS, pasa Smart App Control).

    En el servidor solo hace falta sshd + una authorized_keys con:
      restrict,permitlisten="127.0.0.1:REMOTE_PORT" <pubkey>
    """
    name = "ssh"

    def availability_error(self):
        if not shutil.which("ssh"):
            return "ssh.exe no encontrado (habilitar OpenSSH Client en Windows)"
        if not os.path.exists(self.cfg["key_file"]):
            return "falta tunnel_key"
        return None

    def command(self):
        c = self.cfg
        return [
            shutil.which("ssh"),
            "-N", "-T", "-v",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={c['known_hosts']}",
            "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes",
            "-i", c["key_file"],
            "-R", f"127.0.0.1:{c['remote_port']}:127.0.0.1:{c['local_port']}",
            f"{c['server_user']}@{c['server_host']}",
        ]

    def classify(self, line):
        low = line.lower()
        if "remote forward success" in low:
            return "connected", ""
        if "permission denied" in low:
            return "disconnected", "clave no autorizada"
        if "remote port forwarding failed" in low:
            return "disconnected", f"puerto {self.cfg['remote_port']} ocupado en servidor"
        if "timed out" in low:
            return "disconnected", "servidor no responde"
        if "connection refused" in low:
            return "disconnected", "conexion rechazada (puerto 22)"
        if "could not resolve hostname" in low or "no route to host" in low:
            return "disconnected", "sin red / DNS"
        return None, ""


class FRPTunnel(TunnelBackend):
    """frpc.exe contra un frps en el droplet (requiere instalar frps alla).

    OJO: Smart App Control bloquea frpc.exe en Windows 11 (binario sin firmar).
    Solo usable si SAC esta desactivado o en otra maquina.
    """
    name = "frpc"

    def availability_error(self):
        if not os.path.exists(self.cfg["frpc_exe"]):
            return "falta frpc.exe (descargar de github.com/fatedier/frp/releases)"
        if not os.path.exists(self.cfg["frpc_toml"]):
            return "falta frpc.toml"
        return None

    def command(self):
        return [self.cfg["frpc_exe"], "-c", self.cfg["frpc_toml"]]

    def classify(self, line):
        low = line.lower()
        if "start proxy success" in low or "login to server success" in low:
            return "connected", ""
        if "connect to server error" in low or "dial tcp" in low:
            return "disconnected", "servidor frps no responde"
        if "token" in low and "invalid" in low:
            return "disconnected", "token invalido"
        if "error" in low:
            return "disconnected", ""
        return None, ""


BACKENDS = {b.name: b for b in (SSHTunnel, FRPTunnel)}
