"""
Pruebas automáticas del simulador (unittest de la biblioteca estándar).

Ejecutar desde la carpeta del proyecto:
    python -m unittest -v
"""

import unittest

from nucleo import ErrorKernel, Estado, Kernel
from nucleo.memoria import AdministradorMemoria, ErrorMemoriaInsuficiente
from nucleo.sincronizacion import SemaforoBinario, simular_condicion_carrera


class PruebasMemoria(unittest.TestCase):
    def test_rechaza_proceso_sin_memoria(self):
        k = Kernel()
        self.assertIsNotNone(k.crear_proceso("a", 60, 3))
        self.assertIsNone(k.crear_proceso("b", 60, 3))          # Out of Memory
        self.assertEqual(len(k.procesos), 1)                     # No se creó
        self.assertTrue(any(n == "ERROR" and "OUT OF MEMORY" in m for _, n, m in k.bitacora))

    def test_proceso_mayor_a_la_ram(self):
        with self.assertRaises(ErrorMemoriaInsuficiente):
            AdministradorMemoria().asignar(1, 101)

    def test_llenado_exacto_y_liberacion(self):
        mem = AdministradorMemoria()
        mem.asignar(1, 100)
        self.assertEqual(mem.memoria_libre_mb(), 0)
        mem.liberar(1)
        self.assertEqual(mem.memoria_libre_mb(), 100)

    def test_memoria_se_libera_al_terminar(self):
        k = Kernel()
        k.crear_proceso("a", 100, 2)
        k.ejecutar_hasta_vaciar()
        self.assertEqual(k.memoria.memoria_libre_mb(), 100)
        self.assertIsNotNone(k.crear_proceso("b", 100, 2))


class PruebasRoundRobin(unittest.TestCase):
    def test_orden_y_tiempos(self):
        k = Kernel()
        for r in (7, 4, 9, 2):
            k.crear_proceso("", 4, r)
        k.ejecutar_hasta_vaciar()
        orden = [pid for pid, _, _ in k.planificador.gantt]
        self.assertEqual(orden, [1, 2, 3, 4, 1, 2, 3, 1, 3])
        fines = {p.pid: p.tiempo_finalizacion for p in k.procesos.values()}
        self.assertEqual(fines, {1: 19, 2: 15, 3: 22, 4: 11})
        self.assertAlmostEqual(k.metricas()["espera_promedio"], 11.25)

    def test_quantum_nunca_excede_3(self):
        k = Kernel()
        k.crear_proceso("", 4, 20)
        k.crear_proceso("", 4, 5)
        k.ejecutar_hasta_vaciar()
        self.assertTrue(all(fin - ini <= 3 for _, ini, fin in k.planificador.gantt))

    def test_validaciones(self):
        k = Kernel()
        for tamano, rafaga in [(0, 3), (-5, 3), (10, 0), (10, -1), (10, 10**6)]:
            with self.assertRaises(ErrorKernel):
                k.crear_proceso("x", tamano, rafaga)


class PruebasSemaforo(unittest.TestCase):
    def test_condicion_de_carrera(self):
        final, esperado, _ = simular_condicion_carrera(3, 10, usar_semaforo=False)
        self.assertLess(final, esperado)
        final, esperado, _ = simular_condicion_carrera(3, 10, usar_semaforo=True)
        self.assertEqual(final, esperado)

    def test_cola_de_espera_fifo(self):
        s = SemaforoBinario()
        self.assertTrue(s.wait(1))
        self.assertFalse(s.wait(2))
        self.assertFalse(s.wait(3))
        self.assertEqual(s.signal(1), 2)
        self.assertEqual(s.signal(2), 3)
        self.assertIsNone(s.signal(3))
        self.assertEqual(s.valor, 1)

    def test_bloqueado_sale_de_cola_de_listos(self):
        k = Kernel()
        k.crear_proceso("", 4, 5)
        k.crear_proceso("", 4, 5)
        k.wait(1)
        k.wait(2)
        self.assertEqual(k.procesos[2].estado, Estado.BLOQUEADO)
        self.assertNotIn(k.procesos[2], k.planificador.cola_listos)
        k.signal(1)
        self.assertEqual(k.procesos[2].estado, Estado.LISTO)
        self.assertEqual(k.semaforo.propietario, 2)

    def test_signal_sin_ser_dueno(self):
        k = Kernel()
        k.crear_proceso("", 4, 5)
        with self.assertRaises(ErrorKernel):
            k.signal(1)


class PruebasDeadlock(unittest.TestCase):
    def test_deteccion_y_resolucion(self):
        k = Kernel()
        a, b = k.forzar_deadlock()
        self.assertEqual(sorted(k.recursos.detectar_deadlock()), sorted([a.pid, b.pid]))
        k.abortar(a.pid)
        self.assertEqual(k.recursos.detectar_deadlock(), [])
        self.assertEqual(b.estado, Estado.LISTO)
        self.assertEqual(sorted(b.recursos), ["R1", "R2"])
        k.ejecutar_hasta_vaciar()
        self.assertEqual(b.estado, Estado.TERMINADO)
        self.assertIsNone(k.recursos.recursos["R1"]["propietario"])

    def test_no_permite_forzar_con_recursos_ocupados(self):
        k = Kernel()
        k.crear_proceso("", 4, 5)
        k.solicitar_recurso(1, "R1")
        with self.assertRaises(ErrorKernel):
            k.forzar_deadlock()

    def test_proceso_bloqueado_no_puede_solicitar(self):
        k = Kernel()
        k.forzar_deadlock()
        with self.assertRaises(ErrorKernel):
            k.solicitar_recurso(1, "R1")


if __name__ == "__main__":
    unittest.main()
