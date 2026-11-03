"""
kernel.py - Núcleo del simulador. Integra los cinco componentes:

    PCB/TCB ............ pcb.py
    Planificador RR .... planificador.py
    Memoria ............ memoria.py
    Semáforo ........... sincronizacion.py
    Recursos/Deadlock .. recursos.py

Es la única clase con la que habla la interfaz de consola. Cada acción del
kernel queda registrada en la BITÁCORA (lista de eventos con marca de tiempo),
que la interfaz muestra en pantalla y puede exportar a un archivo de texto
para la sección de casos de prueba del informe.
"""

from datetime import datetime

from .memoria import AdministradorMemoria, ErrorMemoriaInsuficiente
from .pcb import PCB, TCB, Estado
from .planificador import PlanificadorRR
from .recursos import ErrorRecurso, GestorRecursos
from .sincronizacion import ErrorSemaforo, SemaforoBinario

# Límites de validación (protegen al simulador de entradas absurdas)
MAX_RAFAGA = 1000
MAX_TAMANO_MB = 100_000
MAX_HILOS = 8
MAX_NOMBRE = 20


class ErrorKernel(Exception):
    """Error de validación u operación inválida en el kernel."""


class Kernel:
    def __init__(self) -> None:
        self.memoria = AdministradorMemoria()
        self.planificador = PlanificadorRR()
        self.semaforo = SemaforoBinario("mutex")
        self.recursos = GestorRecursos()
        self.procesos: dict[int, PCB] = {}
        self.variable_global = 0          # "Variable Global Compartida" (sección crítica)
        self.bitacora: list[tuple[int, str, str]] = []  # (tiempo, nivel, mensaje)
        self._siguiente_pid = 1
        self._siguiente_tid = 1

    # ================================================================== #
    # Bitácora
    # ================================================================== #
    def registrar(self, nivel: str, mensaje: str, tiempo: int | None = None) -> None:
        """Niveles: INFO, OK, CPU, CTX, ERROR, ALERTA. Por defecto usa el reloj actual."""
        if tiempo is None:
            tiempo = self.planificador.reloj
        self.bitacora.append((tiempo, nivel, mensaje))

    def exportar_bitacora(self, ruta: str | None = None) -> str:
        if ruta is None:
            ruta = f"bitacora_{datetime.now():%Y%m%d_%H%M%S}.txt"
        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.write("BITÁCORA DEL SIMULADOR DE KERNEL\n")
            archivo.write(f"Generada: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
            archivo.write("=" * 70 + "\n")
            for tiempo, nivel, mensaje in self.bitacora:
                archivo.write(f"[t={tiempo:>4}] {nivel:<6} {mensaje}\n")
        return ruta

    # ================================================================== #
    # Consultas
    # ================================================================== #
    def obtener(self, pid: int) -> PCB:
        if pid not in self.procesos:
            raise ErrorKernel(f"No existe un proceso con PID {pid}.")
        return self.procesos[pid]

    def obtener_vivo(self, pid: int) -> PCB:
        """Proceso que existe y no ha terminado."""
        pcb = self.obtener(pid)
        if pcb.estado == Estado.TERMINADO:
            raise ErrorKernel(f"El proceso {pid} ya terminó.")
        return pcb

    def obtener_activo(self, pid: int) -> PCB:
        """Proceso vivo y NO bloqueado (puede hacer solicitudes)."""
        pcb = self.obtener_vivo(pid)
        if pcb.estado == Estado.BLOQUEADO:
            raise ErrorKernel(
                f"El proceso {pid} está BLOQUEADO ({pcb.motivo_bloqueo}); no puede hacer solicitudes.")
        return pcb

    def procesos_vivos(self) -> list[PCB]:
        return [p for p in self.procesos.values() if p.estado != Estado.TERMINADO]

    # ================================================================== #
    # A. Gestión de procesos
    # ================================================================== #
    def crear_proceso(self, nombre: str, tamano_mb: int, rafaga: int, hilos: int = 1) -> PCB | None:
        """
        Crea un proceso: valida datos, pide memoria y lo admite en la cola de listos.
        Si no hay memoria suficiente, el proceso se RECHAZA (Out of Memory) y se
        devuelve None.
        """
        nombre = (nombre or "").strip()[:MAX_NOMBRE]
        if not isinstance(tamano_mb, int) or not 1 <= tamano_mb <= MAX_TAMANO_MB:
            raise ErrorKernel(f"Tamaño inválido: debe ser un entero entre 1 y {MAX_TAMANO_MB} MB.")
        if not isinstance(rafaga, int) or not 1 <= rafaga <= MAX_RAFAGA:
            raise ErrorKernel(f"Ráfaga inválida: debe ser un entero entre 1 y {MAX_RAFAGA}.")
        if not isinstance(hilos, int) or not 1 <= hilos <= MAX_HILOS:
            raise ErrorKernel(f"Cantidad de hilos inválida: entre 1 y {MAX_HILOS}.")

        pid = self._siguiente_pid
        nombre = nombre or f"Proceso{pid}"
        try:
            marcos = self.memoria.asignar(pid, tamano_mb)
        except ErrorMemoriaInsuficiente as error:
            self.registrar("ERROR", f"Proceso '{nombre}' RECHAZADO. {error}")
            return None

        self._siguiente_pid += 1
        pcb = PCB(pid=pid, nombre=nombre, tamano_mb=tamano_mb, rafaga_total=rafaga,
                  tiempo_llegada=self.planificador.reloj, marcos=marcos)
        for _ in range(hilos):
            pcb.hilos.append(TCB(tid=self._siguiente_tid, pid_padre=pid))
            self._siguiente_tid += 1
        self.procesos[pid] = pcb
        self.planificador.admitir(pcb)
        self.registrar(
            "OK",
            f"Proceso creado: PID={pid} '{nombre}' {tamano_mb} MB, ráfaga={rafaga}, "
            f"hilos={hilos}. Marcos asignados: {marcos}. "
            f"RAM libre: {self.memoria.memoria_libre_mb()} MB. Estado: LISTO.")
        return pcb

    def crear_hilo(self, pid: int) -> TCB:
        pcb = self.obtener_vivo(pid)
        if len(pcb.hilos) >= MAX_HILOS:
            raise ErrorKernel(f"El proceso {pid} ya tiene el máximo de {MAX_HILOS} hilos.")
        tcb = TCB(tid=self._siguiente_tid, pid_padre=pid, estado=pcb.estado)
        self._siguiente_tid += 1
        pcb.hilos.append(tcb)
        self.registrar("OK", f"Hilo TID={tcb.tid} creado en el proceso PID={pid} "
                             f"(comparte sus {pcb.tamano_mb} MB de memoria).")
        return tcb

    # ================================================================== #
    # Planificación Round Robin
    # ================================================================== #
    def ejecutar_turno(self) -> dict | None:
        """Ejecuta un quantum del planificador y registra lo sucedido."""
        resultado = self.planificador.ejecutar_turno()
        if resultado is None:
            bloqueados = [p.pid for p in self.procesos_vivos() if p.estado == Estado.BLOQUEADO]
            if bloqueados:
                self.registrar("ALERTA", f"Cola de listos vacía. Procesos BLOQUEADOS: {bloqueados}. "
                                         "La CPU queda ociosa hasta que se desbloqueen.")
            else:
                self.registrar("INFO", "Cola de listos vacía: no hay procesos que ejecutar (CPU ociosa).")
            return None

        pcb: PCB = resultado["pcb"]
        anterior: PCB | None = resultado["anterior"]
        if anterior is not None and anterior.pid != pcb.pid:
            self.registrar("CTX", f"Despachador: carga el contexto de P{pcb.pid} desde su PCB "
                                  f"(PC={pcb.hilos[0].contador_programa - resultado['unidades']}).",
                          tiempo=resultado["inicio"])
        self.registrar("CPU", f"P{pcb.pid} '{pcb.nombre}' ejecuta {resultado['unidades']} u "
                              f"(t={resultado['inicio']}->{resultado['fin']}). "
                              f"Ráfaga restante: {pcb.rafaga_restante}/{pcb.rafaga_total}.",
                          tiempo=resultado["inicio"])
        if resultado["cambio_contexto"]:
            self.registrar("CTX", f"Quantum agotado (q={self.planificador.quantum}). CAMBIO DE CONTEXTO: "
                                  f"se guarda el estado de P{pcb.pid} (restante={pcb.rafaga_restante}) "
                                  f"y regresa al FINAL de la cola de listos.")
        if resultado["terminado"]:
            self.registrar("OK", f"P{pcb.pid} TERMINÓ en t={pcb.tiempo_finalizacion}. "
                                 f"Retorno={pcb.tiempo_retorno}, Espera={pcb.tiempo_espera}.")
            self._liberar_todo(pcb)
        return resultado

    def ejecutar_hasta_vaciar(self, max_turnos: int = 100_000) -> int:
        """Ejecuta turnos hasta que la cola de listos quede vacía."""
        turnos = 0
        while self.planificador.hay_trabajo() and turnos < max_turnos:
            self.ejecutar_turno()
            turnos += 1
        bloqueados = [p.pid for p in self.procesos_vivos() if p.estado == Estado.BLOQUEADO]
        if bloqueados:
            self.registrar("ALERTA", f"Ejecución detenida: quedan procesos BLOQUEADOS {bloqueados}.")
        return turnos

    def metricas(self) -> dict:
        terminados = [p for p in self.procesos.values()
                      if p.tiempo_finalizacion is not None and not p.abortado]
        n = len(terminados)
        reloj = self.planificador.reloj
        return {
            "terminados": terminados,
            "espera_promedio": sum(p.tiempo_espera for p in terminados) / n if n else 0,
            "retorno_promedio": sum(p.tiempo_retorno for p in terminados) / n if n else 0,
            "respuesta_promedio": sum(p.tiempo_respuesta for p in terminados) / n if n else 0,
            "throughput": n / reloj if reloj else 0,
            "cambios_contexto": self.planificador.cambios_contexto,
            "reloj": reloj,
        }

    # ================================================================== #
    # Bloqueo / desbloqueo / liberación (integración entre módulos)
    # ================================================================== #
    def _bloquear(self, pcb: PCB, motivo: str) -> None:
        self.planificador.retirar(pcb.pid)
        pcb.motivo_bloqueo = motivo
        pcb.cambiar_estado(Estado.BLOQUEADO)

    def _despertar(self, pid: int, motivo: str) -> None:
        pcb = self.procesos[pid]
        pcb.motivo_bloqueo = ""
        self.planificador.admitir(pcb)
        self.registrar("OK", f"P{pid} DESBLOQUEADO ({motivo}); vuelve a la cola de listos.")

    def _liberar_todo(self, pcb: PCB) -> None:
        """Libera memoria, recursos y sección crítica de un proceso que sale del sistema."""
        marcos = self.memoria.liberar(pcb.pid)
        if marcos:
            self.registrar("INFO", f"Memoria de P{pcb.pid} liberada: marcos {marcos}. "
                                   f"RAM libre: {self.memoria.memoria_libre_mb()} MB.")
        for rid, receptor in self.recursos.liberar_todos(pcb.pid):
            self.registrar("INFO", f"P{pcb.pid} libera {rid}.")
            if receptor is not None:
                self.procesos[receptor].recursos.append(rid)
                self._despertar(receptor, f"obtuvo {rid}")
        pcb.recursos.clear()
        despertado = self.semaforo.quitar(pcb.pid)
        if despertado is not None:
            self.registrar("INFO", f"Sección crítica liberada por P{pcb.pid}.")
            self._despertar(despertado, "entra a la sección crítica")

    # ================================================================== #
    # C. Concurrencia: semáforo binario y sección crítica
    # ================================================================== #
    def wait(self, pid: int) -> bool:
        pcb = self.obtener_activo(pid)
        try:
            entro = self.semaforo.wait(pid)
        except ErrorSemaforo as error:
            raise ErrorKernel(str(error)) from error
        if entro:
            self.registrar("OK", f"P{pid} wait(): semáforo 1->0. ENTRA a la sección crítica.")
        else:
            self._bloquear(pcb, f"esperando semáforo (dueño: P{self.semaforo.propietario})")
            self.registrar("ALERTA", f"P{pid} wait(): sección crítica OCUPADA por "
                                     f"P{self.semaforo.propietario}. P{pid} BLOQUEADO en la cola "
                                     f"de espera {list(self.semaforo.cola_espera)}.")
        return entro

    def escribir_variable(self, pid: int, incremento: int = 1) -> int:
        self.obtener_vivo(pid)
        if self.semaforo.propietario != pid:
            raise ErrorKernel(f"P{pid} no está en la sección crítica: debe hacer wait() primero.")
        anterior = self.variable_global
        self.variable_global += incremento
        self.registrar("OK", f"P{pid} modifica la variable global: {anterior} -> {self.variable_global}.")
        return self.variable_global

    def signal(self, pid: int) -> int | None:
        self.obtener_vivo(pid)
        try:
            despertado = self.semaforo.signal(pid)
        except ErrorSemaforo as error:
            raise ErrorKernel(str(error)) from error
        if despertado is None:
            self.registrar("OK", f"P{pid} signal(): sale de la sección crítica. Semáforo 0->1 (libre).")
        else:
            self.registrar("OK", f"P{pid} signal(): sale de la sección crítica y la cede a P{despertado}.")
            self._despertar(despertado, "entra a la sección crítica")
        return despertado

    # ================================================================== #
    # D. Recursos e interbloqueo
    # ================================================================== #
    def solicitar_recurso(self, pid: int, rid: str) -> bool:
        pcb = self.obtener_activo(pid)
        rid = rid.upper()
        try:
            asignado = self.recursos.solicitar(pid, rid)
        except ErrorRecurso as error:
            raise ErrorKernel(str(error)) from error
        if asignado:
            pcb.recursos.append(rid)
            self.registrar("OK", f"P{pid} solicita {rid}: ASIGNADO. P{pid} retiene {pcb.recursos}.")
        else:
            dueno = self.recursos.recursos[rid]["propietario"]
            self._bloquear(pcb, f"esperando {rid} (retenido por P{dueno})")
            self.registrar("ALERTA", f"P{pid} solicita {rid}: OCUPADO por P{dueno}. P{pid} BLOQUEADO.")
            self.verificar_deadlock(automatica=True)
        return asignado

    def liberar_recurso(self, pid: int, rid: str) -> None:
        pcb = self.obtener_activo(pid)
        rid = rid.upper()
        try:
            receptor = self.recursos.liberar(pid, rid)
        except ErrorRecurso as error:
            raise ErrorKernel(str(error)) from error
        pcb.recursos.remove(rid)
        self.registrar("OK", f"P{pid} libera {rid}.")
        if receptor is not None:
            self.procesos[receptor].recursos.append(rid)
            self._despertar(receptor, f"obtuvo {rid}")

    def verificar_deadlock(self, automatica: bool = False) -> list[int]:
        """
        Ejecuta el algoritmo de detección. Se llama automáticamente cada vez que
        un proceso se bloquea por un recurso, y también a petición del usuario.
        """
        ciclo = self.recursos.detectar_deadlock()
        if ciclo:
            cadena = " -> ".join(f"P{p}" for p in ciclo + [ciclo[0]])
            self.registrar("ALERTA", f"¡DEADLOCK DETECTADO! Espera circular: {cadena}. "
                                     "Use 'Abortar proceso' para romper el ciclo.")
        elif not automatica:
            self.registrar("INFO", "Detección de deadlock: no hay ciclos en el grafo de espera.")
        return ciclo

    def forzar_deadlock(self) -> tuple[PCB, PCB]:
        """
        Fuerza la espera circular del enunciado:
            Proceso A retiene R1 y solicita R2;
            Proceso B retiene R2 y solicita R1.
        """
        ocupados = [rid for rid, r in self.recursos.recursos.items() if r["propietario"] is not None]
        if ocupados:
            raise ErrorKernel(f"Los recursos {ocupados} ya están ocupados. Libérelos o aborte "
                              "a sus dueños antes de forzar el deadlock.")
        self.registrar("INFO", "=== Forzando escenario de deadlock (espera circular) ===")
        proceso_a = self.crear_proceso("Proceso_A", 4, 6)
        proceso_b = self.crear_proceso("Proceso_B", 4, 6)
        if proceso_a is None or proceso_b is None:
            if proceso_a is not None:
                self.abortar(proceso_a.pid)
            raise ErrorKernel("No hay memoria para crear los procesos A y B del escenario.")
        self.solicitar_recurso(proceso_a.pid, "R1")
        self.solicitar_recurso(proceso_b.pid, "R2")
        self.solicitar_recurso(proceso_a.pid, "R2")   # A se bloquea
        self.solicitar_recurso(proceso_b.pid, "R1")   # B se bloquea -> ciclo
        return proceso_a, proceso_b

    def abortar(self, pid: int) -> None:
        """Termina forzosamente un proceso y libera todo lo que retiene."""
        pcb = self.obtener_vivo(pid)
        self.planificador.retirar(pid)
        pcb.abortado = True
        pcb.motivo_bloqueo = ""
        pcb.tiempo_finalizacion = self.planificador.reloj
        pcb.cambiar_estado(Estado.TERMINADO)
        self.registrar("ALERTA", f"P{pid} '{pcb.nombre}' ABORTADO por el usuario.")
        self._liberar_todo(pcb)
