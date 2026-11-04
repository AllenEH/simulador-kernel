"""
laboratorio.py - Modo Laboratorio: ejemplos manipulables para entender los
algoritmos del simulador.

Todo se ejecuta sobre kernels / planificadores NUEVOS, así que nunca altera la
simulación principal del usuario (igual que los casos de prueba de escenarios.py).

  1. Predicción Round Robin: el usuario adivina qué hará la CPU en cada turno.
  2. Comparador de quantums: mismas ráfagas con distintos q (muestra por qué q = 3).
  3. Laboratorio de memoria: crear y terminar procesos y ver cómo se reparten
     las páginas entre los marcos (paginación simple).
"""

import random

from nucleo import ErrorKernel, Kernel
from nucleo.pcb import PCB
from nucleo.planificador import QUANTUM, PlanificadorRR

from . import vistas
from .colores import gris, negrita, rojo, verde
from .entrada import Cancelado, leer_entero, leer_opcion


# ---------------------------------------------------------------------- #
# 1. Predicción de Round Robin
# ---------------------------------------------------------------------- #
def prediccion_rr() -> None:
    """Reto: antes de cada turno el usuario predice qué pasará; el kernel responde."""
    cantidad = leer_entero("¿Cuántos procesos en el escenario?", 2, 6)
    k = Kernel()
    for i in range(cantidad):
        k.crear_proceso(f"P{i + 1}", 4, random.randint(2, 10))
    q = k.planificador.quantum
    print(gris(f"\nTodos llegan en t=0 y el quantum es q={q}. "
               "Enter sin escribir nada = terminar el reto.\n"))
    vistas.tabla_procesos(k)

    puntos = total = 0
    try:
        while k.planificador.hay_trabajo():
            cola = k.planificador.cola_listos
            print()
            vistas.cola_listos(k)
            actual = cola[0]
            usa = min(q, actual.rafaga_restante)
            termina = usa == actual.rafaga_restante
            if len(cola) > 1:
                siguiente = cola[1].pid
            else:
                siguiente = None if termina else actual.pid

            resp_uso = leer_entero(
                f"¿Cuántas unidades de CPU usará P{actual.pid} "
                f"(le quedan {actual.rafaga_restante})?", 1, q)
            resp_sig = None
            if siguiente is not None:
                resp_sig = leer_entero("Tras este turno, ¿qué PID quedará al frente de la cola?",
                                       1, cantidad)

            marca = len(k.bitacora)
            k.ejecutar_turno()
            for evento in k.bitacora[marca:]:
                print(vistas.linea_bitacora(*evento))

            total += 1
            if resp_uso == usa:
                puntos += 1
                print(verde("  ✓ Correcto: usa " + str(usa) + " u."))
            else:
                print(rojo(f"  ✗ Usó {usa} u: es el MENOR entre el quantum ({q}) "
                           f"y la ráfaga restante."))
            if resp_sig is not None:
                total += 1
                if resp_sig == siguiente:
                    puntos += 1
                    print(verde(f"  ✓ Correcto: P{siguiente} pasa al frente."))
                else:
                    print(rojo(f"  ✗ Quedó P{siguiente} al frente: si el proceso no terminó "
                               "va al FINAL de la cola; si terminó, sale del sistema."))
    except Cancelado:
        print(gris("\nReto terminado antes de tiempo."))

    if total:
        print(negrita(f"\nPuntaje: {puntos}/{total} predicciones correctas."))
    print()
    vistas.gantt(k.planificador.gantt)
    if not k.planificador.hay_trabajo():
        print()
        vistas.tabla_metricas(k)


# ---------------------------------------------------------------------- #
# 2. Comparador de quantums
# ---------------------------------------------------------------------- #
def _simular(rafagas: list[int], quantum: int) -> tuple[float, float, float, int]:
    """RR para ráfagas que llegan en t=0. Devuelve (espera, retorno, respuesta, cambios ctx)."""
    plan = PlanificadorRR(quantum)
    pcbs = [PCB(pid=i + 1, nombre=f"P{i + 1}", tamano_mb=0, rafaga_total=r)
            for i, r in enumerate(rafagas)]
    for pcb in pcbs:
        plan.admitir(pcb)
    while plan.ejecutar_turno():
        pass
    n = len(pcbs)
    return (sum(p.tiempo_espera for p in pcbs) / n,
            sum(p.tiempo_retorno for p in pcbs) / n,
            sum(p.tiempo_respuesta for p in pcbs) / n,
            plan.cambios_contexto)


def comparar_quantums() -> None:
    """Mismas ráfagas, varios quantums: muestra el equilibrio del quantum."""
    cantidad = leer_entero("¿Cuántos procesos?", 2, 8)
    rafagas = [leer_entero(f"  Ráfaga de P{i + 1}", 1, 50) for i in range(cantidad)]
    propio = leer_entero("Un quantum propio para comparar", 1, 50)
    quantums = sorted({1, 2, QUANTUM, 5, 10, 50, propio})

    filas = []
    for q in quantums:
        espera, retorno, respuesta, cambios = _simular(rafagas, q)
        etiqueta = f"{q} (oficial)" if q == QUANTUM else str(q)
        filas.append([etiqueta, f"{espera:.2f}", f"{retorno:.2f}", f"{respuesta:.2f}", cambios])
    print(negrita(f"\nRáfagas: {rafagas}"))
    vistas.tabla(["Quantum", "Espera prom.", "Retorno prom.", "Respuesta prom.", "Cambios ctx"],
                 filas)
    print(gris("  q muy pequeño → respuesta rápida pero MUCHOS cambios de contexto (costo extra)."))
    print(gris("  q muy grande  → pocos cambios de contexto, pero se comporta como FCFS "
               "(q=50 equivale a no apropiar)."))
    print(gris(f"  La simulación oficial siempre usa q = {QUANTUM}."))


# ---------------------------------------------------------------------- #
# 3. Laboratorio de memoria
# ---------------------------------------------------------------------- #
def laboratorio_memoria() -> None:
    """Sandbox de paginación: se crean y terminan procesos y se ve el reparto de marcos."""
    k = Kernel()
    marca = 0
    print(gris("Sandbox de memoria: no afecta la simulación principal. "
               "Cada marco muestra P<proceso>.<página>."))
    vistas.mapa_memoria(k)
    while True:
        try:
            opcion = leer_opcion(
                "Acción (1=crear proceso, 2=terminar proceso, 3=demo de dispersión, "
                "4=reiniciar, 0=salir)", ["0", "1", "2", "3", "4"])
            ultimo_pid = None
            if opcion == "0":
                return
            if opcion == "4":
                k, marca = Kernel(), 0
            elif opcion == "1":
                tamano = leer_entero("Tamaño del proceso (MB)", 1, 10**6)
                pcb = k.crear_proceso("", tamano, 5)
                ultimo_pid = pcb.pid if pcb else None
            elif opcion == "2":
                vivos = k.procesos_vivos()
                if not vivos:
                    print(gris("  No hay procesos para terminar."))
                else:
                    print(gris("Procesos: " + ", ".join(f"P{p.pid}({p.tamano_mb} MB)" for p in vivos)))
                    k.abortar(leer_entero("PID a terminar", 1, 10**9))
            elif opcion == "3":
                k, marca = Kernel(), 0
                for nombre in ("A", "B", "C"):
                    k.crear_proceso(nombre, 20, 5)
                k.abortar(2)                       # B libera 5 marcos en el "medio"
                pcb = k.crear_proceso("D", 32, 5)  # D necesita 8 marcos: no caben juntos
                ultimo_pid = pcb.pid if pcb else None
                print(gris("\nDemo: A, B y C (20 MB = 5 marcos c/u) → se termina B → "
                           "entra D (32 MB = 8 marcos)."))

            for evento in k.bitacora[marca:]:
                print(vistas.linea_bitacora(*evento))
            marca = len(k.bitacora)
            vistas.mapa_memoria(k)
            if ultimo_pid is not None:
                vistas.tabla_paginas(k, ultimo_pid)
            if opcion == "3":
                print(gris("  D ocupó los marcos que dejó B y siguió en otros: sus páginas NO son "
                           "contiguas.\n  Por eso la paginación no sufre fragmentación externa."))
        except ErrorKernel as error:
            print(rojo(f"  ✗ {error}"))
        except Cancelado:
            return