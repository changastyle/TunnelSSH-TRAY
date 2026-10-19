"""Icono de bandeja que mantiene un tunel inverso hacia el droplet.

https://secure.clinicapp.com.ar -> nginx:443 -> 127.0.0.1:3300 -> tunel -> localhost:3000

El backend se elige con BACKEND ("ssh" o "frpc"); ver tunnel_backends.py.
"""
import importlib.util
import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser

import pystray

from tunnel_backends import BACKENDS

if getattr(sys, "frozen", False):
    EXE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", EXE_DIR)
else:
    EXE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = EXE_DIR

BACKEND = "ssh"  # "ssh" (recomendado) o "frpc"

CFG = {
    # --- comun ---
    "local_port": 3000,       # tu app local
    "remote_port": 3300,      # puerto en el servidor (nginx -> tunel)
    "server_host": "10.97.9.51",   # IP ZeroTier del droplet (68.183.99.3 si abris el 22 publico)
    # --- ssh ---
    "server_user": "tunnel",
    "key_file": os.path.join(EXE_DIR, "tunnel_key"),
    "known_hosts": os.path.join(EXE_DIR, "known_hosts"),
    # --- frpc ---
    "frpc_exe": os.path.join(EXE_DIR, "frpc.exe"),
    "frpc_toml": os.path.join(EXE_DIR, "frpc.toml"),
}

PUBLIC_URL = "https://secure.clinicapp.com.ar"
LOG_FILE = os.path.join(EXE_DIR, "tunnel.log")
CREATE_NO_WINDOW = 0x08000000

CONNECTED, CONNECTING, DISCONNECTED = "connected", "connecting", "disconnected"


def _load_icon_drawer():
    """Carga UTILS/ICON-DRAWER.py (el nombre tiene '-', no se puede importar directo)."""
    # primero junto al .exe (permite sobreescribir), luego dentro del bundle
    path = os.path.join(EXE_DIR, "UTILS", "ICON-DRAWER.py")
    if not os.path.exists(path):
        path = os.path.join(BUNDLE_DIR, "UTILS", "ICON-DRAWER.py")
    spec = importlib.util.spec_from_file_location("icon_drawer", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_icon_drawer = _load_icon_drawer()
ICONS = {state: _icon_drawer.draw_icon(state)
         for state in (CONNECTED, CONNECTING, DISCONNECTED)}
LABELS = {
    CONNECTED: "Conectado",
    CONNECTING: "Conectando...",
    DISCONNECTED: "Desconectado",
}


class Tunnel:
    def __init__(self, backend):
        self.backend = backend
        self.state = DISCONNECTED
        self.detail = ""
        self.proc = None
        self.icon = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._lines = queue.SimpleQueue()

    def log(self, msg):
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        except OSError:
            pass

    def set_state(self, state, detail=""):
        self.state = state
        self.detail = detail
        if self.icon:
            self.icon.icon = ICONS[state]
            tip = f"ClinicApp Tunnel - {LABELS[state]}"
            if detail:
                tip += f" ({detail})"
            self.icon.title = tip
            self.icon.update_menu()

    def _reader(self, stream):
        for line in stream:
            self._lines.put(line.rstrip())

    def run(self):
        backoff = 3
        while not self._stop.is_set():
            err = self.backend.availability_error()
            if err:
                self.set_state(DISCONNECTED, err)
                self._wake.wait(30)
                self._wake.clear()
                continue

            self.set_state(CONNECTING)
            self.log(f"Iniciando tunel [{self.backend.name}] ...")
            try:
                self.proc = subprocess.Popen(
                    self.backend.command(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    errors="replace",
                    creationflags=CREATE_NO_WINDOW,
                    cwd=EXE_DIR,
                )
            except OSError as e:
                self.set_state(DISCONNECTED, str(e))
                self._wake.wait(backoff)
                self._wake.clear()
                continue

            threading.Thread(target=self._reader, args=(self.proc.stdout,), daemon=True).start()
            started = time.monotonic()
            while True:
                try:
                    line = self._lines.get(timeout=1)
                    self.log(line)
                    st, detail = self.backend.classify(line)
                    if st:
                        self.set_state(st, detail)
                        if st == CONNECTED:
                            backoff = 3
                except queue.Empty:
                    pass
                if self.proc.poll() is not None:
                    break
                if self.state == CONNECTING and time.monotonic() - started > 6:
                    # vivo > 6s (ssh con ExitOnForwardFailure) => forward activo
                    self.set_state(CONNECTED)
                    backoff = 3
                if self._stop.is_set():
                    break

            if self.proc.poll() is None:
                self.proc.terminate()
            self.proc.wait()
            self.proc = None
            if self._stop.is_set():
                break
            self.set_state(DISCONNECTED, "reconectando")
            self.log(f"tunel caido, reintentando en {backoff}s")
            self._wake.wait(backoff)
            self._wake.clear()
            backoff = min(backoff * 2, 60)

    def reconnect(self):
        self.log("Reconexion manual solicitada")
        self._wake.set()
        if self.proc:
            self.proc.terminate()

    def quit(self):
        self._stop.set()
        self._wake.set()
        if self.proc:
            self.proc.terminate()


def main():
    backend = BACKENDS[BACKEND](CFG)
    tunnel = Tunnel(backend)

    menu = pystray.Menu(
        pystray.MenuItem(lambda item: f"Estado: {LABELS[tunnel.state]}"
                         + (f" - {tunnel.detail}" if tunnel.detail else ""),
                         None, enabled=False),
        pystray.MenuItem(f"Abrir {PUBLIC_URL}", lambda: webbrowser.open(PUBLIC_URL),
                         default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Reconectar", lambda: tunnel.reconnect()),
        pystray.MenuItem("Salir", lambda: (tunnel.quit(), icon.stop())),
    )

    icon = pystray.Icon(
        "clinicapp-tunnel",
        ICONS[DISCONNECTED],
        "ClinicApp Tunnel - Desconectado",
        menu,
    )
    tunnel.icon = icon

    threading.Thread(target=tunnel.run, daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()
