"""
consola.py - Interfaz de línea de comandos (CLI) del simulador.

Organiza las funciones del kernel en menús de texto. Después de cada acción
muestra los eventos nuevos de la bitácora, de modo que el usuario ve en tiempo
real lo que hace el kernel (cambios de estado, cambios de contexto, bloqueos,
alertas de deadlock, errores de memoria...).

Ninguna entrada del usuario puede detener el programa: los errores de
validación se informan y se vuelve al menú.
"""

import random

from nucleo import ErrorKernel, Estado, Kernel
from nucleo.kernel import MAX_HILOS, MAX_NOMBRE, MAX_RAFAGA, MAX_TAMANO_MB
from nucleo.planificador import QUANTUM
from nucleo.sincronizacion import simular_condicion_carrera

from . import escenarios, vistas
from .colores import amarillo, azul, cian, gris, negrita, rojo, verde
from .entrada import Cancelado, confirmar, leer_entero, leer_opcion, leer_texto, pausa
from . import escenarios, vistas, laboratorio


class Consola:
    def __init__(self) -> None:
        self.kernel = Kernel()
        self.visto = 0   # Índice del último evento de bitácora ya mostrado

    # ================================================================== #
    # Utilidades
    # ================================================================== #
    def mostrar_eventos(self) -> None:
        """Imprime los eventos de bitácora que el usuario aún no ha visto."""
        nuevos = self.kernel.bitacora[self.visto:]
        if nuevos:
            print()
            for evento in nuevos:
                print(vistas.linea_bitacora(*evento))
        self.visto = len(self.kernel.bitacora)

    def encabezado(self) -> str:
        k = self.kernel
        vivos = k.procesos_vivos()
        bloqueados = sum(1 for p in vivos if p.estado == Estado.BLOQUEADO)
        return (f"t={k.planificador.reloj} │ RAM {k.memoria.memoria_usada_mb()}/{k.memoria.ram_mb} MB │ "
                f"Listos: {len(k.planificador.cola_listos)} │ Bloqueados: {bloqueados} │ "
                f"Variable global: {k.variable_global}")

    def elegir_proceso(self, mensaje: str = "PID del proceso", filtro=None) -> int:
        """Muestra los procesos candidatos y pide un PID válido."""
        candidatos = [p for p in self.kernel.procesos_vivos() if filtro is None or filtro(p)]
        if not candidatos:
            raise ErrorKernel("No hay procesos disponibles para esta operación.")
        print(gris("Procesos disponibles: " + ", ".join(
            f"P{p.pid}({p.nombre}, {p.estado.value})" for p in candidatos)))
        validos = {p.pid for p in candidatos}
        while True:
            pid = leer_entero(mensaje, 1, 10**9)
            if pid in validos:
                return pid
            print(rojo(f"  ✗ El PID {pid} no está entre los procesos disponibles: {sorted(validos)}"))

    def menu(self, titulo: str, opciones: list[tuple[str, str]]) -> str:
        vistas.titulo(titulo)
        print(gris(self.encabezado()))
        for clave, texto in opciones:
            print(f"  {cian(clave)}. {texto}")
        try:
            return leer_opcion("Seleccione una opción", [c for c, _ in opciones])
        except Cancelado:
            return "0"
        
    def ejecutar_accion(self, accion) -> None:
        """Ejecuta una acción protegiendo al programa de cualquier error."""
        try:
            accion()
        except Cancelado:
            print(gris("  Operación cancelada."))
        except ErrorKernel as error:
            print(rojo(f"  ✗ {error}"))
        except Exception as error:   # Último recurso: el simulador nunca se cae
            print(rojo(f"  ✗ Error inesperado: {type(error).__name__}: {error}"))
        self.mostrar_eventos()
        pausa()

    def submenu(self, titulo: str, opciones: list[tuple[str, str, object]]) -> None:
        acciones = {clave: accion for clave, _, accion in opciones}
        while True:
            opcion = self.menu(titulo, [(c, t) for c, t, _ in opciones] + [("0", "Volver")])
            if opcion == "0":
                return
            self.ejecutar_accion(acciones[opcion])

    # ================================================================== #
    # Bucle principal
    # ================================================================== #
    def iniciar(self) -> None:
        print(azul(BANNER))
        print(gris("Consejo: en cualquier pregunta presione Enter sin escribir nada para cancelar.\n"))
        principales = {
            "1": self.menu_procesos, "2": self.menu_planificador, "3": self.menu_memoria,
            "4": self.menu_concurrencia, "5": self.menu_deadlock, "6": self.menu_casos,
            "7": self.menu_bitacora, "9": self.menu_laboratorio,
        }
        while True:
            try:
                opcion = self.menu("SIMULADOR DE FUNCIONES DEL KERNEL", [
                    ("1", "Gestión de procesos (PCB / TCB)"),
                    ("2", f"Planificación Round Robin (q = {QUANTUM})"),
                    ("3", "Gestión de memoria (100 MB, paginación)"),
                    ("4", "Concurrencia: semáforo y sección crítica"),
                    ("5", "Interbloqueo (Deadlock)"),
                    ("6", "Casos de prueba para el informe"),
                    ("7", "Bitácora de eventos"),
                    ("8", "Reiniciar simulador"),
                    ("9", "Modo Laboratorio (ejemplos manipulables)"),
                    ("0", "Salir"),
                ])
                if opcion == "0":
                    if confirmar("¿Seguro que desea salir?"):
                        break
                elif opcion == "8":
                    if confirmar("Se perderán todos los procesos. ¿Reiniciar?"):
                        self.kernel = Kernel()
                        self.visto = 0
                        print(verde("  ✓ Simulador reiniciado."))
                else:
                    principales[opcion]()
            except Cancelado:
                continue
        print(azul("\nSimulador finalizado. ¡Hasta pronto!"))

    

    # ================================================================== #
    # 1. Procesos
    # ================================================================== #
    def menu_procesos(self) -> None:
        self.submenu("GESTIÓN DE PROCESOS", [
            ("1", "Crear proceso", self.crear_proceso),
            ("2", "Crear procesos aleatorios", self.crear_aleatorios),
            ("3", "Crear hilo (TCB) en un proceso", self.crear_hilo),
            ("4", "Tabla de procesos (PCB)", lambda: vistas.tabla_procesos(self.kernel)),
            ("5", "Tabla de hilos (TCB)", lambda: vistas.tabla_hilos(self.kernel)),
            ("6", "Ver detalle de un proceso", self.detalle),
            ("7", "Abortar proceso", self.abortar),
        ])

    def crear_proceso(self) -> None:
        nombre = leer_texto(f"Nombre del proceso (opcional, máx {MAX_NOMBRE}): ", MAX_NOMBRE)
        tamano = leer_entero("Tamaño en memoria (MB)", 1, MAX_TAMANO_MB)
        rafaga = leer_entero("Ráfaga de CPU (unidades de tiempo)", 1, MAX_RAFAGA)
        hilos = leer_entero("Cantidad de hilos", 1, MAX_HILOS)
        pcb = self.kernel.crear_proceso(nombre, tamano, rafaga, hilos)
        if pcb:
            print(verde(f"  ✓ Proceso P{pcb.pid} creado y en la cola de listos."))
        else:
            print(rojo("  ✗ Proceso rechazado por falta de memoria (ver bitácora)."))

    def crear_aleatorios(self) -> None:
        cantidad = leer_entero("¿Cuántos procesos aleatorios?", 1, 30)
        creados = 0
        for _ in range(cantidad):
            if self.kernel.crear_proceso("", random.randint(1, 30), random.randint(1, 12)):
                creados += 1
        print(verde(f"  ✓ {creados} creados") + (rojo(f", {cantidad - creados} rechazados por memoria")
                                                  if creados < cantidad else ""))

    def crear_hilo(self) -> None:
        pid = self.elegir_proceso()
        self.kernel.crear_hilo(pid)

    def detalle(self) -> None:
        if not self.kernel.procesos:
            raise ErrorKernel("Aún no hay procesos.")
        print(gris("PIDs existentes: " + ", ".join(str(p) for p in self.kernel.procesos)))
        vistas.detalle_proceso(self.kernel, leer_entero("PID", 1, 10**9))

    def abortar(self) -> None:
        pid = self.elegir_proceso("PID del proceso a abortar")
        if confirmar(f"¿Abortar el proceso {pid}?"):
            self.kernel.abortar(pid)

    # ================================================================== #
    # 2. Planificador
    # ================================================================== #
    def menu_planificador(self) -> None:
        self.submenu(f"PLANIFICADOR ROUND ROBIN (q = {QUANTUM})", [
            ("1", "Ejecutar un quantum (paso a paso)", self.paso),
            ("2", "Ejecutar hasta vaciar la cola de listos", self.kernel_ejecutar_todo),
            ("3", "Ver cola de listos", lambda: vistas.cola_listos(self.kernel)),
            ("4", "Diagrama de Gantt", lambda: vistas.gantt(self.kernel.planificador.gantt)),
            ("5", "Métricas de rendimiento", lambda: vistas.tabla_metricas(self.kernel)),
            ("6", "Cálculo teórico de tiempos de espera", self.calculo_teorico),
        ])

    def paso(self) -> None:
        self.kernel.ejecutar_turno()
        self.mostrar_eventos()
        vistas.cola_listos(self.kernel)

    def kernel_ejecutar_todo(self) -> None:
        turnos = self.kernel.ejecutar_hasta_vaciar()
        self.mostrar_eventos()
        print(negrita(f"\n{turnos} turnos ejecutados."))
        vistas.gantt(self.kernel.planificador.gantt)

    def calculo_teorico(self) -> None:
        print(gris("Calcula RR para procesos que llegan en t=0, sin afectar la simulación."))
        cantidad = leer_entero("¿Cuántos procesos?", 1, 10)
        rafagas = [leer_entero(f"  Ráfaga de P{i + 1}", 1, 50) for i in range(cantidad)]
        print()
        escenarios.calculo_teorico_rr(rafagas, QUANTUM)

    # ================================================================== #
    # 3. Memoria
    # ================================================================== #
    def menu_memoria(self) -> None:
        self.submenu("GESTIÓN DE MEMORIA", [
            ("1", "Mapa de memoria (marcos)", lambda: vistas.mapa_memoria(self.kernel)),
            ("2", "Tabla de páginas de un proceso", self.paginas),
            ("3", "Crear proceso (validación de RAM)", self.crear_proceso),
        ])

    def paginas(self) -> None:
        vistas.tabla_paginas(self.kernel, self.elegir_proceso())

    # ================================================================== #
    # 4. Concurrencia
    # ================================================================== #
    def menu_concurrencia(self) -> None:
        self.submenu("CONCURRENCIA: SEMÁFORO BINARIO", [
            ("1", "wait()   - un proceso solicita entrar a la sección crítica", self.op_wait),
            ("2", "Modificar la variable global (dentro de la sección crítica)", self.op_escribir),
            ("3", "signal() - el proceso sale de la sección crítica", self.op_signal),
            ("4", "Estado del semáforo", lambda: vistas.estado_semaforo(self.kernel)),
            ("5", "Simular condición de carrera (sin vs. con semáforo)", self.carrera),
        ])

    def op_wait(self) -> None:
        self.kernel.wait(self.elegir_proceso(filtro=lambda p: p.estado != Estado.BLOQUEADO))
        self.mostrar_eventos()
        vistas.estado_semaforo(self.kernel)

    def op_escribir(self) -> None:
        dueno = self.kernel.semaforo.propietario
        if dueno is None:
            raise ErrorKernel("Nadie está en la sección crítica. Primero un proceso debe hacer wait().")
        incremento = leer_entero(f"Cantidad a sumar a la variable (proceso P{dueno})", -1000, 1000)
        self.kernel.escribir_variable(dueno, incremento)

    def op_signal(self) -> None:
        dueno = self.kernel.semaforo.propietario
        if dueno is None:
            raise ErrorKernel("La sección crítica ya está libre.")
        self.kernel.signal(dueno)
        self.mostrar_eventos()
        vistas.estado_semaforo(self.kernel)

    def carrera(self) -> None:
        hilos = leer_entero("Número de hilos", 2, 5)
        incrementos = leer_entero("Incrementos por hilo", 1, 20)
        for usar in (False, True):
            final, esperado, traza = simular_condicion_carrera(hilos, incrementos, usar)
            print(negrita(f"\n{'CON' if usar else 'SIN'} semáforo:"))
            for linea in traza[:15]:
                print("   " + linea)
            if len(traza) > 15:
                print(gris(f"   ... ({len(traza) - 15} instrucciones más)"))
            pintura = verde if final == esperado else rojo
            print(f"   Valor final: {pintura(final)} (esperado {esperado})")

    # ================================================================== #
    # 5. Deadlock
    # ================================================================== #
    def menu_deadlock(self) -> None:
        self.submenu("INTERBLOQUEO (DEADLOCK)", [
            ("1", "Forzar deadlock (Proceso A ↔ Proceso B)", self.forzar),
            ("2", "Solicitar recurso (R1 / R2)", self.solicitar),
            ("3", "Liberar recurso", self.liberar),
            ("4", "Detectar deadlock", self.detectar),
            ("5", "Estado de recursos y grafo de espera", lambda: vistas.estado_recursos(self.kernel)),
            ("6", "Abortar proceso para romper el ciclo", self.romper),
        ])

    def forzar(self) -> None:
        self.kernel.forzar_deadlock()
        self.mostrar_eventos()
        print()
        vistas.estado_recursos(self.kernel)

    def solicitar(self) -> None:
        pid = self.elegir_proceso(filtro=lambda p: p.estado != Estado.BLOQUEADO)
        rid = leer_opcion("Recurso", ["R1", "R2"])
        self.kernel.solicitar_recurso(pid, rid)

    def liberar(self) -> None:
        pid = self.elegir_proceso(filtro=lambda p: p.recursos and p.estado != Estado.BLOQUEADO)
        rid = leer_opcion("Recurso", ["R1", "R2"])
        self.kernel.liberar_recurso(pid, rid)

    def detectar(self) -> None:
        self.kernel.verificar_deadlock()
        self.mostrar_eventos()
        vistas.estado_recursos(self.kernel)

    def romper(self) -> None:
        ciclo = self.kernel.recursos.detectar_deadlock()
        if ciclo:
            print(amarillo("Procesos en el ciclo: " + ", ".join(f"P{p}" for p in ciclo)))
        else:
            print(gris("No hay deadlock actualmente; se puede abortar cualquier proceso."))
        self.abortar()

    # ================================================================== #
    # 6 y 7. Casos de prueba y bitácora
    # ================================================================== #
    def menu_casos(self) -> None:
        opciones = [(str(i), nombre, caso) for i, (nombre, caso) in enumerate(escenarios.CASOS, 1)]
        opciones.append(("5", "Ejecutar los 4 casos y exportar a archivo .txt", self.exportar_casos))
        self.submenu("CASOS DE PRUEBA (no alteran la simulación actual)", opciones)

    def exportar_casos(self) -> None:
        ruta = escenarios.exportar_todos()
        print(verde(f"  ✓ Casos exportados a: {ruta}"))

    def menu_bitacora(self) -> None:
        self.submenu("BITÁCORA DE EVENTOS", [
            ("1", "Ver bitácora completa", self.ver_bitacora),
            ("2", "Exportar bitácora a archivo .txt", self.exportar_bitacora),
        ])

    def ver_bitacora(self) -> None:
        if not self.kernel.bitacora:
            print(gris("La bitácora está vacía."))
        for evento in self.kernel.bitacora:
            print(vistas.linea_bitacora(*evento))
        self.visto = len(self.kernel.bitacora)

    def exportar_bitacora(self) -> None:
        print(verde(f"  ✓ Bitácora exportada a: {self.kernel.exportar_bitacora()}"))

    def menu_laboratorio(self) -> None:
        self.submenu("MODO LABORATORIO (no altera la simulación actual)", [
            ("1", "Reto: predice el Round Robin", laboratorio.prediccion_rr),
            ("2", "Comparar quantums", laboratorio.comparar_quantums),
            ("3", "Laboratorio de memoria (paginación)", laboratorio.laboratorio_memoria),
        ])

BANNER = r"""
 ╔══════════════════════════════════════════════════════════════╗
 ║        SIMULADOR DE FUNCIONES DEL KERNEL - SO I              ║
 ║  Procesos · Round Robin · Memoria · Semáforo · Deadlock      ║
 ╚══════════════════════════════════════════════════════════════╝"""
