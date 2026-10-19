"""Dibuja el icono del tunel (version PIL del ICONO.svg).

La parte naranja del arco se pinta segun el estado del tunel:
  - verde   -> conectado
  - amarillo -> conectando
  - rojo    -> desconectado

Uso:
    from ICON-DRAWER import draw_icon, save_icon   # via importlib (el nombre tiene "-")
    img = draw_icon("connected")       # PIL.Image RGBA 64x64
    save_icon("icono_verde.png", "connected")
"""
import os

from PIL import Image, ImageDraw

# Paleta (64x64 base, igual que ICONO.svg)
GRAY = (141, 147, 151, 255)        # fondo circular (concreto)
BLACK = (20, 18, 16, 255)          # borde grueso de la boca del tunel
ROAD = (38, 40, 43, 255)           # asfalto
YELLOW = (240, 168, 40, 255)       # doble linea central
BORDER = (95, 101, 105, 255)       # borde exterior sutil
PLUG_BODY = (189, 195, 199, 255)   # conector RJ45 (referencia ssh)
PLUG_DARK = (52, 56, 60, 255)      # contorno del conector
GOLD = (212, 172, 42, 255)         # contactos del conector
CABLE = (70, 74, 78, 255)          # cable hacia abajo

STATE_COLORS = {
    "connected": (46, 204, 113, 255),
    "connecting": (241, 196, 15, 255),
    "disconnected": (231, 76, 60, 255),
}

# Se dibuja a 4x y se reduce con LANCZOS para que quede suave en el tray
_SS = 4


def draw_icon(state="disconnected", size=64, color=None):
    """Devuelve un PIL.Image RGBA del icono de tunel.

    state: "connected" | "connecting" | "disconnected"
    color: RGBA opcional para override del color del arco.
    """
    rgba = tuple(color) + (255,) if color else STATE_COLORS[state]
    k = size * _SS / 64.0

    img = Image.new("RGBA", (size * _SS, size * _SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def rect(x0, y0, x1, y1, fill):
        d.rectangle((x0 * k, y0 * k, x1 * k, y1 * k), fill=fill)

    def arch(x0, y0, x1, y1, fill):
        # cuerpo + semicirculo superior (la boca del tunel)
        rect(x0, (y0 + y1) / 2, x1, 66, fill)
        d.pieslice((x0 * k, y0 * k, x1 * k, y1 * k), 180, 360, fill=fill)

    # fondo circular (concreto)
    d.ellipse((k, k, 63 * k, 63 * k), fill=GRAY)

    # boca del tunel: borde negro grueso + interior de color
    arch(12, 12, 52, 52, BLACK)
    arch(18, 18, 46, 46, rgba)

    # camino (todo el ancho del tunel)
    rect(18, 48, 46, 66, ROAD)

    # doble linea amarilla
    rect(30.0, 50, 31.6, 66, YELLOW)
    rect(32.4, 50, 34.0, 66, YELLOW)

    # conector RJ45 (mas grande y arriba de la ruta, lado derecho)
    lw = max(1, round(0.6 * k))
    rect(38.6, 40, 43.8, 45.2, PLUG_BODY)   # punta
    rect(37.6, 45.2, 45.4, 54.3, PLUG_BODY) # cuerpo
    d.rectangle((38.6 * k, 40 * k, 43.8 * k, 45.2 * k), outline=PLUG_DARK, width=lw)
    d.rectangle((37.6 * k, 45.2 * k, 45.4 * k, 54.3 * k), outline=PLUG_DARK, width=lw)
    rect(39.6, 41.3, 40.7, 43.9, GOLD)      # contactos
    rect(41.7, 41.3, 42.8, 43.9, GOLD)
    rect(40.7, 54.3, 42.3, 60, CABLE)       # cable

    # borde sutil + recorte circular
    d.ellipse((k, k, 63 * k, 63 * k), outline=BORDER, width=max(1, round(1.5 * k)))
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse((k, k, 63 * k, 63 * k), fill=255)
    img.putalpha(mask)

    return img.resize((size, size), Image.LANCZOS)


def save_icon(path, state="disconnected", size=64, color=None):
    """Genera el icono y lo guarda como PNG en `path`."""
    img = draw_icon(state=state, size=size, color=color)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img.save(path)
    return path


if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for st in STATE_COLORS:
        p = save_icon(os.path.join(base, "preview_%s.png" % st), st)
        print("generado:", p)
