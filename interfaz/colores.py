"""
colores.py - Colores ANSI para la consola.

Se desactivan automáticamente si la salida no es una terminal (por ejemplo, al
exportar a archivo) o si existe la variable de entorno NO_COLOR.
"""

import os
import re
import sys

# En Windows 10+ esta llamada activa el soporte de secuencias ANSI en la consola.
if os.name == "nt":
    os.system("")

ACTIVOS = sys.stdout.isatty() and "NO_COLOR" not in os.environ

_CODIGOS = {
    "rojo": "31", "verde": "32", "amarillo": "33", "azul": "34",
    "magenta": "35", "cian": "36", "gris": "90", "negrita": "1",
}
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def color(texto: str, nombre: str) -> str:
    if not ACTIVOS:
        return str(texto)
    return f"\x1b[{_CODIGOS[nombre]}m{texto}\x1b[0m"


def sin_color(texto: str) -> str:
    return _ANSI.sub("", texto)


def activar(valor: bool) -> bool:
    """Activa o desactiva los colores. Devuelve el valor anterior."""
    global ACTIVOS
    anterior = ACTIVOS
    ACTIVOS = valor
    return anterior


def rojo(t): return color(t, "rojo")
def verde(t): return color(t, "verde")
def amarillo(t): return color(t, "amarillo")
def azul(t): return color(t, "azul")
def magenta(t): return color(t, "magenta")
def cian(t): return color(t, "cian")
def gris(t): return color(t, "gris")
def negrita(t): return color(t, "negrita")
