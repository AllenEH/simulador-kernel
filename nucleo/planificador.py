"""
planificador.py - Planificador de CPU con algoritmo Round Robin (RR).

Funcionamiento:
  1. Los procesos LISTOS esperan en una cola FIFO (cola de listos).
  2. El despachador toma el proceso del frente y le da la CPU por un máximo de
     QUANTUM unidades de tiempo (q = 3).
  3. Si el proceso termina su ráfaga antes o justo al agotar el quantum, sale
     del sistema (TERMINADO) y libera sus recursos.
  4. Si el quantum se agota y aún le queda ráfaga, ocurre un CAMBIO DE CONTEXTO:
     se guarda su estado en el PCB (ráfaga restante, contador de programa) y el
     proceso regresa al FINAL de la cola de listos.

Por qué Round Robin: es apropiativo y equitativo; ningún proceso acapara la CPU
y todos reciben respuesta en a lo sumo (n-1)*q unidades, ideal para sistemas
interactivos y de tiempo compartido.
"""

from collections import deque

from .pcb import PCB, Estado

QUANTUM = 3


class PlanificadorRR:
    def __init__(self, quantum: int = QUANTUM):
        self.quantum = quantum
        self.cola_listos: deque[PCB] = deque()
        self.reloj = 0                       # Tiempo simulado (unidades de CPU)
        self.en_cpu: PCB | None = None       # Proceso que usó la CPU por última vez
        self.gantt: list[tuple[int, int, int]] = []  # (pid, inicio, fin)
        self.cambios_contexto = 0

    # ------------------------------------------------------------------ #
    # Manejo de la cola de listos
    # ------------------------------------------------------------------ #
    def admitir(self, pcb: PCB) -> None:
        """Coloca un proceso al final de la cola de listos."""
        pcb.cambiar_estado(Estado.LISTO)
        self.cola_listos.append(pcb)

    def retirar(self, pid: int) -> bool:
        """Saca un proceso de la cola (al bloquearse o abortarse)."""
        for pcb in list(self.cola_listos):
            if pcb.pid == pid:
                self.cola_listos.remove(pcb)
                return True
        return False

    def hay_trabajo(self) -> bool:
        return bool(self.cola_listos)

    # ------------------------------------------------------------------ #
    # Despacho de un turno
    # ------------------------------------------------------------------ #
    def ejecutar_turno(self) -> dict | None:
        """
        Ejecuta un turno de Round Robin (máximo un quantum).
        Devuelve un diccionario con lo ocurrido, o None si la cola está vacía.
        """
        if not self.cola_listos:
            return None

        pcb = self.cola_listos.popleft()
        anterior = self.en_cpu

        # Despacho: el proceso pasa a EJECUTANDO.
        pcb.cambiar_estado(Estado.EJECUTANDO)
        if pcb.tiempo_primera_cpu is None:
            pcb.tiempo_primera_cpu = self.reloj

        # Usa la CPU el menor entre el quantum y lo que le falta.
        unidades = min(self.quantum, pcb.rafaga_restante)
        inicio = self.reloj
        self.reloj += unidades
        pcb.avanzar(unidades)
        self.gantt.append((pcb.pid, inicio, self.reloj))
        self.en_cpu = pcb

        resultado = {
            "pcb": pcb,
            "inicio": inicio,
            "fin": self.reloj,
            "unidades": unidades,
            "anterior": anterior,
            "terminado": False,
            "cambio_contexto": False,
        }

        if pcb.rafaga_restante == 0:
            # Terminó su ráfaga dentro del quantum.
            pcb.tiempo_finalizacion = self.reloj
            pcb.cambiar_estado(Estado.TERMINADO)
            resultado["terminado"] = True
        else:
            # Quantum agotado: cambio de contexto y regreso al final de la cola.
            pcb.cambios_contexto += 1
            self.cambios_contexto += 1
            pcb.cambiar_estado(Estado.LISTO)
            self.cola_listos.append(pcb)
            resultado["cambio_contexto"] = True

        return resultado
