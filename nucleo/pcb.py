"""
pcb.py - Estructuras de control: PCB (Process Control Block) y TCB (Thread Control Block).

El PCB es la "ficha" que el kernel guarda por cada proceso. Contiene todo lo que
el sistema operativo necesita para administrarlo: identificador, estado, memoria
asignada y el avance de su ejecución en CPU.

El TCB es la ficha equivalente para cada hilo de ejecución dentro de un proceso.
Un proceso puede tener varios hilos; todos comparten la memoria del proceso
(registrada en el PCB) pero cada hilo tiene su propio contador de programa
y estado.
"""

from dataclasses import dataclass, field
from enum import Enum


class Estado(Enum):
    """Estados del ciclo de vida de un proceso (modelo de 5 estados)."""
    NUEVO = "NUEVO"            # Recién creado, aún no admitido
    LISTO = "LISTO"            # En la cola de listos esperando CPU
    EJECUTANDO = "EJECUTANDO"  # Usando la CPU en este momento
    BLOQUEADO = "BLOQUEADO"    # Esperando un evento (semáforo o recurso)
    TERMINADO = "TERMINADO"    # Finalizó su ráfaga o fue abortado


@dataclass
class TCB:
    """Bloque de Control de Hilo."""
    tid: int                       # Identificador del hilo
    pid_padre: int                 # PID del proceso al que pertenece
    estado: Estado = Estado.NUEVO  # Estado propio del hilo
    contador_programa: int = 0     # Instrucción simulada en la que va el hilo

    def __str__(self) -> str:
        return (f"TID={self.tid} (PID padre={self.pid_padre}) "
                f"estado={self.estado.value} PC={self.contador_programa}")


@dataclass
class PCB:
    """
    Bloque de Control de Proceso.

    Campos obligatorios según el enunciado:
        pid, estado, tamano_mb, rafaga_total, rafaga_restante.
    Campos adicionales que usa el simulador para métricas e integración:
        nombre, tiempo_llegada, tiempo_finalizacion, marcos (memoria),
        hilos (TCB), recursos retenidos, cambios de contexto.
    """
    pid: int
    nombre: str
    tamano_mb: int
    rafaga_total: int
    rafaga_restante: int = -1
    estado: Estado = Estado.NUEVO
    tiempo_llegada: int = 0
    tiempo_primera_cpu: int | None = None
    tiempo_finalizacion: int | None = None
    marcos: list[int] = field(default_factory=list)
    hilos: list[TCB] = field(default_factory=list)
    recursos: list[str] = field(default_factory=list)
    cambios_contexto: int = 0
    motivo_bloqueo: str = ""
    abortado: bool = False

    def __post_init__(self) -> None:
        # Al crearse, la ráfaga restante es igual a la total.
        if self.rafaga_restante < 0:
            self.rafaga_restante = self.rafaga_total

    # ------------------------------------------------------------------ #
    # Cambios de estado: se propagan también a los hilos del proceso.
    # ------------------------------------------------------------------ #
    def cambiar_estado(self, nuevo: Estado) -> None:
        self.estado = nuevo
        for hilo in self.hilos:
            hilo.estado = nuevo

    def avanzar(self, unidades: int) -> None:
        """Consume 'unidades' de ráfaga de CPU y avanza el PC del hilo principal."""
        self.rafaga_restante -= unidades
        if self.hilos:
            self.hilos[0].contador_programa += unidades

    # ------------------------------------------------------------------ #
    # Métricas de planificación
    # ------------------------------------------------------------------ #
    @property
    def tiempo_retorno(self) -> int | None:
        """Turnaround: desde que llegó hasta que terminó."""
        if self.tiempo_finalizacion is None:
            return None
        return self.tiempo_finalizacion - self.tiempo_llegada

    @property
    def tiempo_espera(self) -> int | None:
        """Tiempo en cola de listos = retorno - ráfaga ejecutada."""
        if self.tiempo_retorno is None:
            return None
        ejecutado = self.rafaga_total - self.rafaga_restante
        return self.tiempo_retorno - ejecutado

    @property
    def tiempo_respuesta(self) -> int | None:
        """Desde que llegó hasta que tocó CPU por primera vez."""
        if self.tiempo_primera_cpu is None:
            return None
        return self.tiempo_primera_cpu - self.tiempo_llegada
