"""
recursos.py - Administración de recursos exclusivos y manejo de Interbloqueo (Deadlock).

El sistema cuenta con dos recursos de uso exclusivo: R1 y R2 (piense en una
impresora y un escáner). Cada recurso tiene un dueño y una cola de espera.

Estrategia de manejo de deadlock: DETECCIÓN Y RECUPERACIÓN.
  * Detección: se construye el Grafo de Espera (wait-for graph): existe una
    arista Pi -> Pj si Pi espera un recurso que retiene Pj. Si el grafo tiene
    un CICLO, hay deadlock (espera circular). La detección se ejecuta
    automáticamente después de cada solicitud que bloquea a un proceso.
  * Recuperación: el usuario elige una víctima y la aborta. Sus recursos se
    liberan y se entregan al siguiente proceso en espera, rompiendo el ciclo.

Se cumplen las 4 condiciones de Coffman cuando ocurre el deadlock:
exclusión mutua, retención y espera, no apropiación y espera circular.
"""

from collections import deque

RECURSOS = ("R1", "R2")


class ErrorRecurso(Exception):
    """Solicitud o liberación inválida de un recurso."""


class GestorRecursos:
    def __init__(self, nombres: tuple[str, ...] = RECURSOS):
        self.recursos: dict[str, dict] = {
            nombre: {"propietario": None, "cola": deque()} for nombre in nombres
        }

    def _validar(self, rid: str) -> dict:
        rid = rid.upper()
        if rid not in self.recursos:
            raise ErrorRecurso(f"El recurso '{rid}' no existe. Disponibles: {', '.join(self.recursos)}")
        return self.recursos[rid]

    # ------------------------------------------------------------------ #
    def solicitar(self, pid: int, rid: str) -> bool:
        """
        El proceso pide el recurso. Devuelve True si se le asignó, False si
        quedó bloqueado esperando.
        """
        recurso = self._validar(rid)
        if recurso["propietario"] == pid:
            raise ErrorRecurso(f"El proceso {pid} ya retiene {rid.upper()}.")
        if pid in recurso["cola"]:
            raise ErrorRecurso(f"El proceso {pid} ya espera por {rid.upper()}.")
        if recurso["propietario"] is None:
            recurso["propietario"] = pid
            return True
        recurso["cola"].append(pid)
        return False

    def liberar(self, pid: int, rid: str) -> int | None:
        """Libera un recurso. Devuelve el PID que lo recibe, si había alguien esperando."""
        recurso = self._validar(rid)
        if recurso["propietario"] != pid:
            raise ErrorRecurso(f"El proceso {pid} no retiene {rid.upper()}.")
        if recurso["cola"]:
            recurso["propietario"] = recurso["cola"].popleft()
            return recurso["propietario"]
        recurso["propietario"] = None
        return None

    def liberar_todos(self, pid: int) -> list[tuple[str, int | None]]:
        """
        Libera todo lo que retiene el proceso y lo saca de las colas de espera.
        Devuelve [(recurso, pid_que_lo_recibe), ...].
        """
        entregas = []
        for rid, recurso in self.recursos.items():
            if pid in recurso["cola"]:
                recurso["cola"].remove(pid)
            if recurso["propietario"] == pid:
                entregas.append((rid, self.liberar(pid, rid)))
        return entregas

    def retenidos_por(self, pid: int) -> list[str]:
        return [rid for rid, r in self.recursos.items() if r["propietario"] == pid]

    def esperando(self, pid: int) -> str | None:
        for rid, r in self.recursos.items():
            if pid in r["cola"]:
                return rid
        return None

    # ------------------------------------------------------------------ #
    # Detección de deadlock
    # ------------------------------------------------------------------ #
    def grafo_espera(self) -> dict[int, set[int]]:
        """Construye el grafo de espera: pid -> {pids que retienen lo que espera}."""
        grafo: dict[int, set[int]] = {}
        for recurso in self.recursos.values():
            dueno = recurso["propietario"]
            for esperando in recurso["cola"]:
                if dueno is not None:
                    grafo.setdefault(esperando, set()).add(dueno)
        return grafo

    def detectar_deadlock(self) -> list[int]:
        """
        Busca un ciclo en el grafo de espera con búsqueda en profundidad (DFS).
        Devuelve la lista de PIDs que forman el ciclo, o [] si no hay deadlock.
        """
        grafo = self.grafo_espera()
        visitados: set[int] = set()

        def dfs(nodo: int, camino: list[int]) -> list[int]:
            if nodo in camino:                       # Regresamos a un nodo del camino: ciclo
                return camino[camino.index(nodo):]
            if nodo in visitados:
                return []
            visitados.add(nodo)
            for vecino in sorted(grafo.get(nodo, ())):
                ciclo = dfs(vecino, camino + [nodo])
                if ciclo:
                    return ciclo
            return []

        for inicio in sorted(grafo):
            ciclo = dfs(inicio, [])
            if ciclo:
                return ciclo
        return []
