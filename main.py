"""
main.py - Punto de entrada del Simulador de Funciones del Kernel.

Ejecutar con:
    python main.py

Opciones:
    python main.py --casos     Ejecuta los 4 casos de prueba y termina.
    python main.py --exportar  Exporta los 4 casos de prueba a un archivo .txt.
"""

import sys

if sys.version_info < (3, 10):
    sys.exit("Se requiere Python 3.10 o superior.")

# Evita errores con acentos y caracteres de caja en consolas de Windows.
for flujo in (sys.stdout, sys.stderr):
    try:
        flujo.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from interfaz import escenarios  # noqa: E402
from interfaz.consola import Consola  # noqa: E402


def main() -> None:
    argumento = sys.argv[1] if len(sys.argv) > 1 else ""
    if argumento == "--casos":
        for _, caso in escenarios.CASOS:
            caso()
        return
    if argumento == "--exportar":
        print(f"Casos exportados a: {escenarios.exportar_todos()}")
        return
    try:
        Consola().iniciar()
    except (EOFError, KeyboardInterrupt):
        print("\nSimulador finalizado.")


if __name__ == "__main__":
    main()
