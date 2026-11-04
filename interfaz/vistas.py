"""
vistas.py - Funciones que dibujan en consola el estado interno del kernel:
tablas de PCB/TCB, mapa de memoria, cola de listos, diagrama de Gantt,
métricas, semáforo y grafo de espera de recursos.
"""

from nucleo import Estado, Kernel
from nucleo.memoria import TAMANO_MARCO_MB

from .colores import amarillo, azul, cian, gris, magenta, negrita, rojo, sin_color, verde

COLOR_ESTADO = {
    Estado.NUEVO: gris, Estado.LISTO: cian, Estado.EJECUTANDO: verde,
    Estado.BLOQUEADO: amarillo, Estado.TERMINADO: gris,
}
COLOR_NIVEL = {
    "OK": verde, "ERROR": rojo, "ALERTA": amarillo,
    "CPU": cian, "CTX": magenta, "INFO": gris,
}


# ---------------------------------------------------------------------- #
# Utilidades generales
# ---------------------------------------------------------------------- #
def titulo(texto: str) -> None:
    linea = "═" * (len(texto) + 4)
    print("\n" + azul(linea))
    print(azul("║ ") + negrita(texto) + azul(" ║"))
    print(azul(linea))


def tabla(encabezados: list[str], filas: list[list]) -> None:
    """Imprime una tabla alineada; respeta los colores ANSI al medir anchos."""
    filas = [[str(c) for c in fila] for fila in filas]
    anchos = [len(e) for e in encabezados]
    for fila in filas:
        for i, celda in enumerate(fila):
            anchos[i] = max(anchos[i], len(sin_color(celda)))

    def renglon(celdas):
        partes = [c + " " * (anchos[i] - len(sin_color(c))) for i, c in enumerate(celdas)]
        return "│ " + " │ ".join(partes) + " │"

    borde = "─┼─".join("─" * a for a in anchos)
    print("┌─" + "─┬─".join("─" * a for a in anchos) + "─┐")
    print(renglon([negrita(e) for e in encabezados]))
    print("├─" + borde + "─┤")
    if not filas:
        print("│ " + gris("(sin datos)".ljust(sum(anchos) + 3 * (len(anchos) - 1))) + " │")
    for fila in filas:
        print(renglon(fila))
    print("└─" + "─┴─".join("─" * a for a in anchos) + "─┘")


def estado_coloreado(estado: Estado) -> str:
    return COLOR_ESTADO[estado](estado.value)


def linea_bitacora(tiempo: int, nivel: str, mensaje: str) -> str:
    return f"{gris(f'[t={tiempo:>4}]')} {COLOR_NIVEL.get(nivel, str)(f'{nivel:<6}')} {mensaje}"


def barra(usado: int, total: int, ancho: int = 30) -> str:
    llenos = round(ancho * usado / total) if total else 0
    porcentaje = 100 * usado / total if total else 0
    pintura = rojo if porcentaje >= 90 else amarillo if porcentaje >= 70 else verde
    return pintura("█" * llenos) + gris("░" * (ancho - llenos)) + f" {usado}/{total} MB ({porcentaje:.0f}%)"


# ---------------------------------------------------------------------- #
# Procesos
# ---------------------------------------------------------------------- #
def tabla_procesos(kernel: Kernel, incluir_terminados: bool = True) -> None:
    filas = []
    for p in kernel.procesos.values():
        if not incluir_terminados and p.estado == Estado.TERMINADO:
            continue
        estado = estado_coloreado(p.estado) + (rojo(" (abortado)") if p.abortado else "")
        filas.append([p.pid, p.nombre, estado, f"{p.tamano_mb} MB", p.rafaga_total,
                      p.rafaga_restante, len(p.hilos), ",".join(p.recursos) or "-",
                      p.motivo_bloqueo or "-"])
    tabla(["PID", "Nombre", "Estado", "Memoria", "Ráfaga total", "Ráfaga restante",
           "Hilos", "Recursos", "Motivo de bloqueo"], filas)


def tabla_hilos(kernel: Kernel) -> None:
    filas = [[h.tid, f"P{h.pid_padre}", kernel.procesos[h.pid_padre].nombre,
              estado_coloreado(h.estado), h.contador_programa]
             for p in kernel.procesos.values() for h in p.hilos]
    tabla(["TID", "PID padre", "Proceso", "Estado", "Contador de programa"], filas)


def detalle_proceso(kernel: Kernel, pid: int) -> None:
    p = kernel.obtener(pid)
    print(negrita(f"\nPCB del proceso {p.pid}"))
    datos = [
        ("PID", p.pid), ("Nombre", p.nombre), ("Estado", estado_coloreado(p.estado)),
        ("Tamaño en memoria", f"{p.tamano_mb} MB"),
        ("Ráfaga de CPU total", p.rafaga_total), ("Ráfaga de CPU restante", p.rafaga_restante),
        ("Tiempo de llegada", p.tiempo_llegada),
        ("Primera vez en CPU", "-" if p.tiempo_primera_cpu is None else p.tiempo_primera_cpu),
        ("Tiempo de finalización", "-" if p.tiempo_finalizacion is None else p.tiempo_finalizacion),
        ("Cambios de contexto", p.cambios_contexto),
        ("Marcos de memoria", p.marcos or "(liberados)"),
        ("Recursos retenidos", p.recursos or "-"),
        ("Motivo de bloqueo", p.motivo_bloqueo or "-"),
    ]
    for clave, valor in datos:
        print(f"  {clave:<24}: {valor}")
    print(negrita("  Hilos (TCB):"))
    for h in p.hilos:
        print(f"    • {h}")


# ---------------------------------------------------------------------- #
# Memoria
# ---------------------------------------------------------------------- #
def mapa_memoria(kernel: Kernel) -> None:
    mem = kernel.memoria
    print(negrita(f"\nRAM física: {mem.ram_mb} MB = {mem.total_marcos} marcos de {mem.marco_mb} MB "
                  f"(paginación simple)"))
    print("Uso: " + barra(mem.memoria_usada_mb(), mem.ram_mb))
    por_fila = 5
    for inicio in range(0, mem.total_marcos, por_fila):
        celdas = []
        for numero in range(inicio, min(inicio + por_fila, mem.total_marcos)):
            dueno = mem.marcos[numero]
            pagina = mem.tablas_paginas[dueno].index(numero) if dueno is not None else None
            etiqueta = f"P{dueno}.{pagina}" if dueno is not None else "libre"
            pintura = cian if dueno is not None else gris
            celdas.append(f"M{numero:02d}:" + pintura(f"{etiqueta:<7}"))
        direccion = f"{inicio * mem.marco_mb:>3}-{min(inicio + por_fila, mem.total_marcos) * mem.marco_mb - 1:>3} MB"
        print(f"  {gris(direccion)}  " + "  ".join(celdas))


def tabla_paginas(kernel: Kernel, pid: int) -> None:
    p = kernel.obtener(pid)
    marcos = kernel.memoria.tablas_paginas.get(pid, [])
    print(negrita(f"\nTabla de páginas de P{pid} ({p.tamano_mb} MB)"))
    if not marcos:
        print(gris("  El proceso no tiene memoria asignada (terminó o fue abortado)."))
        return
    tabla(["Página", "Marco", "Dirección física"],
          [[i, m, f"{m * TAMANO_MARCO_MB}-{(m + 1) * TAMANO_MARCO_MB - 1} MB"] for i, m in enumerate(marcos)])
    frag = kernel.memoria.fragmentacion_interna_mb(pid, p.tamano_mb)
    print(f"  Fragmentación interna (última página): {frag} MB")


# ---------------------------------------------------------------------- #
# Planificación
# ---------------------------------------------------------------------- #
def cola_listos(kernel: Kernel) -> None:
    cola = kernel.planificador.cola_listos
    if not cola:
        print(gris("Cola de listos vacía."))
        return
    print(negrita("Cola de listos (frente → final):"))
    print("  " + " → ".join(cian(f"[P{p.pid} r={p.rafaga_restante}]") for p in cola))


def gantt(segmentos: list[tuple[int, int, int]], ancho_max: int = 72) -> None:
    """Diagrama de Gantt en texto. Cada segmento es (pid, inicio, fin)."""
    if not segmentos:
        print(gris("Aún no se ha ejecutado ningún proceso."))
        return
    print(negrita("Diagrama de Gantt (cada bloque es un turno de CPU):"))
    barra_txt, regla = "|", "0"
    for pid, ini, fin in segmentos:
        etiqueta = f"P{pid}"
        ancho = max(len(etiqueta) + 2, (fin - ini) * 2)
        bloque = etiqueta.center(ancho) + "|"
        marca = str(fin)
        if len(barra_txt) + len(bloque) > ancho_max:
            print(barra_txt)
            print(regla)
            barra_txt, regla = "|", str(ini)
        barra_txt += bloque
        # El tiempo de fin se alinea justo debajo de la '|' que cierra el bloque.
        regla = regla.ljust(len(barra_txt) - len(marca)) + marca
    print(barra_txt)
    print(regla)


def tabla_metricas(kernel: Kernel) -> None:
    m = kernel.metricas()
    filas = [[p.pid, p.nombre, p.tiempo_llegada, p.rafaga_total, p.tiempo_finalizacion,
              p.tiempo_retorno, p.tiempo_espera, p.tiempo_respuesta, p.cambios_contexto]
             for p in m["terminados"]]
    tabla(["PID", "Nombre", "Llegada", "Ráfaga", "Fin", "Retorno", "Espera", "Respuesta", "Cambios ctx"],
          filas)
    if filas:
        print(f"  Tiempo de espera promedio   : {m['espera_promedio']:.2f}")
        print(f"  Tiempo de retorno promedio  : {m['retorno_promedio']:.2f}")
        print(f"  Tiempo de respuesta promedio: {m['respuesta_promedio']:.2f}")
        print(f"  Throughput                  : {m['throughput']:.3f} procesos/unidad de tiempo")
        print(f"  Cambios de contexto totales : {m['cambios_contexto']}")
        print(gris("  Retorno = Fin - Llegada | Espera = Retorno - Ráfaga | Respuesta = 1ª CPU - Llegada"))


# ---------------------------------------------------------------------- #
# Concurrencia y recursos
# ---------------------------------------------------------------------- #
def estado_semaforo(kernel: Kernel) -> None:
    s = kernel.semaforo
    valor = verde("1 (libre)") if s.valor == 1 else rojo("0 (ocupado)")
    print(negrita("\nSemáforo binario 'mutex'"))
    print(f"  Valor               : {valor}")
    print(f"  En sección crítica  : {'P' + str(s.propietario) if s.propietario else '-'}")
    print(f"  Cola de espera      : {[f'P{p}' for p in s.cola_espera] or '(vacía)'}")
    print(f"  Variable global     : {negrita(kernel.variable_global)}")


def estado_recursos(kernel: Kernel) -> None:
    filas = []
    for rid, r in kernel.recursos.recursos.items():
        dueno = f"P{r['propietario']}" if r["propietario"] else verde("libre")
        filas.append([rid, dueno, ", ".join(f"P{p}" for p in r["cola"]) or "-"])
    tabla(["Recurso", "Retenido por", "Cola de espera"], filas)
    grafo = kernel.recursos.grafo_espera()
    print(negrita("Grafo de espera (Pi → Pj: Pi espera un recurso que tiene Pj):"))
    if not grafo:
        print(gris("  (sin aristas: ningún proceso espera recursos)"))
    for origen, destinos in sorted(grafo.items()):
        for destino in sorted(destinos):
            rid = kernel.recursos.esperando(origen)
            print(f"  P{origen} ──espera {rid}──▶ P{destino}")
    ciclo = kernel.recursos.detectar_deadlock()
    if ciclo:
        print(rojo("  ⚠ CICLO: " + " → ".join(f"P{p}" for p in ciclo + [ciclo[0]]) + "  (DEADLOCK)"))
