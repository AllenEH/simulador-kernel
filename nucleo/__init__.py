"""Paquete 'nucleo': lógica del Simulador de Funciones del Kernel."""

from .kernel import Kernel, ErrorKernel
from .pcb import PCB, TCB, Estado

__all__ = ["Kernel", "ErrorKernel", "PCB", "TCB", "Estado"]
