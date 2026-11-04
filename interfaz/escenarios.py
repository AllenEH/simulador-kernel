"""
escenarios.py - Casos de prueba de la Bitácora del informe.

Cada caso se ejecuta sobre un kernel NUEVO (no altera la simulación del usuario)
y produce un volcado de texto listo para copiar al documento:

  1. Rechazo de procesos por falta de RAM.
  2. Sucesión de ráfagas en Round Robin.
  3. Efectividad del semáforo ante condiciones de carrera.
  4. Detección y posterior eliminación de un Deadlock.
"""

import io
from contextlib import redirect_stdout
from datetime import datetime

from nucleo import Kernel
from nucleo.pcb import PCB
from nucleo.planificador import PlanificadorRR
from nucleo.sincronizacion import simular_condicion_carrera

from . import colores, vistas
from .colores import gris, negrita, rojo, verde


def _volcar_bitacora(kernel: Kernel, desde: int = 0) -> int:
    for evento in kernel.bitacora[desde:]:
        print(vistas.linea_bitacora(*evento))
    return len(kernel.bitacora)


# ---------------------------------------------------------------------- #
def caso_memoria() -> None:
    vistas.titulo("CASO 1: Rechazo de procesos por falta de RAM (Out of Memory)")
    print("RAM de 100 MB dividida en 25 marcos de 4 MB. Se crean procesos hasta llenarla.\n")
    k = Kernel()
    for nombre, tamano, rafaga in [("Navegador", 40, 6), ("Editor", 40, 4),
                                   ("Compilador", 30, 5), ("Terminal", 20, 3),
                                   ("Reloj", 1, 2), ("BaseDatos", 150, 9)]:
        print(gris(f"> crear proceso '{nombre}' de {tamano} MB"))
        k.crear_proceso(nombre, tamano, rafaga)
    _volcar_bitacora(k)
    vistas.mapa_memoria(k)
    print(negrita("\nResultado esperado:"))
    print("  • Navegador (40) y Editor (40) entran: quedan 20 MB (5 marcos).")
    print("  • Compilador (30 MB = 8 marcos) se RECHAZA: solo hay 5 marcos libres.")
    print("  • Terminal (20 MB = 5 marcos) entra y la RAM queda al 100%.")
    print("  • Reloj (1 MB) y BaseDatos (150 MB) se RECHAZAN: no hay marcos libres.")


# ---------------------------------------------------------------------- #
def caso_round_robin() -> None:
    vistas.titulo("CASO 2: Sucesión de ráfagas en Round Robin (q = 3)")
    k = Kernel()
    for nombre, rafaga in [("P_A", 7), ("P_B", 4), ("P_C", 9), ("P_D", 2)]:
        k.crear_proceso(nombre, 8, rafaga)
    print("Procesos (todos llegan en t=0): P1=7, P2=4, P3=9, P4=2 unidades de ráfaga.\n")
    k.ejecutar_hasta_vaciar()
    _volcar_bitacora(k)
    print()
    vistas.gantt(k.planificador.gantt)
    print()
    vistas.tabla_metricas(k)


# ---------------------------------------------------------------------- #
def caso_semaforo() -> None:
    vistas.titulo("CASO 3: Efectividad del semáforo ante condiciones de carrera")
    hilos, incrementos = 2, 3
    print(f"{hilos} hilos incrementan la variable global {incrementos} veces cada uno.")
    print("Cada incremento = LEER → CALCULAR → ESCRIBIR; se cambia de hilo tras cada instrucción.\n")

    final, esperado, traza = simular_condicion_carrera(hilos, incrementos, usar_semaforo=False)
    print(negrita("a) SIN semáforo:"))
    for linea in traza[:12]:
        print("   " + linea)
    if len(traza) > 12:
        print(gris(f"   ... ({len(traza) - 12} instrucciones más)"))
    print(f"   Resultado: {rojo(final)} | Esperado: {esperado} → "
          + rojo(f"se perdieron {esperado - final} actualizaciones (condición de carrera)"))

    final, esperado, traza = simular_condicion_carrera(hilos, incrementos, usar_semaforo=True)
    print(negrita("\nb) CON semáforo binario (wait/signal):"))
    for linea in traza[:14]:
        print("   " + linea)
    if len(traza) > 14:
        print(gris(f"   ... ({len(traza) - 14} instrucciones más)"))
    print(f"   Resultado: {verde(final)} | Esperado: {esperado} → " + verde("correcto, sin pérdidas"))

    print(negrita("\nc) Cola de espera del semáforo con procesos del kernel:"))
    k = Kernel()
    for nombre in ("Escritor1", "Escritor2", "Escritor3"):
        k.crear_proceso(nombre, 4, 5)
    k.wait(1)
    k.wait(2)
    k.wait(3)
    k.escribir_variable(1)
    k.signal(1)
    k.escribir_variable(2)
    k.signal(2)
    k.escribir_variable(3)
    k.signal(3)
    _volcar_bitacora(k)
    vistas.estado_semaforo(k)


# ---------------------------------------------------------------------- #
def caso_deadlock() -> None:
    vistas.titulo("CASO 4: Detección y eliminación de un Deadlock")
    k = Kernel()
    a, b = k.forzar_deadlock()
    _volcar_bitacora(k)
    print()
    vistas.estado_recursos(k)
    print(gris(f"\n> abortar proceso {a.pid} (víctima elegida para romper el ciclo)"))
    marca = len(k.bitacora)
    k.abortar(a.pid)
    k.verificar_deadlock()
    marca = _volcar_bitacora(k, marca)
    print()
    vistas.estado_recursos(k)
    print(gris(f"\n> ejecutar planificador: P{b.pid} ya puede terminar"))
    k.ejecutar_hasta_vaciar()
    _volcar_bitacora(k, marca)
    print()
    vistas.tabla_procesos(k)


CASOS = [
    ("Rechazo de procesos por falta de RAM", caso_memoria),
    ("Sucesión de ráfagas en Round Robin", caso_round_robin),
    ("Semáforo ante condiciones de carrera", caso_semaforo),
    ("Detección y eliminación de Deadlock", caso_deadlock),
]


def exportar_todos(ruta: str | None = None) -> str:
    """Ejecuta los 4 casos y guarda la salida (sin colores) en un archivo de texto."""
    if ruta is None:
        ruta = f"casos_de_prueba_{datetime.now():%Y%m%d_%H%M%S}.txt"
    buffer = io.StringIO()
    anterior = colores.activar(False)
    try:
        with redirect_stdout(buffer):
            print("CASOS DE PRUEBA - SIMULADOR DE FUNCIONES DEL KERNEL")
            print(f"Generado: {datetime.now():%Y-%m-%d %H:%M:%S}")
            for _, caso in CASOS:
                caso()
                print()
    finally:
        colores.activar(anterior)
    with open(ruta, "w", encoding="utf-8") as archivo:
        archivo.write(buffer.getvalue())
    return ruta


# ---------------------------------------------------------------------- #
def calculo_teorico_rr(rafagas: list[int], quantum: int = 3) -> None:
    """
    Calcula la planificación RR para un conjunto de ráfagas (todas llegan en t=0)
    sin tocar el kernel del usuario. Sirve para los cálculos teóricos del informe.
    """
    planificador = PlanificadorRR(quantum)
    procesos = [PCB(pid=i + 1, nombre=f"P{i + 1}", tamano_mb=0, rafaga_total=r)
                for i, r in enumerate(rafagas)]
    for pcb in procesos:
        planificador.admitir(pcb)
    while planificador.ejecutar_turno():
        pass
    vistas.gantt(planificador.gantt)
    print()
    filas = [[p.pid, p.rafaga_total, p.tiempo_finalizacion, p.tiempo_retorno, p.tiempo_espera]
             for p in procesos]
    vistas.tabla(["Proceso", "Ráfaga", "Fin", "Retorno", "Espera"], filas)
    n = len(procesos)
    espera = sum(p.tiempo_espera for p in procesos)
    retorno = sum(p.tiempo_retorno for p in procesos)
    print(f"  Espera promedio  = ({' + '.join(str(p.tiempo_espera) for p in procesos)}) / {n} = {espera / n:.2f}")
    print(f"  Retorno promedio = ({' + '.join(str(p.tiempo_retorno) for p in procesos)}) / {n} = {retorno / n:.2f}")
    print(f"  Cambios de contexto por quantum agotado: {planificador.cambios_contexto}")
