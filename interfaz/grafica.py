"""
grafica.py - Interfaz gráfica (Tkinter) del simulador de funciones del kernel.

Usa EXACTAMENTE el mismo Kernel que la consola: no duplica lógica. Cada botón
llama a un método del kernel y después se redibuja todo lo que el usuario ve.
Tkinter viene incluido con Python, no requiere instalar nada.

Pestañas:
  Procesos · Round Robin · Memoria · Semáforo · Deadlock · Bitácora
"""

import math
import random
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from nucleo import ErrorKernel, Estado, Kernel
from nucleo.kernel import MAX_HILOS, MAX_RAFAGA, MAX_TAMANO_MB
from nucleo.planificador import QUANTUM
from nucleo.sincronizacion import simular_condicion_carrera

# Un color por PID (se repite si hay más de 10 procesos)
PALETA = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2",
          "#B279A2", "#C9A227", "#9D755D", "#D67195", "#7F7F7F"]
COLOR_ESTADO = {
    Estado.NUEVO: "#888888", Estado.LISTO: "#1F77B4", Estado.EJECUTANDO: "#2E8B57",
    Estado.BLOQUEADO: "#C77700", Estado.TERMINADO: "#888888",
}
COLOR_NIVEL = {"OK": "#2E8B57", "ERROR": "#C0392B", "ALERTA": "#C77700",
               "CPU": "#1F77B4", "CTX": "#8E44AD", "INFO": "#777777"}


def color_pid(pid: int) -> str:
    return PALETA[(pid - 1) % len(PALETA)]


def entero(texto: str, nombre: str, minimo: int, maximo: int) -> int:
    """Convierte el texto de un campo a entero validando el rango."""
    t = (texto or "").strip()
    try:
        valor = int(t)
    except ValueError:
        raise ErrorKernel(f"{nombre}: debe ser un número entero (escribió '{t}').") from None
    if not minimo <= valor <= maximo:
        raise ErrorKernel(f"{nombre}: debe estar entre {minimo} y {maximo}.")
    return valor


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Simulador de Funciones del Kernel - Sistemas Operativos I")
        self.geometry("1180x740")
        self.minsize(1000, 640)
        self.kernel = Kernel()
        self.visto = 0          # eventos de bitácora ya volcados en la pestaña
        self.auto = False       # reproducción automática del planificador
        self._construir()
        self.refrescar()

    # ================================================================== #
    # Construcción de la ventana
    # ================================================================== #
    def _construir(self) -> None:
        barra = tk.Frame(self, bg="#1F2A44")
        barra.pack(fill="x")
        self.lbl_estado = tk.Label(barra, bg="#1F2A44", fg="white", anchor="w",
                                   font=("Segoe UI", 10, "bold"), padx=10, pady=8)
        self.lbl_estado.pack(side="left", fill="x", expand=True)
        ttk.Button(barra, text="Reiniciar simulador", command=self.reiniciar).pack(side="right", padx=8, pady=4)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        self._tab_procesos()
        self._tab_planificador()
        self._tab_memoria()
        self._tab_semaforo()
        self._tab_deadlock()
        self._tab_bitacora()

        self.lbl_ultimo = tk.Label(self, anchor="w", padx=10, pady=4, font=("Consolas", 9))
        self.lbl_ultimo.pack(fill="x")

    # ---------------------------------------------------------------- #
    def _tab_procesos(self) -> None:
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Procesos")
        form = ttk.LabelFrame(f, text="Nuevo proceso", padding=8)
        form.pack(fill="x")
        self.v_nombre = tk.StringVar()
        self.v_tam = tk.StringVar(value="20")
        self.v_raf = tk.StringVar(value="6")
        self.v_hilos = tk.StringVar(value="1")
        campos = [("Nombre (opcional)", self.v_nombre, 16), (f"Tamaño MB (1-{MAX_TAMANO_MB})", self.v_tam, 8),
                  (f"Ráfaga (1-{MAX_RAFAGA})", self.v_raf, 6), (f"Hilos (1-{MAX_HILOS})", self.v_hilos, 4)]
        for i, (texto, var, ancho) in enumerate(campos):
            ttk.Label(form, text=texto).grid(row=0, column=2 * i, padx=(0, 4), sticky="e")
            ttk.Entry(form, textvariable=var, width=ancho).grid(row=0, column=2 * i + 1, padx=(0, 12))
        ttk.Button(form, text="Crear proceso",
                   command=lambda: self.ejecutar(self.crear_proceso)).grid(row=0, column=8, padx=4)
        ttk.Button(form, text="Crear 5 aleatorios",
                   command=lambda: self.ejecutar(self.crear_aleatorios)).grid(row=0, column=9, padx=4)

        acc = ttk.Frame(f)
        acc.pack(fill="x", pady=6)
        ttk.Button(acc, text="Crear hilo en el proceso seleccionado",
                   command=lambda: self.ejecutar(self.crear_hilo)).pack(side="left")
        ttk.Button(acc, text="Abortar proceso seleccionado",
                   command=lambda: self.ejecutar(self.abortar_seleccionado)).pack(side="left", padx=8)

        cols = ("pid", "nombre", "estado", "mem", "raf", "rest", "hilos", "rec", "motivo")
        titulos = ("PID", "Nombre", "Estado", "Memoria", "Ráfaga total", "Ráfaga restante",
                   "Hilos", "Recursos", "Motivo de bloqueo")
        anchos = (50, 120, 110, 80, 90, 110, 50, 80, 330)
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=14, selectmode="browse")
        for c, t, a in zip(cols, titulos, anchos):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=a, anchor="w" if c in ("nombre", "motivo") else "center")
        for estado, color in COLOR_ESTADO.items():
            self.tree.tag_configure(estado.name, foreground=color)
        self.tree.pack(fill="both", expand=True)

    # ---------------------------------------------------------------- #
    def _tab_planificador(self) -> None:
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Round Robin")
        barra = ttk.Frame(f)
        barra.pack(fill="x")
        ttk.Label(barra, text=f"Quantum fijo q = {QUANTUM}",
                  font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 16))
        ttk.Button(barra, text="Ejecutar un quantum",
                   command=lambda: self.ejecutar(self.kernel.ejecutar_turno)).pack(side="left")
        ttk.Button(barra, text="Ejecutar hasta vaciar",
                   command=lambda: self.ejecutar(self.kernel.ejecutar_hasta_vaciar)).pack(side="left", padx=8)
        self.btn_auto = ttk.Button(barra, text="▶ Reproducir", command=self.alternar_auto)
        self.btn_auto.pack(side="left")
        ttk.Label(barra, text="  Pausa entre turnos (ms):").pack(side="left")
        self.velocidad = tk.IntVar(value=700)
        ttk.Scale(barra, from_=100, to=1500, variable=self.velocidad, length=140).pack(side="left")

        ttk.Label(f, text="Cola de listos (frente → final):",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 2))
        self.canvas_cola = tk.Canvas(f, height=50, bg="white", highlightthickness=1,
                                     highlightbackground="#CCCCCC")
        self.canvas_cola.pack(fill="x")

        ttk.Label(f, text="Diagrama de Gantt (cada bloque es un turno de CPU):",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 2))
        marco = ttk.Frame(f)
        marco.pack(fill="x")
        self.canvas_gantt = tk.Canvas(marco, height=95, bg="white", highlightthickness=1,
                                      highlightbackground="#CCCCCC")
        scroll = ttk.Scrollbar(marco, orient="horizontal", command=self.canvas_gantt.xview)
        self.canvas_gantt.configure(xscrollcommand=scroll.set)
        self.canvas_gantt.pack(fill="x")
        scroll.pack(fill="x")

        ttk.Label(f, text="Métricas de procesos terminados:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 2))
        cols = ("pid", "nombre", "llegada", "rafaga", "fin", "retorno", "espera", "resp", "ctx")
        titulos = ("PID", "Nombre", "Llegada", "Ráfaga", "Fin", "Retorno", "Espera", "Respuesta", "Cambios ctx")
        self.tree_met = ttk.Treeview(f, columns=cols, show="headings", height=6)
        for c, t in zip(cols, titulos):
            self.tree_met.heading(c, text=t)
            self.tree_met.column(c, width=90, anchor="center")
        self.tree_met.pack(fill="both", expand=True)
        self.lbl_met = ttk.Label(f, text="", justify="left")
        self.lbl_met.pack(anchor="w", pady=4)

    # ---------------------------------------------------------------- #
    def _tab_memoria(self) -> None:
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Memoria")
        izq = ttk.Frame(f)
        izq.pack(side="left", fill="y")
        self.lbl_ram = ttk.Label(izq, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_ram.pack(anchor="w")
        self.barra_ram = ttk.Progressbar(izq, length=560, mode="determinate")
        self.barra_ram.pack(anchor="w", pady=(2, 8))
        self.canvas_mem = tk.Canvas(izq, width=610, height=360, bg="white",
                                    highlightthickness=1, highlightbackground="#CCCCCC")
        self.canvas_mem.pack(anchor="w")
        ttk.Label(izq, text="Cada marco muestra P<proceso>.<página>: las páginas de un proceso "
                            "pueden quedar en marcos NO contiguos.",
                  foreground="#666666").pack(anchor="w", pady=4)

        der = ttk.Frame(f)
        der.pack(side="left", fill="both", expand=True, padx=(12, 0))
        prueba = ttk.LabelFrame(der, text="Probar la validación de RAM", padding=8)
        prueba.pack(fill="x")
        self.v_mem_tam = tk.StringVar(value="30")
        ttk.Label(prueba, text="Tamaño del proceso (MB):").grid(row=0, column=0, sticky="e")
        ttk.Entry(prueba, textvariable=self.v_mem_tam, width=8).grid(row=0, column=1, padx=6)
        ttk.Button(prueba, text="Crear proceso",
                   command=lambda: self.ejecutar(self.crear_rapido)).grid(row=0, column=2)
        ttk.Button(prueba, text="Abortar seleccionado",
                   command=lambda: self.ejecutar(self.abortar_seleccionado)).grid(row=1, column=0,
                                                                                  columnspan=3, pady=(6, 0))
        ttk.Label(der, text="Tabla de páginas (todos los procesos activos):",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 2))
        cols = ("pid", "pag", "marco", "dir")
        self.tree_pag = ttk.Treeview(der, columns=cols, show="headings", height=14)
        for c, t, a in zip(cols, ("PID", "Página", "Marco", "Dirección física"), (50, 60, 60, 140)):
            self.tree_pag.heading(c, text=t)
            self.tree_pag.column(c, width=a, anchor="center")
        self.tree_pag.pack(fill="both", expand=True)

    # ---------------------------------------------------------------- #
    def _tab_semaforo(self) -> None:
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Semáforo")
        ctrl = ttk.LabelFrame(f, text="Sección crítica (semáforo binario)", padding=8)
        ctrl.pack(fill="x")
        ttk.Label(ctrl, text="Proceso:").grid(row=0, column=0)
        self.cb_sem = ttk.Combobox(ctrl, state="readonly", width=28)
        self.cb_sem.grid(row=0, column=1, padx=6)
        ttk.Button(ctrl, text="wait()  → entrar",
                   command=lambda: self.ejecutar(self.sem_wait)).grid(row=0, column=2, padx=4)
        self.v_inc = tk.StringVar(value="1")
        ttk.Label(ctrl, text="Sumar a la variable:").grid(row=0, column=3, padx=(12, 2))
        ttk.Entry(ctrl, textvariable=self.v_inc, width=6).grid(row=0, column=4)
        ttk.Button(ctrl, text="Modificar variable global",
                   command=lambda: self.ejecutar(self.sem_escribir)).grid(row=0, column=5, padx=4)
        ttk.Button(ctrl, text="signal()  → salir",
                   command=lambda: self.ejecutar(self.sem_signal)).grid(row=0, column=6, padx=4)

        est = ttk.LabelFrame(f, text="Estado actual", padding=8)
        est.pack(fill="x", pady=8)
        self.lbl_sem = tk.Label(est, justify="left", anchor="w", font=("Consolas", 11))
        self.lbl_sem.pack(fill="x")

        carrera = ttk.LabelFrame(f, text="Condición de carrera: sin vs. con semáforo", padding=8)
        carrera.pack(fill="both", expand=True)
        fila = ttk.Frame(carrera)
        fila.pack(fill="x")
        self.v_hilos_c = tk.StringVar(value="2")
        self.v_inc_c = tk.StringVar(value="3")
        ttk.Label(fila, text="Hilos (2-5):").pack(side="left")
        ttk.Entry(fila, textvariable=self.v_hilos_c, width=4).pack(side="left", padx=4)
        ttk.Label(fila, text="Incrementos por hilo (1-20):").pack(side="left", padx=(8, 0))
        ttk.Entry(fila, textvariable=self.v_inc_c, width=4).pack(side="left", padx=4)
        ttk.Button(fila, text="Simular",
                   command=lambda: self.ejecutar(self.carrera)).pack(side="left", padx=8)
        self.txt_carrera = ScrolledText(carrera, height=12, font=("Consolas", 10))
        self.txt_carrera.pack(fill="both", expand=True, pady=(6, 0))
        self.txt_carrera.tag_configure("ok", foreground="#2E8B57", font=("Consolas", 10, "bold"))
        self.txt_carrera.tag_configure("mal", foreground="#C0392B", font=("Consolas", 10, "bold"))

    # ---------------------------------------------------------------- #
    def _tab_deadlock(self) -> None:
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Deadlock")
        ctrl = ttk.LabelFrame(f, text="Recursos exclusivos R1 y R2", padding=8)
        ctrl.pack(fill="x")
        ttk.Button(ctrl, text="Forzar deadlock (A ↔ B)",
                   command=lambda: self.ejecutar(self.kernel.forzar_deadlock)).grid(row=0, column=0, padx=4)
        ttk.Button(ctrl, text="Detectar deadlock",
                   command=lambda: self.ejecutar(self.kernel.verificar_deadlock)).grid(row=0, column=1, padx=4)
        ttk.Label(ctrl, text="Proceso:").grid(row=0, column=2, padx=(16, 2))
        self.cb_dl = ttk.Combobox(ctrl, state="readonly", width=28)
        self.cb_dl.grid(row=0, column=3)
        self.cb_rid = ttk.Combobox(ctrl, state="readonly", width=4, values=["R1", "R2"])
        self.cb_rid.set("R1")
        self.cb_rid.grid(row=0, column=4, padx=4)
        ttk.Button(ctrl, text="Solicitar",
                   command=lambda: self.ejecutar(self.dl_solicitar)).grid(row=0, column=5, padx=2)
        ttk.Button(ctrl, text="Liberar",
                   command=lambda: self.ejecutar(self.dl_liberar)).grid(row=0, column=6, padx=2)
        ttk.Button(ctrl, text="Abortar proceso (romper el ciclo)",
                   command=lambda: self.ejecutar(self.dl_abortar)).grid(row=1, column=0, columnspan=4,
                                                                         pady=(8, 0), sticky="w", padx=4)

        self.lbl_dl = tk.Label(f, anchor="w", font=("Segoe UI", 12, "bold"), pady=6)
        self.lbl_dl.pack(fill="x")
        cuerpo = ttk.Frame(f)
        cuerpo.pack(fill="both", expand=True)
        cols = ("rid", "dueno", "cola")
        self.tree_rec = ttk.Treeview(cuerpo, columns=cols, show="headings", height=4)
        for c, t, a in zip(cols, ("Recurso", "Retenido por", "Cola de espera"), (80, 110, 140)):
            self.tree_rec.heading(c, text=t)
            self.tree_rec.column(c, width=a, anchor="center")
        self.tree_rec.pack(side="left", anchor="n")
        graf = ttk.Frame(cuerpo)
        graf.pack(side="left", fill="both", expand=True, padx=(12, 0))
        ttk.Label(graf, text="Grafo de espera (Pi → Pj: Pi espera un recurso que tiene Pj):",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.canvas_grafo = tk.Canvas(graf, height=320, bg="white", highlightthickness=1,
                                      highlightbackground="#CCCCCC")
        self.canvas_grafo.pack(fill="both", expand=True)

    # ---------------------------------------------------------------- #
    def _tab_bitacora(self) -> None:
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Bitácora")
        barra = ttk.Frame(f)
        barra.pack(fill="x", pady=(0, 6))
        ttk.Button(barra, text="Exportar bitácora a .txt",
                   command=lambda: self.ejecutar(self.exportar_bitacora)).pack(side="left")
        self.txt_bit = ScrolledText(f, font=("Consolas", 10), state="disabled")
        self.txt_bit.pack(fill="both", expand=True)
        for nivel, color in COLOR_NIVEL.items():
            self.txt_bit.tag_configure(nivel, foreground=color)

    # ================================================================== #
    # Utilidades
    # ================================================================== #
    def ejecutar(self, accion) -> bool:
        """Ejecuta una acción protegiendo la ventana de cualquier error."""
        ok = True
        try:
            accion()
        except ErrorKernel as error:
            ok = False
            messagebox.showerror("Operación no válida", str(error))
        except Exception as error:   # último recurso: la ventana nunca se cae
            ok = False
            messagebox.showerror("Error inesperado", f"{type(error).__name__}: {error}")
        self.refrescar()
        return ok

    def pid_de(self, combo: ttk.Combobox) -> int:
        texto = combo.get().strip()
        if not texto:
            raise ErrorKernel("Seleccione un proceso de la lista.")
        return int(texto.split(" ")[0])

    def pid_seleccionado(self) -> int:
        seleccion = self.tree.selection()
        if not seleccion:
            raise ErrorKernel("Seleccione un proceso en la tabla de la pestaña 'Procesos'.")
        return int(seleccion[0])

    def reiniciar(self) -> None:
        if messagebox.askyesno("Reiniciar", "Se perderán todos los procesos. ¿Reiniciar el simulador?"):
            self.auto = False
            self.btn_auto.config(text="▶ Reproducir")
            self.kernel = Kernel()
            self.visto = 0
            self.txt_bit.config(state="normal")
            self.txt_bit.delete("1.0", "end")
            self.txt_bit.config(state="disabled")
            self.txt_carrera.delete("1.0", "end")
            self.refrescar()

    # ================================================================== #
    # Acciones (cada una llama al kernel; los errores los atrapa ejecutar)
    # ================================================================== #
    def crear_proceso(self) -> None:
        tam = entero(self.v_tam.get(), "Tamaño", 1, MAX_TAMANO_MB)
        raf = entero(self.v_raf.get(), "Ráfaga", 1, MAX_RAFAGA)
        hilos = entero(self.v_hilos.get(), "Hilos", 1, MAX_HILOS)
        self._crear(self.v_nombre.get(), tam, raf, hilos)

    def crear_rapido(self) -> None:
        tam = entero(self.v_mem_tam.get(), "Tamaño", 1, MAX_TAMANO_MB)
        self._crear("", tam, 5, 1)

    def _crear(self, nombre: str, tam: int, raf: int, hilos: int) -> None:
        if self.kernel.crear_proceso(nombre, tam, raf, hilos) is None:
            messagebox.showwarning(
                "Out of Memory",
                f"Proceso rechazado: no hay marcos libres suficientes para {tam} MB.\n"
                "Revise la pestaña Bitácora para ver el detalle.")

    def crear_aleatorios(self) -> None:
        rechazados = 0
        for _ in range(5):
            if self.kernel.crear_proceso("", random.randint(1, 30), random.randint(1, 12)) is None:
                rechazados += 1
        if rechazados:
            messagebox.showwarning("Out of Memory", f"{rechazados} proceso(s) rechazado(s) por falta de RAM.")

    def crear_hilo(self) -> None:
        self.kernel.crear_hilo(self.pid_seleccionado())

    def abortar_seleccionado(self) -> None:
        pid = self.pid_seleccionado()
        if messagebox.askyesno("Abortar proceso", f"¿Abortar forzosamente el proceso {pid}?"):
            self.kernel.abortar(pid)

    def sem_wait(self) -> None:
        self.kernel.wait(self.pid_de(self.cb_sem))

    def sem_escribir(self) -> None:
        dueno = self.kernel.semaforo.propietario
        if dueno is None:
            raise ErrorKernel("Nadie está en la sección crítica. Primero un proceso debe hacer wait().")
        self.kernel.escribir_variable(dueno, entero(self.v_inc.get(), "Incremento", -1000, 1000))

    def sem_signal(self) -> None:
        dueno = self.kernel.semaforo.propietario
        if dueno is None:
            raise ErrorKernel("La sección crítica ya está libre.")
        self.kernel.signal(dueno)

    def carrera(self) -> None:
        hilos = entero(self.v_hilos_c.get(), "Hilos", 2, 5)
        incrementos = entero(self.v_inc_c.get(), "Incrementos", 1, 20)
        txt = self.txt_carrera
        txt.delete("1.0", "end")
        for usar in (False, True):
            final, esperado, traza = simular_condicion_carrera(hilos, incrementos, usar)
            txt.insert("end", f"{'CON' if usar else 'SIN'} semáforo:\n")
            for linea in traza[:15]:
                txt.insert("end", "   " + linea + "\n")
            if len(traza) > 15:
                txt.insert("end", f"   ... ({len(traza) - 15} instrucciones más)\n")
            txt.insert("end", f"   Valor final: {final} (esperado {esperado})\n\n",
                       "ok" if final == esperado else "mal")

    def dl_solicitar(self) -> None:
        self.kernel.solicitar_recurso(self.pid_de(self.cb_dl), self.cb_rid.get())

    def dl_liberar(self) -> None:
        self.kernel.liberar_recurso(self.pid_de(self.cb_dl), self.cb_rid.get())

    def dl_abortar(self) -> None:
        pid = self.pid_de(self.cb_dl)
        if messagebox.askyesno("Abortar proceso", f"¿Abortar forzosamente el proceso {pid} "
                                                  "y liberar sus recursos?"):
            self.kernel.abortar(pid)

    def exportar_bitacora(self) -> None:
        ruta = self.kernel.exportar_bitacora()
        messagebox.showinfo("Bitácora exportada", f"Archivo guardado en:\n{ruta}")

    # --- reproducción automática del planificador ---------------------- #
    def alternar_auto(self) -> None:
        self.auto = not self.auto
        self.btn_auto.config(text="⏸ Pausar" if self.auto else "▶ Reproducir")
        if self.auto:
            self._tick()

    def _tick(self) -> None:
        if not self.auto:
            return
        if not self.kernel.planificador.hay_trabajo():
            self.auto = False
            self.btn_auto.config(text="▶ Reproducir")
            self.refrescar()
            return
        if not self.ejecutar(self.kernel.ejecutar_turno):
            self.auto = False
            self.btn_auto.config(text="▶ Reproducir")
            return
        self.after(int(self.velocidad.get()), self._tick)

    # ================================================================== #
    # Redibujado
    # ================================================================== #
    def refrescar(self) -> None:
        k = self.kernel
        vivos = k.procesos_vivos()
        bloqueados = sum(1 for p in vivos if p.estado == Estado.BLOQUEADO)
        self.lbl_estado.config(
            text=f"t = {k.planificador.reloj}   │   RAM {k.memoria.memoria_usada_mb()}/{k.memoria.ram_mb} MB   │   "
                 f"Listos: {len(k.planificador.cola_listos)}   │   Bloqueados: {bloqueados}   │   "
                 f"Variable global: {k.variable_global}")
        self._ref_procesos()
        self._ref_planificador()
        self._ref_memoria()
        self._ref_semaforo()
        self._ref_deadlock()
        self._ref_bitacora()
        for combo in (self.cb_sem, self.cb_dl):
            self._ref_combo(combo)

    def _ref_combo(self, combo: ttk.Combobox) -> None:
        valores = [f"{p.pid} - {p.nombre} ({p.estado.value})" for p in self.kernel.procesos_vivos()]
        actual = combo.get().split(" ")[0] if combo.get() else ""
        combo["values"] = valores
        combo.set(next((v for v in valores if v.split(" ")[0] == actual), ""))

    def _ref_procesos(self) -> None:
        previo = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for p in self.kernel.procesos.values():
            estado = p.estado.value + (" (abortado)" if p.abortado else "")
            self.tree.insert("", "end", iid=str(p.pid), tags=(p.estado.name,), values=(
                p.pid, p.nombre, estado, f"{p.tamano_mb} MB", p.rafaga_total, p.rafaga_restante,
                len(p.hilos), ",".join(p.recursos) or "-", p.motivo_bloqueo or "-"))
        if previo and self.tree.exists(previo[0]):
            self.tree.selection_set(previo[0])

    def _ref_planificador(self) -> None:
        k = self.kernel
        # Cola de listos
        c = self.canvas_cola
        c.delete("all")
        x = 8
        if not k.planificador.cola_listos:
            c.create_text(10, 25, text="Cola de listos vacía", anchor="w", fill="#888888")
        for p in k.planificador.cola_listos:
            c.create_rectangle(x, 8, x + 92, 42, fill=color_pid(p.pid), outline="")
            c.create_text(x + 46, 25, text=f"P{p.pid}  r={p.rafaga_restante}", fill="white",
                          font=("Segoe UI", 9, "bold"))
            x += 104
        # Gantt
        g = self.canvas_gantt
        g.delete("all")
        segmentos = k.planificador.gantt
        if not segmentos:
            g.create_text(10, 40, text="Aún no se ha ejecutado ningún proceso.", anchor="w", fill="#888888")
            g.configure(scrollregion=(0, 0, 400, 90))
        else:
            esc, x0, y0, h = 30, 12, 12, 42
            for pid, ini, fin in segmentos:
                x1, x2 = x0 + ini * esc, x0 + fin * esc
                g.create_rectangle(x1, y0, x2, y0 + h, fill=color_pid(pid), outline="white")
                g.create_text((x1 + x2) / 2, y0 + h / 2, text=f"P{pid}", fill="white",
                              font=("Segoe UI", 9, "bold"))
                g.create_text(x1, y0 + h + 12, text=str(ini), font=("Segoe UI", 8))
            ultimo = segmentos[-1][2]
            g.create_text(x0 + ultimo * esc, y0 + h + 12, text=str(ultimo), font=("Segoe UI", 8))
            g.configure(scrollregion=(0, 0, x0 + ultimo * esc + 30, 90))
            g.xview_moveto(1)
        # Métricas
        m = k.metricas()
        self.tree_met.delete(*self.tree_met.get_children())
        for p in m["terminados"]:
            self.tree_met.insert("", "end", values=(
                p.pid, p.nombre, p.tiempo_llegada, p.rafaga_total, p.tiempo_finalizacion,
                p.tiempo_retorno, p.tiempo_espera, p.tiempo_respuesta, p.cambios_contexto))
        if m["terminados"]:
            self.lbl_met.config(
                text=f"Espera promedio: {m['espera_promedio']:.2f}   │   "
                     f"Retorno promedio: {m['retorno_promedio']:.2f}   │   "
                     f"Respuesta promedio: {m['respuesta_promedio']:.2f}   │   "
                     f"Cambios de contexto: {m['cambios_contexto']}")
        else:
            self.lbl_met.config(text="Aún no hay procesos terminados.")

    def _ref_memoria(self) -> None:
        mem = self.kernel.memoria
        usada = mem.memoria_usada_mb()
        self.lbl_ram.config(text=f"RAM física: {mem.ram_mb} MB = {mem.total_marcos} marcos de "
                                 f"{mem.marco_mb} MB   │   Usada: {usada} MB   │   Libre: {mem.memoria_libre_mb()} MB")
        self.barra_ram.config(maximum=mem.ram_mb, value=usada)
        c = self.canvas_mem
        c.delete("all")
        por_fila, ancho, alto, pad = 5, 112, 64, 8
        for n in range(mem.total_marcos):
            fila, col = divmod(n, por_fila)
            x, y = pad + col * (ancho + pad), pad + fila * (alto + pad)
            dueno = mem.marcos[n]
            if dueno is None:
                relleno, texto, fg = "#ECECEC", "libre", "#888888"
            else:
                try:
                    pagina = mem.tablas_paginas[dueno].index(n)
                except (KeyError, ValueError):
                    pagina = "?"
                relleno, texto, fg = color_pid(dueno), f"P{dueno}.{pagina}", "white"
            c.create_rectangle(x, y, x + ancho, y + alto, fill=relleno, outline="#BBBBBB")
            c.create_text(x + 5, y + 4, text=f"M{n:02d}", anchor="nw", fill=fg, font=("Consolas", 8))
            c.create_text(x + ancho / 2, y + alto / 2, text=texto, fill=fg, font=("Segoe UI", 11, "bold"))
            c.create_text(x + ancho / 2, y + alto - 9, text=f"{n * mem.marco_mb}-{(n + 1) * mem.marco_mb - 1} MB",
                          fill=fg, font=("Consolas", 8))
        filas = math.ceil(mem.total_marcos / por_fila)
        c.configure(width=pad + por_fila * (ancho + pad), height=pad + filas * (alto + pad))
        self.tree_pag.delete(*self.tree_pag.get_children())
        for pid, marcos in mem.tablas_paginas.items():
            for i, m in enumerate(marcos):
                self.tree_pag.insert("", "end", values=(
                    f"P{pid}", i, m, f"{m * mem.marco_mb}-{(m + 1) * mem.marco_mb - 1} MB"))

    def _ref_semaforo(self) -> None:
        s = self.kernel.semaforo
        libre = s.valor == 1
        dueno = f"P{s.propietario}" if s.propietario is not None else "-"
        cola = ", ".join(f"P{p}" for p in s.cola_espera) or "(vacía)"
        self.lbl_sem.config(
            text=f"Valor del semáforo  : {'1 (libre)' if libre else '0 (ocupado)'}\n"
                 f"En sección crítica  : {dueno}\n"
                 f"Cola de espera      : {cola}\n"
                 f"Variable global     : {self.kernel.variable_global}",
            fg="#2E8B57" if libre else "#C0392B")

    def _ref_deadlock(self) -> None:
        k = self.kernel
        self.tree_rec.delete(*self.tree_rec.get_children())
        for rid, r in k.recursos.recursos.items():
            dueno = f"P{r['propietario']}" if r["propietario"] is not None else "libre"
            self.tree_rec.insert("", "end", values=(rid, dueno, ", ".join(f"P{p}" for p in r["cola"]) or "-"))
        ciclo = k.recursos.detectar_deadlock()
        if ciclo:
            cadena = " → ".join(f"P{p}" for p in ciclo + [ciclo[0]])
            self.lbl_dl.config(text=f"⚠ DEADLOCK DETECTADO: {cadena}", fg="#C0392B")
        else:
            self.lbl_dl.config(text="✓ Sin deadlock: no hay ciclos en el grafo de espera", fg="#2E8B57")
        self._dibujar_grafo(ciclo or [])

    def _dibujar_grafo(self, ciclo: list) -> None:
        c = self.canvas_grafo
        c.delete("all")
        grafo = self.kernel.recursos.grafo_espera()
        nodos = sorted(set(grafo) | {d for destinos in grafo.values() for d in destinos})
        if not nodos:
            c.create_text(14, 20, text="(sin aristas: ningún proceso espera recursos)",
                          anchor="w", fill="#888888")
            return
        c.update_idletasks()
        ancho, alto = max(c.winfo_width(), 400), max(c.winfo_height(), 260)
        cx, cy, radio = ancho / 2, alto / 2, min(ancho, alto) / 2 - 50
        pos = {}
        for i, p in enumerate(nodos):
            ang = 2 * math.pi * i / len(nodos) - math.pi / 2
            pos[p] = (cx + radio * math.cos(ang), cy + radio * math.sin(ang))
        r_nodo = 24
        en_ciclo = set(ciclo)
        for origen, destinos in grafo.items():
            for destino in destinos:
                (x1, y1), (x2, y2) = pos[origen], pos[destino]
                dx, dy = x2 - x1, y2 - y1
                largo = math.hypot(dx, dy) or 1
                ux, uy = dx / largo, dy / largo
                ox, oy = -uy * 8, ux * 8        # desplazamiento para no solapar A→B con B→A
                rojo = origen in en_ciclo and destino in en_ciclo
                c.create_line(x1 + ux * r_nodo + ox, y1 + uy * r_nodo + oy,
                              x2 - ux * r_nodo + ox, y2 - uy * r_nodo + oy,
                              arrow=tk.LAST, width=2, fill="#C0392B" if rojo else "#555555")
                try:
                    rid = self.kernel.recursos.esperando(origen)
                except Exception:
                    rid = ""
                c.create_text((x1 + x2) / 2 + ox * 2.2, (y1 + y2) / 2 + oy * 2.2, text=f"espera {rid}",
                              font=("Segoe UI", 8), fill="#333333")
        for p, (x, y) in pos.items():
            c.create_oval(x - r_nodo, y - r_nodo, x + r_nodo, y + r_nodo, fill=color_pid(p), outline="white", width=2)
            c.create_text(x, y, text=f"P{p}", fill="white", font=("Segoe UI", 11, "bold"))

    def _ref_bitacora(self) -> None:
        nuevos = self.kernel.bitacora[self.visto:]
        if nuevos:
            self.txt_bit.config(state="normal")
            for tiempo, nivel, mensaje in nuevos:
                self.txt_bit.insert("end", f"[t={tiempo:>4}] {nivel:<6} {mensaje}\n", nivel)
            self.txt_bit.see("end")
            self.txt_bit.config(state="disabled")
            self.visto = len(self.kernel.bitacora)
        if self.kernel.bitacora:
            tiempo, nivel, mensaje = self.kernel.bitacora[-1]
            corto = mensaje if len(mensaje) <= 150 else mensaje[:147] + "..."
            self.lbl_ultimo.config(text=f"[t={tiempo}] {nivel}: {corto}", fg=COLOR_NIVEL.get(nivel, "#333333"))
        else:
            self.lbl_ultimo.config(text="Listo. Cree un proceso para empezar.", fg="#777777")


def iniciar() -> None:
    App().mainloop()
