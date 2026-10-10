"""Leer facturas: la cola de PDF, Gemini, el cliente del lote y unir hojas.

Parte de la ventana principal (app.py), separada para que cada tarea
viva en su sitio. Los métodos usan el estado de la ventana (self).
"""

from __future__ import annotations

import os
import time
import weakref
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from facturas_excel import almacen, archivo, costes, imagen_hoja, muestras_revision
from facturas_excel.banda_avisos import AVISO, ERROR, INFO
from facturas_excel.claves import leer_api_key
from facturas_excel.dialogo_cliente import DialogoCliente
from facturas_excel.clientes import marcar_cliente, mismo_nombre, recordar_nombre
from facturas_excel.control_facturas import clave_documento
from facturas_excel.pdf import PAGINAS_POR_BLOQUE, dividir_pdf, numero_paginas
from facturas_excel.procesar import (
    analizar_cliente, clave_proveedor, fusionar_paginas_manual, preparar_lote,
    recordar_nif,
)
from facturas_excel.registro import parece_listado
from facturas_excel.rutas import dir_datos
from facturas_excel.union_bloques import unir_ultimo_bloque

from facturas_excel.rutas import escritorio
from facturas_excel.ventana_comun import EXT_FACTURA
from facturas_excel.hilos import NO_LEIDA_AL_CERRAR, Worker

# Cada cuánto se vuelve a intentar poner en el lote un bloque leído que llegó
# con una pregunta abierta (milisegundos).
REINTENTO_APLAZADO_MS = 250
# Al cerrar a mitad de lectura, lo que se espera a que llegue el bloque que se
# está leyendo (segundos): lo que no llega a tiempo vuelve a la cola, que se
# guarda con la sesión.
ESPERA_LECTURA_AL_CERRAR_S = 5
# Lo que se guarda de cada bloque de la cola con la sesión (lo demás, como
# la lectura en marcha, no sirve la próxima vez).
CLAVES_COLA = ("rutas", "original", "muestra_id", "etiqueta", "parte", "partes",
               "archivar", "mover_original", "desde_escaner", "sin_identificar",
               "tipo_declarado")


class LecturaMixin:
    def _cargar(self):
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Elige facturas (PDF o imágenes)", escritorio(),
            "Facturas (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp)")
        if rutas:
            self.procesar_rutas(rutas)

    def procesar_rutas(self, rutas, desde_escaner: bool = False,
                       tipo_declarado: str = ""):
        """Añade documentos a la cola, dividiendo los PDF largos en bloques.

        `tipo_declarado` es lo que dijo la persona al escanear («gastos» o
        «ingresos»): va con cada bloque de ese escaneo, no en la ventana, que
        la puede cambiar otro escaneo mientras se lee éste."""
        self._esperar_archivo()      # antes, lo que se esté archivando
        rutas = [os.path.abspath(r) for r in rutas
                 if os.path.isfile(r) and os.path.splitext(r)[1].lower() in EXT_FACTURA]
        if not rutas:
            QMessageBox.warning(self, "Archivos no compatibles",
                                "No se encontraron PDFs o imágenes válidas.")
            return
        sin_identificar = (len(rutas) == 1 and archivo.sin_identificar(rutas[0]))
        # Si lo que se ha soltado es el listado de Aplifisa, NO se manda a
        # Gemini: aqui se lee gratis y lo que se quiere es contrastarlo.
        listados = [r for r in rutas if r.lower().endswith(".pdf")
                    and parece_listado(r)]
        if listados:
            self._ofrecer_contraste(listados[0])
            rutas = [r for r in rutas if r not in listados]
            if not rutas:
                return
        # La copia del original (un PDF de 200 MB) se hace aparte, sin parar
        # la ventana: su huella no hace falta hasta acabar el primer bloque.
        muestras = {ruta: self._capturar_original_aparte(ruta) for ruta in rutas}
        api_key = leer_api_key()
        if not api_key:
            # Sin lectura se guarda igual el original (y se avisa si falla).
            for futuro in muestras.values():
                self._muestra_capturada({"muestra_id": futuro})
            QMessageBox.warning(self, "Falta la API key",
                                "Configura primero tu API key de Gemini.")
            return
        declarado = (tipo_declarado or self._tipo_escaneo) if desde_escaner else ""
        elementos = []
        try:
            for ruta in rutas:
                if ruta.lower().endswith(".pdf"):
                    partes = dividir_pdf(ruta, PAGINAS_POR_BLOQUE)
                    for numero, parte in enumerate(partes, 1):
                        mover_original = bool(desde_escaner or sin_identificar)
                        elementos.append({
                            "rutas": [parte],
                            "original": ruta, "muestra_id": muestras.get(ruta),
                            "etiqueta": os.path.splitext(os.path.basename(parte))[0],
                            "parte": numero,
                            "partes": len(partes),
                            # Todo PDF termina en el archivo documental. Los
                            # externos se COPIAN; solo se mueve el provisional
                            # creado por el escáner de la propia aplicación.
                            "archivar": True,
                            "mover_original": mover_original,
                            "desde_escaner": bool(desde_escaner),
                            "sin_identificar": bool(sin_identificar),
                            "tipo_declarado": declarado,
                        })
                else:
                    elementos.append({
                        "rutas": [ruta], "original": ruta, "muestra_id": muestras.get(ruta),
                        "etiqueta": os.path.splitext(os.path.basename(ruta))[0],
                        "parte": 1, "partes": 1,
                        "archivar": False,
                        "mover_original": False,
                        "desde_escaner": bool(desde_escaner),
                        "sin_identificar": bool(sin_identificar),
                        "tipo_declarado": declarado,
                    })
        except Exception as e:
            QMessageBox.critical(
                self, "No se pudo preparar el PDF",
                f"No se ha añadido a la cola:\n\n{e}")
            return

        # En curso hasta que su bloque está en el lote, no hasta que el hilo
        # acaba: con un aviso abierto al terminar un bloque, el hilo ya no
        # corría y se arrancaba otra lectura encima (dos a la vez, y al
        # soltar una viva el programa se cerraba de golpe).
        en_curso = self._lectura_en_curso()
        if not en_curso and not self._cola:
            self._cola_total = 0
            self._cola_completados = 0
        self._cola.extend(elementos)
        self._cola_total += len(elementos)
        self.btn_gastos.setEnabled(False)
        self.btn_ventas.setEnabled(False)
        self.progreso.setVisible(True)
        self.progreso.setValue(0)
        if en_curso:
            self.lbl_estado.setText(
                f"Añadidos {len(elementos)} bloque(s). Cola total: "
                f"{self._cola_completados + 1}/{self._cola_total} en curso.")
            return
        self._iniciar_siguiente_cola(api_key)

    def _lectura_en_curso(self) -> bool:
        """Si hay un bloque leyéndose (o leído y aún sin poner en el lote), o
        una lectura que se dejó atrás al cerrar y todavía no ha acabado."""
        return self._elemento_cola_actual is not None or any(
            w.isRunning() for w in self._lecturas_abandonadas)

    def _bloques_por_leer(self) -> int:
        """Los bloques de la cola que aún no están en el lote (el que se lee
        de antes de «Vaciar todo» no cuenta: ya no es del lote)."""
        actual = self._elemento_cola_actual
        return len(self._cola) + (actual is not None
                                  and not self._lectura_descartada(actual))

    def _iniciar_siguiente_cola(self, api_key=None):
        # Una sola lectura a la vez, y nunca desde dentro de otro arranque
        # (un aviso abierto deja que lleguen otras señales mientras tanto).
        # Al cerrar el programa no se empieza nada: la cola se guarda.
        if self._iniciando_cola or self._cerrando or self._lectura_en_curso():
            return
        if not self._cola:
            self._elemento_cola_actual = None
            self.progreso.setVisible(False)
            self.btn_cargar.setEnabled(True)
            hay_datos = self.tabla.rowCount() > 0
            self.btn_gastos.setEnabled(hay_datos)
            self.btn_registro.setEnabled(hay_datos)
            if self._cola_total:
                self.lbl_estado.setText(
                    f"Cola terminada: {self._cola_completados} bloque(s) procesado(s).")
            # Lo dudoso se señala en el documento mientras se revisa lo demás.
            self._localizar_dudosas()
            return
        api_key = api_key or leer_api_key()
        if not api_key:
            self.lbl_estado.setText("Cola pendiente: falta la API key de Gemini.")
            return
        self._iniciando_cola = True
        try:
            # La lectura anterior ya entregó su bloque: le queda un instante
            # para acabar. Se espera, para que nunca haya dos hilos leyendo.
            for anterior in list(self._lecturas_vivas):
                if getattr(anterior, "entregada", False) and anterior.isRunning():
                    anterior.wait(2000)
            elemento = self._cola.pop(0)
            elemento["generacion"] = self._generacion_cola
            self._elemento_cola_actual = elemento
            self._rutas_actuales = list(elemento["rutas"])
            self._escaneo_reciente = elemento["desde_escaner"]
            self._escaneo_sin_identificar = elemento["sin_identificar"]
            self.lbl_origen.setText(elemento["etiqueta"])
            actual = self._cola_completados + 1
            self.lbl_estado.setText(
                f"Cola {actual}/{self._cola_total}: leyendo {elemento['etiqueta']}…")
            self.worker = Worker(self._rutas_actuales, api_key)
            self._seguir_lectura(self.worker)
            self.worker.start()
        finally:
            self._iniciando_cola = False

    def _seguir_lectura(self, worker) -> None:
        """Conecta la lectura con la ventana y la conserva hasta que acabe.

        Lo que entrega (el bloque leído o el fallo) pasa antes por
        `_lectura_entregada`, que lo descarta si ya no es la lectura de ahora
        (una que se dejó atrás al cerrar). La lectura se guarda en
        `_lecturas_vivas` hasta su `finished`: soltar un QThread que aún
        trabaja tumba el programa («QThread: Destroyed while thread is still
        running»)."""
        referencia = weakref.ref(worker)
        worker.progreso.connect(self._on_progreso)
        worker.gasto.connect(self._on_gasto)
        worker.terminado.connect(
            lambda *datos: self._lectura_entregada(referencia, datos=datos))
        worker.fallo.connect(
            lambda mensaje: self._lectura_entregada(referencia, fallo=mensaje))
        acabada = getattr(worker, "finished", None)
        if acabada is not None:
            self._lecturas_vivas.append(worker)
            acabada.connect(lambda: self._lectura_acabada(referencia()))

    def _lectura_entregada(self, referencia, datos=None, fallo=None) -> None:
        """Una lectura entrega su bloque (`datos`) o su fallo."""
        worker = referencia()
        if (worker is None or worker is not self.worker or self._cerrado
                or worker in self._lecturas_abandonadas
                or self._elemento_cola_actual is None):
            # Una lectura que ya no es la de ahora (la que se dejó atrás al
            # cerrar, cuyo bloque volvió a la cola), o la ventana ya se cerró
            # (lo leído y la cola se guardaron al cerrar): no toca el lote.
            return
        worker.entregada = True
        if fallo is not None:
            self._on_fallo(fallo)
        else:
            self._incorporar(datos)

    def _lectura_acabada(self, worker) -> None:
        """El hilo de una lectura ha acabado del todo: ya se puede soltar."""
        if worker is None:
            return
        if worker in self._lecturas_vivas:
            self._lecturas_vivas.remove(worker)
        abandonada = worker in self._lecturas_abandonadas
        if abandonada:
            self._lecturas_abandonadas.remove(worker)
        if (worker is self.worker and not getattr(worker, "entregada", False)
                and self._elemento_cola_actual is not None and not self._cerrado):
            # Acabó sin entregar nada (no debería pasar): la cola no se para.
            worker.entregada = True
            self._on_fallo("La lectura se cortó sin dar resultado.")
        elif abandonada:
            self._iniciar_siguiente_cola()

    # ---------- poner en el lote un bloque leído ----------

    def _hay_que_esperar(self) -> bool:
        """Si ahora no se puede poner un bloque en el lote: se está poniendo
        otro (con una pregunta abierta dentro) o hay un diálogo abierto que
        trabaja con las filas de ahora (unir hojas, exportar…)."""
        return bool(self._incorporando or self._preguntas_abiertas
                    or QApplication.activeModalWidget() is not None)

    @contextmanager
    def _pregunta_abierta(self):
        """Mientras se pregunta algo sobre las filas de ahora, ningún bloque
        nuevo cambia la tabla (los diálogos de prueba no son modales de
        verdad: esto vale para los dos)."""
        self._preguntas_abiertas += 1
        try:
            yield
        finally:
            self._preguntas_abiertas -= 1

    def _lectura_descartada(self, elemento) -> bool:
        """Si es de antes de «Vaciar todo»: ya no es de este lote."""
        return bool(elemento) and \
            elemento.get("generacion", self._generacion_cola) != self._generacion_cola

    def _descartar_lectura(self, elemento) -> None:
        """Lo leído de un lote que se vació mientras se leía: ni filas ni
        partes; la cola sigue con lo que haya ahora."""
        self._limpiar_parte_interna(elemento)
        if self._elemento_cola_actual is elemento:
            self._elemento_cola_actual = None
        self._iniciar_siguiente_cola()
        if not self._lectura_en_curso():
            self._resumen()      # la barra, con el lote de ahora

    def _devolver_a_la_cola(self, elemento) -> None:
        """Al cerrar, un bloque a medias vuelve a la cola (que se guarda).

        Uno de antes de «Vaciar todo» no: ya no es del lote. Si al cerrar
        enseguida su lectura cancelada no llegaba, se guardaba como cola y al
        abrir se ofrecía seguir leyendo lo que se había vaciado."""
        if not elemento:
            return
        if self._elemento_cola_actual is elemento:
            self._elemento_cola_actual = None
        if self._lectura_descartada(elemento):
            self._limpiar_parte_interna(elemento)
            return
        if elemento not in self._cola:
            self._cola.insert(0, elemento)

    @staticmethod
    def _lectura_cortada(datos) -> bool:
        """Si alguna hoja se quedó sin pedir porque se cancelaba la lectura."""
        crudos = datos[3] if len(datos) > 3 else None
        return any(str((d or {}).get("_error", "")).startswith(NO_LEIDA_AL_CERRAR[:18])
                   for *_, d in (crudos or []))

    def _incorporar(self, datos) -> None:
        """Pone en el lote el bloque leído de la lectura de ahora.

        - Si es de antes de «Vaciar todo», se descarta.
        - Al cerrar se pone sin preguntar nada; si se quedó a medias (hojas
          sin pedir), vuelve a la cola, que se guarda con la sesión.
        - Con una pregunta abierta (o poniendo otro bloque) espera y se
          reintenta: un bloque que llegaba con «¿Unir?» abierto rehacía la
          tabla y la unión borraba otras facturas.
        - El guardado automático no salta mientras: la sesión llegaba a
          guardarse con el bloque en el lote y la tabla sin rehacer."""
        elemento = self._elemento_cola_actual
        if self._lectura_descartada(elemento):
            self._descartar_lectura(elemento)
            return
        if self._cerrando:
            if self._lectura_cortada(datos):
                self._devolver_a_la_cola(elemento)
                return
        elif self._hay_que_esperar():
            self._lectura_aplazada = datos
            QTimer.singleShot(REINTENTO_APLAZADO_MS, self._reintentar_aplazada)
            return
        self._timer_sesion.stop()
        self._incorporando += 1
        try:
            self._on_terminado(*datos)
        finally:
            self._incorporando -= 1
            self._timer_sesion.start()
            if elemento is not None and self._elemento_cola_actual is elemento:
                # Se cortó a medias (un fallo poniéndolo en la tabla): la
                # cola no se queda parada.
                self._limpiar_parte_interna(elemento)
                self._elemento_cola_actual = None
                self._iniciar_siguiente_cola()

    def _reintentar_aplazada(self) -> None:
        datos, self._lectura_aplazada = self._lectura_aplazada, None
        if datos is not None and not self._cerrado:
            self._incorporar(datos)

    # ---------- cerrar, vaciar y la cola de la próxima vez ----------

    def _parar_lectura_al_cerrar(self) -> None:
        """Al cerrar a mitad de lectura: no se dibujan ni se piden más hojas,
        se espera un poco a que llegue lo ya leído (y se pone en el lote sin
        preguntar nada) y lo que no llega a tiempo vuelve a la cola, que se
        guarda con la sesión para seguir la próxima vez.

        Antes se seguía leyendo (y pagando) con la ventana cerrada, la sesión
        se guardaba sin lo que llegaba después y el programa se cerraba de
        golpe al soltar la lectura viva."""
        datos, self._lectura_aplazada = self._lectura_aplazada, None
        if datos is not None:
            self._incorporar(datos)          # llegó con una pregunta abierta
        elemento = self._elemento_cola_actual
        if elemento is None:
            return
        worker = self.worker
        if worker is not None and hasattr(worker, "cancelar"):
            worker.cancelar()
        # A la de antes de «Vaciar todo» no se la espera: lo que entregue se
        # tira igual (ver _devolver_a_la_cola).
        if worker is not None and hasattr(worker, "wait") \
                and not self._lectura_descartada(elemento):
            self.lbl_estado.setText("Cerrando: guardando lo ya leído…")
            limite = time.monotonic() + ESPERA_LECTURA_AL_CERRAR_S
            while self._elemento_cola_actual is not None \
                    and time.monotonic() < limite:
                corriendo = worker.isRunning()
                # Lo que entrega la lectura llega como evento: se atiende
                # aquí (sin clics ni teclas, como al esperar al archivo).
                QCoreApplication.processEvents(QEventLoop.ExcludeUserInputEvents, 50)
                if not corriendo:
                    break        # acabó, y lo que entregó ya se ha atendido
                worker.wait(50)
        if self._elemento_cola_actual is not None:
            # No llegó a tiempo: vuelve a la cola, y esa lectura queda atrás
            # (lo que entregue ya no toca el lote; al salir no se la espera).
            if worker is not None and worker.isRunning() \
                    and worker not in self._lecturas_abandonadas:
                self._lecturas_abandonadas.append(worker)
            self._devolver_a_la_cola(self._elemento_cola_actual)

    def _soltar_cola(self) -> None:
        """«Vaciar todo» tira también la cola: lo que esperaba turno, lo que
        quedó de la última vez y lo que se está leyendo, que se cancela (lo que
        entregue se descarta: antes volvía a aparecer en el lote vacío). Sus
        partes temporales se borran."""
        # Fuera de la cola antes de borrar sus partes: si no, las de un PDF
        # cargado dos veces se guardaban unas a otras y se quedaban.
        soltados = [*self._cola, *self._cola_guardada]
        self._cola = []
        self._cola_guardada = []
        for elemento in soltados:
            self._limpiar_parte_interna(elemento)
        self._generacion_cola += 1
        self._cola_total = self._cola_completados = 0
        actual = self._elemento_cola_actual
        if actual is None:
            return
        worker = self.worker
        if worker is not None and hasattr(worker, "cancelar"):
            worker.cancelar()
        if self._lectura_aplazada is not None:
            # Ya había llegado (esperaba a una pregunta): se descarta ya.
            self._lectura_aplazada = None
            self._descartar_lectura(actual)

    @staticmethod
    def _elemento_para_guardar(elemento) -> dict:
        guardado = {clave: elemento[clave] for clave in CLAVES_COLA if clave in elemento}
        huella = elemento.get("muestra_id")
        if isinstance(huella, Future):
            # La copia del original, si ya acabó; si no, se rehace al seguir.
            huella = (huella.result() if huella.done() and not huella.cancelled()
                      and huella.exception() is None else None)
        guardado["muestra_id"] = huella if isinstance(huella, str) else None
        return guardado

    def _cola_para_guardar(self) -> list:
        """Lo que queda por leer, para la sesión: el bloque que se está
        leyendo (si se corta, se vuelve a leer entero), lo que espera turno y
        lo que quedó de la última vez sin seguir todavía."""
        elementos = [self._elemento_cola_actual, *self._cola, *self._cola_guardada]
        # Sin lo que se sigue leyendo de antes de «Vaciar todo» (el guardado
        # automático lo guardaba, y tras un corte se ofrecía seguir con él).
        return [self._elemento_para_guardar(e) for e in elementos
                if e and not self._lectura_descartada(e)]

    def _partes_de_la_cola(self) -> set:
        """Las partes temporales (cola_pdf) que aún hacen falta."""
        return {os.path.abspath(ruta)
                for elemento in [self._elemento_cola_actual, *self._cola,
                                 *self._cola_guardada] if elemento
                for ruta in elemento.get("rutas", [])}

    def _recuperar_cola_guardada(self, cola) -> None:
        """La cola que se guardó con la sesión (solo lo que aún se puede leer:
        sus partes tienen que seguir ahí). Lo que ya no está (se borraron sus
        hojas, o el PDF o la imagen suelta) se dice al ofrecerla: antes se
        olvidaba sin decir nada."""
        self._cola_guardada, self._cola_perdida = [], []
        for elemento in cola or []:
            if not isinstance(elemento, dict) or not elemento.get("rutas"):
                continue
            if all(os.path.isfile(ruta) for ruta in elemento["rutas"]):
                self._cola_guardada.append(dict(elemento))
            else:
                self._cola_perdida.append(elemento)

    @staticmethod
    def _nombres_de(elementos) -> str:
        nombres = sorted({os.path.basename(e.get("original") or e["rutas"][0])
                          for e in elementos})
        return ", ".join(nombres[:3]) + (" y otros" if len(nombres) > 3 else "")

    def _ofrecer_cola_guardada(self, antes: str = "") -> None:
        """Ofrece seguir leyendo lo que quedó a medias, en la banda (no se
        lee solo: cuesta dinero y puede que ya no haga falta).

        `antes` es otro aviso de la apertura que va delante, en el mismo:
        la banda enseña uno solo y éste lo tapaba."""
        perdida, self._cola_perdida = getattr(self, "_cola_perdida", []), []
        textos = [antes] if antes else []
        if self._cola_guardada:
            hojas = 0
            for elemento in self._cola_guardada:
                for ruta in elemento.get("rutas", []):
                    try:
                        hojas += numero_paginas(ruta) if ruta.lower().endswith(".pdf") else 1
                    except Exception:
                        pass
            textos.append(
                f"La última vez quedó sin leer parte de "
                f"{self._nombres_de(self._cola_guardada)}: "
                f"{len(self._cola_guardada)} bloque(s), {hojas} hoja(s).")
        if perdida:
            cuantos = f"{len(perdida)} bloque(s) de {self._nombres_de(perdida)}"
            textos.append(
                (f"Además, {cuantos} que quedaban por leer ya no están"
                 if self._cola_guardada else
                 f"La última vez quedaron sin leer {cuantos}, pero ya no están")
                + " (se borraron o se movieron sus hojas): vuelva a cargarlas si "
                "hace falta.")
        if not textos:
            return
        self._avisar(" ".join(textos), AVISO, segundos=0,
                     deshacer=self._seguir_cola_guardada if self._cola_guardada else None,
                     boton="Seguir leyendo")

    def _seguir_cola_guardada(self) -> None:
        """Pone en la cola lo que quedó por leer la última vez."""
        elementos, self._cola_guardada = self._cola_guardada, []
        elementos = [e for e in elementos
                     if all(os.path.isfile(ruta) for ruta in e.get("rutas", []))]
        if not elementos:
            self._avisar("Las partes que quedaban por leer ya no están. Vuelva "
                         "a cargar el PDF.", AVISO)
            return
        # La copia del original en las muestras, si no llegó a hacerse.
        copias = {}
        for elemento in elementos:
            original = elemento.get("original") or ""
            if not elemento.get("muestra_id") and os.path.isfile(original):
                if original not in copias:
                    copias[original] = self._capturar_original_aparte(original)
                elemento["muestra_id"] = copias[original]
        if not self._lectura_en_curso() and not self._cola:
            self._cola_total = 0
            self._cola_completados = 0
        self._cola.extend(elementos)
        self._cola_total += len(elementos)
        self.btn_gastos.setEnabled(False)
        self.progreso.setVisible(True)
        self.progreso.setValue(0)
        self._iniciar_siguiente_cola()

    def _pasar_al_siguiente_bloque(self, elemento) -> None:
        """El bloque ya está en el lote: su parte temporal sobra y la cola
        sigue con el siguiente, que se pone a leer ya (aunque aún haya que
        preguntar algo de éste: su bloque esperará a la respuesta)."""
        self._limpiar_parte_interna(elemento)
        self._cola_completados += 1
        if elemento and self._elemento_cola_actual is elemento:
            self._elemento_cola_actual = None
        if self._cola:
            self._iniciar_siguiente_cola()

    def _on_progreso(self, actual, total):
        if self._cerrando or self._lectura_descartada(self._elemento_cola_actual):
            return      # una lectura que ya no cuenta (cerrando, o tras vaciar)
        self.progreso.setMaximum(total)
        self.progreso.setValue(actual)
        bloque = self._cola_completados + 1
        self.lbl_estado.setText(
            f"Cola {bloque}/{self._cola_total} · páginas {actual}/{total}")

    def _capturar_original_aparte(self, ruta) -> Future | None:
        """Guarda el original en las muestras en un hilo aparte (en orden).

        Devuelve el «pendiente» de su huella, que se recoge con
        `_muestra_capturada` antes de mover el original o de usarla."""
        try:
            # La carpeta se fija ahora: la copia la usa aunque acabe tarde.
            raiz = muestras_revision.carpeta()
        except OSError as error:
            self._avisar_error_muestras(error)
            return None
        hilo = getattr(self, "_hilo_originales", None)
        if hilo is None:
            hilo = self._hilo_originales = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="guardar-original")
        return hilo.submit(muestras_revision.guardar_original, ruta, raiz)

    def _muestra_capturada(self, elemento: dict):
        """La huella del original del elemento de la cola (espera a que se
        acabe de copiar, si aún no). Un fallo se avisa y no para la cola."""
        valor = elemento.get("muestra_id")
        if isinstance(valor, Future):
            try:
                valor = valor.result()
            except Exception as error:
                self._avisar_error_muestras(error)
                valor = None
            elemento["muestra_id"] = valor
        return valor

    def _on_fallo(self, msg):
        elemento = self._elemento_cola_actual or {}
        if self._lectura_descartada(elemento):
            self._descartar_lectura(elemento)     # de antes de «Vaciar todo»
            return
        if self._cerrando:
            # Al cerrar no se da el bloque por perdido: vuelve a la cola, que
            # se guarda, y se lee la próxima vez.
            self._devolver_a_la_cola(elemento)
            return
        self._muestra_capturada(elemento)
        self._limpiar_parte_interna(elemento)
        self._cola_completados += 1
        self._escaneo_reciente = False
        if self._elemento_cola_actual is elemento:
            self._elemento_cola_actual = None
        # En la banda, no en una ventana: un aviso abierto paraba la cola
        # (y con otro bloque llegando mientras, el programa se cerraba).
        etiqueta = elemento.get("etiqueta") or "este bloque"
        self._avisar(f"No se pudo leer «{etiqueta}»: {msg}. La cola sigue con "
                     "el siguiente.", ERROR, segundos=0)
        self._iniciar_siguiente_cola()

    def _on_terminado(self, procesadas, nombre, nif, crudos=None):
        elemento = self._elemento_cola_actual or {}
        worker = self.worker
        if elemento:
            # Lo del bloque sale de su elemento de la cola, no de la ventana:
            # mientras se leía pudo empezar un escaneo (o esperar a una
            # pregunta) y cambiarlo.
            self._rutas_actuales = list(elemento.get("rutas", []))
            self._escaneo_reciente = bool(elemento.get("desde_escaner"))
            self._escaneo_sin_identificar = bool(elemento.get("sin_identificar"))
        # Antes de nada: el original puede moverse ahora mismo al archivo del
        # cliente, y su copia en las muestras tiene que estar ya terminada.
        self._muestra_capturada(elemento)
        # El lote guarda el asa de la imagen de cada hoja, no sus bytes (ver
        # imagen_hoja). La lectura ya las deja así; lo que aún llegue con
        # los bytes (no se pudo escribir) se intenta aquí otra vez.
        convertir = imagen_hoja.Conversor()
        procesadas = convertir.procesadas(procesadas)
        if crudos:
            crudos = convertir.registros(crudos)
        rutas_parte = list(self._rutas_actuales)
        if (elemento.get("parte", 1) > 1 and self._bloques
                and self._bloques[-1].get("original") == elemento.get("original")
                and self._bloques[-1].get("nif")):
            # La segunda parte puede empezar solo con importes y no aportar
            # candidato a cliente. Mantener el cliente del mismo PDF completo.
            anterior = self._bloques[-1]
            nombre, nif = anterior["cliente"], anterior["nif"]
            procesadas = preparar_lote(crudos or [], nombre, nif)
        # Si el escaneo salió sin saber de quién era, ahora ya se sabe: el PDF
        # se muda solo a la carpeta del cliente antes de nombrar el bloque.
        if elemento.get("archivar"):
            original_anterior = elemento.get("original", "")
            self._rutas_actuales = [original_anterior]
            self._recolocar_escaneo(
                nombre, procesadas,
                copiar=not elemento.get("mover_original", False), nif=nif)
            original_nuevo = self._rutas_actuales[0]
            elemento["original"] = original_nuevo
            for pendiente in self._cola:
                if pendiente.get("original") == original_anterior:
                    pendiente["original"] = original_nuevo
                    pendiente["archivar"] = False
                    pendiente["mover_original"] = False
                    pendiente["desde_escaner"] = False
                    pendiente["sin_identificar"] = False
        elif not elemento:
            # También conserva el contrato de llamadas directas (pruebas y
            # pequeñas integraciones que entregan un bloque ya procesado).
            self._recolocar_escaneo(nombre, procesadas, nif=nif)
        if elemento:
            self._rutas_actuales = rutas_parte
            # Una parte interna no es documentación. Las filas y los datos
            # crudos deben apuntar siempre al PDF completo archivado y conservar
            # el número de página global para poder borrar la parte temporal.
            origen_documento = elemento.get("original", "")
            desplazamiento = ((elemento.get("parte", 1) - 1)
                              * PAGINAS_POR_BLOQUE)
            if origen_documento:
                for _, pr in procesadas:
                    pr.origen = origen_documento
                    pr.pagina += desplazamiento
                    for factura in pr.facturas:
                        factura.origen_imagen = origen_documento
                        factura.pagina_origen += desplazamiento
                        factura.ultima_pagina_origen += desplazamiento
                crudos = [
                    (imagen, origen_documento, pagina + desplazamiento, datos)
                    for imagen, _origen, pagina, datos in (crudos or [])
                ]
        referencias = {}
        for _, origen, _, _ in (crudos or []):
            if origen not in referencias:
                identificador = elemento.get("muestra_id")
                if not identificador and os.path.isfile(origen):
                    identificador = self._capturar_original(origen)
                if identificador:
                    referencias[origen] = identificador
        for _, pr in procesadas:
            for f in pr.facturas:
                f.original_id = referencias.get(f.origen_imagen, "")
        try:
            muestras_revision.guardar_lecturas(crudos or [], referencias)
        except (OSError, ValueError) as error:
            self._avisar_error_muestras(error)
        # Cada carga entra como un BLOQUE mas: asi se pueden juntar varios PDF
        # de escaner (25-30 hojas cada uno) en un unico Excel para Aplifisa.
        self._bloques.append({
            "nombre": self._nombre_bloque(elemento.get("etiqueta")),
            # Cuándo se leyó: pasa al registro de facturas al exportar.
            "leido_en": almacen.ahora(),
            "original": elemento.get("original", ""),
            "procesadas": procesadas,
            # Lo leido por Gemini, tal cual: permite rehacer el lote con otro
            # cliente sin gastar otra lectura.
            "crudos": list(crudos or []),
            "cliente": nombre,
            "nif": nif,
            # Lo que dijo el usuario al escanear ("gastos" o "ingresos"): sirve
            # para cazar una factura que sale del reves.
            "tipo_declarado": (elemento.get("tipo_declarado", "") if elemento
                               else self._tipo_escaneo if self._escaneo_reciente
                               else ""),
        })
        unir_ultimo_bloque(self._bloques)
        self._escaneo_reciente = False
        self._avisar_si_otro_cliente(nombre, nif)
        analisis = self._analisis_del_lote()
        # El nombre del cliente se guarda para proponerlo al escanear el
        # proximo taco suyo, sin tener que escribirlo otra vez (no si le falta
        # una letra: se quedaría así).
        if not any(c.nif == nif and c.nombre_roto for c in analisis.candidatos):
            recordar_nombre(nif, nombre)
        self._cliente_nif, self._cliente_nombre = nif, nombre
        self._pintar_cliente()
        self._pasar_al_siguiente_bloque(elemento)
        # Primero se confirma quién es el cliente; solo después tiene sentido
        # decidir si la otra parte contradice un NIF guardado de proveedor.
        # Un homónimo del cliente se pregunta una vez por lote: si ya se eligió
        # este cliente, no se repregunta después de cada bloque de la cola.
        ya_elegido = getattr(self, "_cliente_elegido_lote", "") == nif
        if analisis.empate or (analisis.homonimo and not ya_elegido):
            self._cambiar_cliente(automatico=True)
        self._resolver_conflictos_nif()
        self._preparar_recargo()
        self._actualizar_combo_bloques()
        self._rellenar_tabla()
        self._revalidar_todo()
        hay_datos = self.tabla.rowCount() > 0
        # Exportar, solo con la cola acabada: con bloques por leer salía un
        # Excel a medias (ver _exportar_todo).
        self.btn_gastos.setEnabled(hay_datos and not self._bloques_por_leer())
        self.btn_registro.setEnabled(hay_datos)
        self.btn_cliente.setEnabled(bool(self._bloques))
        if hay_datos and len(self._bloques) == 1:
            self.tabla.selectRow(0)
        # La muestra de revisión, con la de cada poco (la revisión del lote
        # ya la ha pedido): no una foto entera del lote por cada bloque.
        self._avisar_paginas_no_leidas(worker)
        self._iniciar_siguiente_cola()

    @staticmethod
    def _quitar_aviso_conflicto(pr, mensaje: str) -> None:
        """Retira únicamente el aviso que acaba de quedar resuelto."""
        if pr.aviso == mensaje:
            pr.aviso = ""
        else:
            pr.aviso = " ".join(pr.aviso.replace(mensaje, "").split())

    def _decidir_conflicto_nif(self, nombre: str, guardado: str,
                               leido: str, cantidad: int) -> str:
        """Pregunta una vez cuando varias facturas contradicen la memoria."""
        cuadro = QMessageBox(self)
        cuadro.setWindowTitle("Confirmar CIF/NIF del proveedor")
        cuadro.setIcon(QMessageBox.Warning)
        cuadro.setText(
            f"Para {nombre} está guardado <b>{guardado}</b>, pero "
            f"{cantidad} facturas de este lote muestran <b>{leido}</b>.")
        cuadro.setInformativeText(
            "El programa no cambiará lo aprendido sin que usted lo confirme.")
        mantener = cuadro.addButton("Mantener el guardado", QMessageBox.AcceptRole)
        sustituir = cuadro.addButton("Usar el nuevo y recordarlo", QMessageBox.ActionRole)
        revisar = cuadro.addButton("Dejar pendiente", QMessageBox.RejectRole)
        cuadro.setDefaultButton(revisar)
        cuadro.exec()
        pulsado = cuadro.clickedButton()
        if pulsado is mantener:
            return "guardado"
        if pulsado is sustituir:
            return "nuevo"
        return "revisar"

    def _resolver_conflictos_nif(self) -> None:
        """Contrasta la memoria con la evidencia acumulada de todo el lote."""
        if self._cerrando:
            return      # al cerrar no se pregunta: queda en ámbar
        grupos = {}
        for bloque in self._bloques:
            for _imagen, pr in bloque.get("procesadas", []):
                conflicto = getattr(pr, "conflicto_nif", None)
                if not conflicto:
                    continue
                clave = (clave_proveedor(conflicto["nombre"]),
                         conflicto["guardado"], conflicto["leido"])
                grupos.setdefault(clave, []).append(pr)

        for clave_grupo, procesadas in grupos.items():
            _clave, guardado, leido = clave_grupo
            decision = self._decisiones_conflicto_nif.get(clave_grupo)
            if decision:
                self._aplicar_decision_conflicto_nif(
                    procesadas, decision, guardado, leido)
                continue
            # Una discrepancia aislada se ve en amarillo. Con evidencia
            # repetida se pregunta una sola vez por todo el grupo.
            if len(procesadas) < 3:
                continue
            if any(pr.conflicto_nif.get("consultado") for pr in procesadas):
                for pr in procesadas:
                    pr.conflicto_nif["consultado"] = True
                continue
            nombre = procesadas[0].conflicto_nif["nombre"]
            decision = self._decidir_conflicto_nif(
                nombre, guardado, leido, len(procesadas))
            self._decisiones_conflicto_nif[clave_grupo] = decision
            self._aplicar_decision_conflicto_nif(
                procesadas, decision, guardado, leido)

    def _aplicar_decision_conflicto_nif(self, procesadas, decision: str,
                                        guardado: str, leido: str) -> None:
        """Aplica la decisión a este grupo y a sus partes posteriores."""
        nombre = procesadas[0].conflicto_nif["nombre"]
        if decision == "guardado":
            recordar_nif(nombre, guardado, manual=True)
            for pr in procesadas:
                for factura in pr.facturas:
                    factura.nif = guardado
        elif decision == "nuevo":
            recordar_nif(nombre, leido, manual=True)
        for pr in procesadas:
            conflicto = pr.conflicto_nif
            if decision != "revisar":
                self._quitar_aviso_conflicto(pr, conflicto["mensaje"])
                pr.conflicto_nif = None
            else:
                conflicto["consultado"] = True

    def _avisar_paginas_no_leidas(self, worker=None):
        """Detalla las páginas agotadas o ilegibles sin detener la cola: en
        la banda, no en una ventana que hay que cerrar (ver _on_fallo)."""
        worker = worker or getattr(self, "worker", None)
        fallos = getattr(worker, "fallos", None)
        if not fallos:
            return
        salto = chr(10)
        credito = getattr(worker, "sin_credito", "")
        cabecera = (
            f"Gemini se quedó sin crédito a mitad del bloque. Lo ya leído se ha "
            f"conservado; lo que falta está en rojo para leerlo cuando haya "
            f"saldo.{salto}{credito}{salto}{salto}" if credito else "")
        detalle = salto.join(
            f"· {os.path.basename(ruta) or 'documento'}, página {pagina}: {motivo}"
            for ruta, pagina, motivo in fallos[:10])
        if len(fallos) > 10:
            detalle += f"{salto}· … y {len(fallos) - 10} más"
        self._avisar(
            "Páginas sin leer. "
            f"{cabecera}"
            f"{len(fallos)} página(s) no se han podido leer y están en rojo "
            f"en la tabla:{salto}{detalle}{salto}"
            "La cola continúa. Puede volver a cargar solo esas páginas.",
            AVISO, segundos=0)

    def _limpiar_parte_interna(self, elemento: dict) -> None:
        """Borra una parte ya procesada, nunca el PDF original del usuario.

        Tampoco la que aún tiene que leer otro bloque de la cola: el mismo
        PDF vuelto a cargar (tras «Vaciar todo», o dos veces) tiene las mismas
        partes, y al descartar la lectura vieja se borraba la del bloque
        nuevo, que luego no se podía leer («no such file»)."""
        if int(elemento.get("partes", 1) or 1) <= 1:
            return
        en_uso = {os.path.normcase(os.path.abspath(ruta))
                  for otro in [self._elemento_cola_actual, *self._cola]
                  if otro and otro is not elemento
                  for ruta in otro.get("rutas", [])}
        raiz = os.path.abspath(os.path.join(dir_datos(), "cola_pdf"))
        for ruta in elemento.get("rutas", []):
            ruta_abs = os.path.abspath(ruta)
            if not os.path.normcase(ruta_abs).startswith(
                    os.path.normcase(raiz) + os.sep):
                continue
            if os.path.normcase(ruta_abs) in en_uso:
                continue        # la borrará ese bloque cuando se lea
            try:
                os.remove(ruta_abs)
                carpeta = os.path.dirname(ruta_abs)
                if os.path.isdir(carpeta) and not os.listdir(carpeta):
                    os.rmdir(carpeta)
            except OSError:
                pass

    def _analisis_del_lote(self):
        """Las partes que salen en TODO el lote (todos los bloques)."""
        datos = [d for bloque in self._bloques for *_, d in bloque.get("crudos", [])]
        return analizar_cliente(datos)

    def _cambiar_cliente(self, automatico: bool = False):
        """Quien es el cliente de la asesoria en este lote.

        Al cambiarlo se rehace todo desde lo que ya leyo Gemini: no se vuelve a
        pagar ninguna lectura.
        """
        if automatico and self._cerrando:
            return      # al cerrar no se pregunta: se decide al volver
        analisis = self._analisis_del_lote()
        if len(analisis.candidatos) < 2:
            if not automatico:
                self._avisar(
                    "En estas facturas solo se ha identificado una parte con "
                    "NIF, así que no hay entre quién elegir.", INFO)
            return
        dialogo = DialogoCliente(analisis.candidatos, self,
                                 elegido=getattr(self, "_cliente_nif", ""))
        if dialogo.exec() != QDialog.Accepted:
            return
        elegido = dialogo.elegido()
        if not elegido or not elegido.nif:
            return
        # Lo que dice una persona manda y se recuerda; y a los demas del lote
        # se les apunta como proveedores, que es lo que son.
        # Un nombre al que le falta una letra no se confirma ni se lleva a
        # la suite: se queda la confirmación del NIF.
        marcar_cliente(elegido.nif,
                       "" if elegido.nombre_roto else elegido.nombre)
        self._cliente_elegido_lote = elegido.nif
        for otro in analisis.candidatos:
            # Un homónimo del cliente (su nombre con otro NIF) no se apunta
            # como proveedor: estropearía la memoria de quien sí le compra.
            if (otro.nif != elegido.nif and otro.nombre and otro.nif
                    and not otro.nombre_roto
                    and not mismo_nombre(otro.nombre, elegido.nombre)
                    and clave_proveedor(otro.nombre)
                    != clave_proveedor(elegido.nombre)):
                recordar_nif(otro.nombre, otro.nif, manual=True)
        self._rehacer_con_cliente(elegido.nombre, elegido.nif)

    def _rehacer_con_cliente(self, nombre, nif):
        """Vuelve a montar todos los bloques con otro cliente, sin Gemini."""
        for bloque in self._bloques:
            if bloque.get("crudos"):
                bloque["procesadas"] = preparar_lote(bloque["crudos"], nombre, nif)
                bloque["cliente"], bloque["nif"] = nombre, nif
        self._cliente_nif, self._cliente_nombre = nif, nombre
        self._pintar_cliente()
        self._preparar_recargo()
        self._rellenar_tabla()
        self._revalidar_todo()
        self.lbl_estado.setText(f"Lote rehecho con {nombre or nif} como cliente.")
        self._avisar(f"Lote rehecho con {nombre or nif} como cliente, sin "
                     "volver a pagar la lectura.", INFO)

    def _nombre_bloque(self, base_preferido: str = "") -> str:
        """Nombre corto del bloque: el del PDF cargado, sin repetirse."""
        rutas = self._rutas_actuales
        if base_preferido:
            base = base_preferido
        elif not rutas:
            base = f"Bloque {len(self._bloques) + 1}"
        elif len(rutas) == 1:
            base = os.path.splitext(os.path.basename(rutas[0]))[0]
        else:
            base = f"{os.path.splitext(os.path.basename(rutas[0]))[0]} +{len(rutas) - 1}"
        usados = {b["nombre"] for b in self._bloques}   # aun no se ha añadido
        nombre, n = base, 2
        while nombre in usados:
            nombre, n = f"{base} ({n})", n + 1
        return nombre

    def _avisar_si_otro_cliente(self, nombre, nif):
        """Mezclar clientes en un mismo Excel es un lio gordo: hay que verlo."""
        anteriores = {b["nif"] for b in self._bloques[:-1] if b["nif"]}
        if not anteriores or not nif or nif in anteriores:
            return
        previo = next(b for b in self._bloques[:-1] if b["nif"])
        # En la banda: una ventana aquí paraba la cola mientras estaba
        # abierta (y con otro bloque llegando, el programa se cerraba).
        self._avisar(
            "¿Facturas de otro cliente? Este bloque parece de OTRO cliente: "
            f"bloques anteriores de {previo['cliente'] or '?'} "
            f"({previo['nif']}), bloque nuevo de {nombre or '?'} ({nif}). "
            "Se ha añadido igualmente, pero el Excel saldría con facturas de "
            "los dos. Si es un error, use «Quitar este bloque».",
            AVISO, segundos=0)

    def _on_gasto(self, modelo, coste_lote):
        self._pintar_gasto(modelo, coste_lote)
        aviso = costes.aviso_tope()
        if aviso and not getattr(self, "_aviso_tope_dado", False):
            # Una vez por sesion: recordarlo en cada lote seria un incordio.
            # En la banda: llega mientras se lee y una ventana pararía la cola.
            self._aviso_tope_dado = True
            self._avisar(f"Gasto de Gemini: {aviso}", AVISO, segundos=0)

    @staticmethod
    def _mismo_archivo(a: str, b: str) -> bool:
        return os.path.normcase(os.path.abspath(a or "")) == \
            os.path.normcase(os.path.abspath(b or ""))

    def _crudos_de_filas(self, filas: list[int]) -> list[tuple]:
        """Localiza las páginas originales de las filas, también en sesiones viejas."""
        encontrados = []
        usados = set()
        for fila in filas:
            registro_tabla = self.filas[fila]
            f = self._leer_fila(fila)
            pagina = int(getattr(f, "pagina_origen", 0) or 0)
            for ib, bloque in enumerate(self._bloques):
                for ir, crudo in enumerate(bloque.get("crudos", [])):
                    clave = (ib, ir)
                    if clave in usados:
                        continue
                    imagen, origen, pag, _datos = crudo
                    ultima = max(pagina, int(f.ultima_pagina_origen or pagina))
                    coincide_pagina = (pagina and pagina <= int(pag) <= ultima and
                                       self._mismo_archivo(origen, f.origen_imagen))
                    # Las sesiones creadas antes de guardar pagina_origen aún
                    # pueden localizarse por la miniatura y el archivo.
                    coincide_imagen = (not pagina and imagen == registro_tabla["png"] and
                                       self._mismo_archivo(origen, f.origen_imagen))
                    if coincide_pagina or coincide_imagen:
                        encontrados.append((ib, ir, crudo))
                        usados.add(clave)
        return sorted(encontrados, key=lambda r: (r[0], r[1]))

    def _localizar_hojas(self, hojas) -> list | None:
        """Dónde están ahora esas hojas (las mismas, no otras iguales), como
        `_crudos_de_filas`; None si alguna ya no está en el lote."""
        encontrados = []
        for hoja in hojas:
            sitio = next(((ib, ir) for ib, bloque in enumerate(self._bloques)
                          for ir, crudo in enumerate(bloque.get("crudos", []))
                          if crudo is hoja), None)
            if sitio is None:
                return None
            encontrados.append((*sitio, hoja))
        return sorted(encontrados, key=lambda r: (r[0], r[1]))

    def _unir_hojas_seleccionadas(self) -> None:
        filas = self._filas_seleccionadas()
        crudos = self._crudos_de_filas(filas)
        if len(crudos) < 2:
            self._avisar(
                "Para unir hojas, seleccione filas de al menos dos hojas "
                "distintas. Si una factura tiene varias líneas de IVA en la "
                "misma hoja, cuentan como una sola hoja.", AVISO)
            return
        referencias = []
        for _ib, _ir, (_img, _origen, pagina, datos) in crudos:
            referencias.append(
                f"página {pagina}: {datos.get('num_factura') or 'sin nº'}")
        pregunta = (
            "Se unirán estas hojas como UNA sola factura:\n\n· "
            + "\n· ".join(referencias)
            + "\n\nLa primera aporta número, fecha y cliente; el resumen fiscal "
              "completo de la última sustituye los subtotales intermedios."
        )
        # Lo elegido se recuerda por lo que es (sus facturas y sus hojas), no
        # por su sitio: si mientras se pregunta llega otro bloque, la tabla se
        # rehace (con la tabla ordenada, en otro orden) y por el número de
        # fila se unían y se borraban facturas que nadie había tocado.
        fuentes = [fuente for fila in filas
                   for fuente in self.filas[fila].get("fuentes", [self.filas[fila]["factura"]])]
        hojas = [crudo for _ib, _ir, crudo in crudos]
        with self._pregunta_abierta():
            respuesta = QMessageBox.question(
                self, "Confirmar unión de hojas", pregunta,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if respuesta != QMessageBox.Yes:
            return
        crudos = self._localizar_hojas(hojas)
        if crudos is None:
            self._avisar("Mientras se preguntaba ha cambiado el lote y alguna de "
                         "esas hojas ya no está igual. Vuelva a elegirlas.", AVISO)
            return

        self._guardar_muestra_revision()
        documentos = {clave_documento(f) for f in fuentes}
        primero_bloque, primero_indice, _ = crudos[0]
        destino = self._bloques[primero_bloque]
        seleccion = {(ib, ir) for ib, ir, _ in crudos}
        posicion = sum(1 for ir in range(primero_indice)
                       if (primero_bloque, ir) not in seleccion)
        fusionado = fusionar_paginas_manual([crudo for _, _, crudo in crudos])
        nueva = preparar_lote([fusionado], destino.get("cliente", ""), destino.get("nif", ""))[0]
        original_id = next((f.original_id for f in fuentes if f.original_id), "")
        for f in nueva[1].facturas:
            f.original_id = original_id
            f.edicion_manual = True
        insertada = False
        for ib, bloque in enumerate(self._bloques):
            restantes = []
            for imagen, pr in bloque["procesadas"]:
                if any(clave_documento(f) in documentos for f in pr.facturas):
                    if bloque is destino and not insertada:
                        restantes.append(nueva)
                        insertada = True
                else:
                    restantes.append((imagen, pr))
            bloque["procesadas"] = restantes
            bloque["crudos"] = [crudo for ir, crudo in enumerate(bloque.get("crudos", []))
                                if (ib, ir) not in seleccion]
        if not insertada:
            destino["procesadas"].append(nueva)
        destino["crudos"].insert(posicion, fusionado)
        self._bloques = [bloque for bloque in self._bloques
                         if bloque.get("procesadas") or bloque is destino]
        try:
            muestras_revision.guardar_lecturas(
                [fusionado], {fusionado[1]: original_id} if original_id else {})
        except (OSError, ValueError) as error:
            self._avisar_error_muestras(error)
        self._actualizar_combo_bloques()
        self._rellenar_tabla()
        self._revalidar_todo()
        self._guardar_sesion()
        numero = fusionado[3].get("num_factura") or "sin nº"
        self.lbl_estado.setText(
            f"{len(crudos)} hojas unidas como una sola factura ({numero}).")
