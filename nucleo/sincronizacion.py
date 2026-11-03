"""
sincronizacion.py - Exclusión mutua mediante un Semáforo Binario.

Sección crítica: región de código que accede a la "Variable Global Compartida".
Solo un proceso puede estar dentro a la vez.

Semáforo binario (valor 0 ó 1):
  wait()   -> Si el valor es 1, lo pone en 0 y el proceso entra a la sección crítica.
              Si es 0 (ocupado), el proceso se BLOQUEA y se encola en la cola de
              espera del semáforo (no consume CPU mientras espera: no hay espera activa).
  signal() -> Si hay procesos en espera, despierta al primero (FIFO) y le cede la
              sección crítica directamente. Si no hay nadie, el valor vuelve a 1.

Además se incluye una simulación de CONDICIÓN DE CARRERA: varios hilos incrementan
la variable compartida con la secuencia LEER -> CALCULAR -> ESCRIBIR. Sin semáforo,
el intercalado hace que se pierdan actualizaciones; con semáforo el resultado
siempre es el correcto.
"""

from collections import deque


class ErrorSemaforo(Exception):
    """Uso inválido del semáforo (p. ej. signal de un proceso que no es dueño)."""


class SemaforoBinario:
    def __init__(self, nombre: str = "mutex"):
        self.nombre = nombre
        self.valor = 1                       # 1 = libre, 0 = ocupado
        self.propietario: int | None = None  # PID dentro de la sección crítica
        self.cola_espera: deque[int] = deque()

    def wait(self, pid: int) -> bool:
        """
        Operación P / wait(). Devuelve True si el proceso entró a la sección
        crítica, False si quedó bloqueado en la cola de espera.
        """
        if self.propietario == pid:
            raise ErrorSemaforo(f"El proceso {pid} ya está dentro de la sección crítica.")
        if pid in self.cola_espera:
            raise ErrorSemaforo(f"El proceso {pid} ya está en la cola de espera.")
        if self.valor == 1:
            self.valor = 0
            self.propietario = pid
            return True
        self.cola_espera.append(pid)
        return False

    def signal(self, pid: int) -> int | None:
        """
        Operación V / signal(). Devuelve el PID del proceso que se despertó
        (y que ahora es dueño de la sección crítica), o None si no había nadie.
        """
        if self.propietario != pid:
            raise ErrorSemaforo(
                f"El proceso {pid} no puede hacer signal(): no está en la sección crítica.")
        if self.cola_espera:
            siguiente = self.cola_espera.popleft()
            self.propietario = siguiente       # El valor sigue en 0: se cede directo
            return siguiente
        self.valor = 1
        self.propietario = None
        return None

    def quitar(self, pid: int) -> int | None:
        """
        Elimina a un proceso del semáforo (cuando el proceso se aborta).
        Si era el dueño, se libera la sección crítica como si hiciera signal().
        """
        if pid in self.cola_espera:
            self.cola_espera.remove(pid)
            return None
        if self.propietario == pid:
            return self.signal(pid)
        return None


# ---------------------------------------------------------------------- #
# Simulación de condición de carrera
# ---------------------------------------------------------------------- #
def simular_condicion_carrera(num_hilos: int, incrementos: int,
                              usar_semaforo: bool) -> tuple[int, int, list[str]]:
    """
    Simula 'num_hilos' hilos que hacen 'incrementos' veces: variable = variable + 1.
    Cada incremento son 3 instrucciones de máquina (LEER, CALCULAR, ESCRIBIR) y
    el planificador cambia de hilo después de CADA instrucción (peor caso de
    intercalado). Devuelve (valor_final, valor_esperado, traza).
    """
    variable_global = 0
    semaforo = SemaforoBinario("mutex_carrera")
    traza: list[str] = []

    # Estado de cada hilo: cuántos incrementos le faltan, registro local y fase.
    hilos = {tid: {"faltan": incrementos, "registro": 0,
                   "fase": "WAIT" if usar_semaforo else "LEER", "bloqueado": False}
             for tid in range(1, num_hilos + 1)}

    while any(h["faltan"] > 0 for h in hilos.values()):
        for tid, h in hilos.items():
            if h["faltan"] == 0 or h["bloqueado"]:
                continue
            fase = h["fase"]
            if fase == "WAIT":
                if semaforo.wait(tid):
                    traza.append(f"H{tid}: wait() -> entra a la sección crítica")
                    h["fase"] = "LEER"
                else:
                    traza.append(f"H{tid}: wait() -> OCUPADO, se bloquea en cola de espera")
                    h["bloqueado"] = True
            elif fase == "LEER":
                h["registro"] = variable_global
                traza.append(f"H{tid}: LEER     registro = variable ({variable_global})")
                h["fase"] = "CALCULAR"
            elif fase == "CALCULAR":
                h["registro"] += 1
                traza.append(f"H{tid}: CALCULAR registro = {h['registro']}")
                h["fase"] = "ESCRIBIR"
            elif fase == "ESCRIBIR":
                variable_global = h["registro"]
                traza.append(f"H{tid}: ESCRIBIR variable = {variable_global}")
                if usar_semaforo:
                    h["fase"] = "SIGNAL"   # El incremento se cuenta al salir
                else:
                    h["faltan"] -= 1
                    h["fase"] = "LEER"
            elif fase == "SIGNAL":
                despertado = semaforo.signal(tid)
                if despertado is not None:
                    hilos[despertado]["bloqueado"] = False
                    hilos[despertado]["fase"] = "LEER"
                    traza.append(f"H{tid}: signal() -> despierta a H{despertado}")
                else:
                    traza.append(f"H{tid}: signal() -> sección crítica libre")
                h["faltan"] -= 1
                h["fase"] = "WAIT"

    return variable_global, num_hilos * incrementos, traza
