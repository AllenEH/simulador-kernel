"""
memoria.py - Administrador de Memoria con Paginación Simple.

La RAM física simulada mide 100 MB y se divide en marcos (frames) de tamaño fijo.
Cada proceso se divide en páginas del mismo tamaño y cada página se coloca en
cualquier marco libre: los marcos de un proceso NO tienen que ser contiguos.

Ventajas de paginación frente a asignación contigua:
  * Elimina la fragmentación externa (no quedan "huecos" inservibles).
  * Solo existe fragmentación interna en la última página del proceso.

Si no hay suficientes marcos libres, el proceso se rechaza con un error de
desbordamiento de memoria (Out of Memory) y NO se crea.
"""

import math

RAM_TOTAL_MB = 100      # Tamaño de la memoria física simulada
TAMANO_MARCO_MB = 4     # Tamaño de cada marco / página
TOTAL_MARCOS = RAM_TOTAL_MB // TAMANO_MARCO_MB  # 25 marcos


class ErrorMemoriaInsuficiente(Exception):
    """Out of Memory: no hay marcos libres suficientes para el proceso."""


class AdministradorMemoria:
    def __init__(self, ram_mb: int = RAM_TOTAL_MB, marco_mb: int = TAMANO_MARCO_MB):
        self.ram_mb = ram_mb
        self.marco_mb = marco_mb
        self.total_marcos = ram_mb // marco_mb
        # Tabla de marcos: índice = número de marco, valor = PID dueño o None si está libre.
        self.marcos: list[int | None] = [None] * self.total_marcos
        # Tabla de páginas por proceso: PID -> lista de marcos (página i está en marcos[i]).
        self.tablas_paginas: dict[int, list[int]] = {}

    # ------------------------------------------------------------------ #
    def paginas_necesarias(self, tamano_mb: int) -> int:
        return math.ceil(tamano_mb / self.marco_mb)

    def marcos_libres(self) -> int:
        return self.marcos.count(None)

    def memoria_libre_mb(self) -> int:
        return self.marcos_libres() * self.marco_mb

    def memoria_usada_mb(self) -> int:
        return self.ram_mb - self.memoria_libre_mb()

    # ------------------------------------------------------------------ #
    def asignar(self, pid: int, tamano_mb: int) -> list[int]:
        """
        Reserva los marcos que necesita el proceso.
        Lanza ErrorMemoriaInsuficiente si no caben (el proceso se rechaza).
        """
        necesarias = self.paginas_necesarias(tamano_mb)
        libres = self.marcos_libres()
        if necesarias > libres:
            raise ErrorMemoriaInsuficiente(
                f"OUT OF MEMORY: el proceso requiere {tamano_mb} MB "
                f"({necesarias} página(s) de {self.marco_mb} MB) pero solo hay "
                f"{libres} marcos libres ({libres * self.marco_mb} MB disponibles)."
            )
        asignados = []
        for numero, dueno in enumerate(self.marcos):
            if dueno is None:
                self.marcos[numero] = pid
                asignados.append(numero)
                if len(asignados) == necesarias:
                    break
        self.tablas_paginas[pid] = asignados
        return asignados

    def liberar(self, pid: int) -> list[int]:
        """Devuelve a la lista libre todos los marcos del proceso."""
        liberados = self.tablas_paginas.pop(pid, [])
        for numero in liberados:
            self.marcos[numero] = None
        return liberados

    def fragmentacion_interna_mb(self, pid: int, tamano_mb: int) -> int:
        """Espacio desperdiciado dentro de la última página del proceso."""
        return len(self.tablas_paginas.get(pid, [])) * self.marco_mb - tamano_mb
