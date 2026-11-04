"""
entrada.py - Lectura validada de datos desde el teclado.

Todas las entradas del usuario pasan por estas funciones para que el simulador
nunca se caiga ante datos inválidos (letras, decimales, negativos, vacíos,
números gigantes, Ctrl+C, etc.). Esto es clave para la "prueba de estrés en
vivo" donde el catedrático ingresa parámetros aleatorios.

Convención: presionar Enter sin escribir nada CANCELA la operación (devuelve None).
"""

import re

from .colores import gris, rojo

_ENTERO = re.compile(r"[+-]?[0-9]+")
_DECIMAL = re.compile(r"[+-]?[0-9]*[.,][0-9]+")


class Cancelado(Exception):
    """El usuario canceló la operación (Enter vacío o Ctrl+C)."""


def _leer(mensaje: str) -> str:
    try:
        return input(mensaje).strip()
    except KeyboardInterrupt:
        print()
        raise Cancelado()
    # EOFError (fin de la entrada) se deja pasar: el programa principal lo
    # interpreta como salida.


def leer_entero(mensaje: str, minimo: int, maximo: int, permitir_vacio: bool = True) -> int:
    """
    Pide un entero en el rango [minimo, maximo]. Repite hasta que sea válido.
    Lanza Cancelado si el usuario deja la entrada vacía.
    """
    while True:
        texto = _leer(f"{mensaje} {gris(f'[{minimo}-{maximo}]')}: ")
        if texto == "":
            if permitir_vacio:
                raise Cancelado()
            print(rojo("  ✗ Debe ingresar un valor."))
            continue
        # Se acepta un signo opcional seguido solo de dígitos ASCII.
        limpio = texto.replace(" ", "")
        if not _ENTERO.fullmatch(limpio):
            if _DECIMAL.fullmatch(limpio):
                print(rojo(f"  ✗ '{texto}' es decimal: ingrese un número ENTERO."))
            else:
                print(rojo(f"  ✗ '{texto}' no es un número entero válido."))
            continue
        if len(limpio.lstrip("+-")) > 12:
            print(rojo(f"  ✗ Número demasiado grande. Rango permitido: {minimo} a {maximo}."))
            continue
        valor = int(limpio)
        if not minimo <= valor <= maximo:
            print(rojo(f"  ✗ {valor} está fuera de rango. Debe estar entre {minimo} y {maximo}."))
            continue
        return valor


def leer_texto(mensaje: str, maximo: int = 20) -> str:
    """Texto opcional (puede quedar vacío). Se recortan caracteres no imprimibles."""
    texto = _leer(mensaje)
    texto = "".join(c for c in texto if c.isprintable())
    if len(texto) > maximo:
        print(gris(f"  (nombre recortado a {maximo} caracteres)"))
        texto = texto[:maximo]
    return texto


def leer_opcion(mensaje: str, opciones: list[str]) -> str:
    """Pide una opción de una lista cerrada (sin distinguir mayúsculas)."""
    validas = [o.upper() for o in opciones]
    while True:
        texto = _leer(f"{mensaje} {gris('[' + '/'.join(opciones) + ']')}: ").upper()
        if texto == "":
            raise Cancelado()
        if texto in validas:
            return texto
        print(rojo(f"  ✗ Opción inválida. Escriba una de: {', '.join(opciones)}"))


def confirmar(mensaje: str) -> bool:
    try:
        return leer_opcion(mensaje, ["S", "N"]) == "S"
    except Cancelado:
        return False


def pausa() -> None:
    try:
        input(gris("\nPresione Enter para continuar..."))
    except KeyboardInterrupt:
        print()
