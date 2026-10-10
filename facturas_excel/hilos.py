"""Trabajos en segundo plano: leer con Gemini, escanear y actualizar."""

from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QObject, QThread, Signal

from facturas_excel import ajustes, costes, escaner, imagen_hoja, updater
from facturas_excel.extraccion import Extractor, SinCredito
from facturas_excel.pdf import Hojas
from facturas_excel.procesar import detectar_cliente, preparar_lote


HILOS = 10  # hojas leidas a la vez (con la clave de pago de Gemini)
# Lo que dice una hoja que no se ha pedido porque se cerró el programa (o se
# vació el lote) mientras se leía. Es el mismo texto que pone la lectura
# (extraccion.Extractor) cuando la cancelan con la hoja esperando turno: la
# ventana lo usa para saber que el bloque se quedó a medias.
NO_LEIDA_AL_CERRAR = "No leída: se cerró el programa mientras se leía."


def hilos_lectura() -> int:
    """Hojas que se leen a la vez; ajustable en ajustes.json (hilos_lectura)."""
    try:
        return max(1, min(20, int(ajustes.leer("hilos_lectura", HILOS))))
    except (TypeError, ValueError):
        return HILOS


class Worker(QThread):
    progreso = Signal(int, int)
    terminado = Signal(object, str, str, object)  # procesadas, nombre, nif, crudos
    gasto = Signal(str, float)             # modelo real, coste del lote en euros
    fallo = Signal(str)

    def __init__(self, rutas, api_key):
        super().__init__()
        self.rutas = rutas
        self.api_key = api_key
        self.fallos = []      # (archivo, pagina, motivo) de lo que no se leyó
        self.sin_credito = ""   # el aviso de Google si se acabó el crédito
        self._extractor = None
        self._hojas = None
        # Se crea ya, no con la lectura: cancelar mientras se cuentan o se
        # dibujan las hojas (antes de que exista la lectura) también vale.
        self._cancelado = threading.Event()

    def cancelar(self) -> None:
        """Al cerrar el programa (o vaciar el lote): no se dibujan más hojas,
        no se espera a Google ni se piden más."""
        self._cancelado.set()
        cancelado = getattr(self._extractor, "cancelado", None)
        if cancelado is not None:
            cancelado.set()
        # El PDF se suelta ya, sin esperar a que Gemini conteste: ya no se
        # dibuja ninguna hoja más, y la parte de la cola queda libre aunque
        # la lectura tarde (la ventana la espera como mucho 5 s y luego la
        # deja atrás; en Windows, abierta no se puede mover ni borrar).
        hojas = self._hojas
        if hojas is not None and not hojas.cerrar(espera=0.5):
            # El cerrojo de MuPDF lo puede tener un buen rato el archivo de
            # una exportación (guardando el expediente del año): la ventana
            # no se queda parada esperándolo; se suelta en cuanto quede libre.
            threading.Thread(target=hojas.cerrar, daemon=True,
                             name="soltar-pdf").start()

    def run(self):
        hojas = None
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            # Aquí solo se cuentan las hojas: cada una se dibuja en su hilo
            # justo antes de leerla (ver `tarea`). Antes se dibujaba el bloque
            # entero (de 3 a 5 s) sin que Gemini empezara, con todas sus
            # imágenes en memoria; ahora en memoria solo están las que se
            # están leyendo, y la ventana no se para mientras.
            hojas = self._hojas = Hojas(
                self.rutas, dpi=int(ajustes.leer('lectura_ppp', 150)))
            if not len(hojas):
                raise ValueError("No se encontraron páginas o imágenes compatibles.")
            extractor = Extractor(self.api_key)
            self._extractor = extractor
            if self._cancelado.is_set():        # se cerró mientras se contaban
                self.cancelar()
            total = len(hojas)
            registros = [None] * total

            consumo = []   # (modelo, tokens entrada, tokens salida) por llamada
            sin_credito = []
            leidas = []

            def sin_leer(img, origen, pagina):
                motivo = "No leída: la API key se quedó sin crédito"
                self.fallos.append((origen, pagina, motivo))
                return {"emisor_nombre": None, "lineas_iva": [{}],
                        "_error": motivo}

            def sin_imagen(idx, origen, pagina, motivo):
                """La hoja queda en rojo, sin imagen y sin pedirla a Gemini."""
                self.fallos.append((origen, pagina, motivo))
                return idx, (b"", origen, pagina, {
                    "emisor_nombre": None, "lineas_iva": [{}], "_error": motivo})

            def a_disco(img):
                """La imagen pasa a las muestras en cuanto se ha leído, aquí,
                fuera de la ventana, y el lote se queda con su asa (ver
                imagen_hoja). La que no se pueda escribir sigue con sus bytes."""
                try:
                    return imagen_hoja.a_disco(img) if img else img
                except OSError:
                    return img

            def tarea(idx):
                origen, pagina = hojas.lista[idx]
                if self._cancelado.is_set():
                    # Se está cerrando: ni se dibuja ni se pide.
                    return sin_imagen(idx, origen, pagina, NO_LEIDA_AL_CERRAR)
                try:
                    # Con el cerrojo de MuPDF solo lo suyo; la foto de un
                    # escaneo se reduce fuera (pdf.hoja_a_jpg).
                    img = hojas.imagen(idx)
                except Exception as e:
                    if self._cancelado.is_set():
                        # Cancelar suelta el PDF aunque haya hojas esperando
                        # al cerrojo para dibujarse: esas no se han roto, se
                        # han quedado sin pedir (y así la ventana sabe que el
                        # bloque está a medias y lo vuelve a poner en cola).
                        return sin_imagen(idx, origen, pagina, NO_LEIDA_AL_CERRAR)
                    # Una hoja que no se puede sacar no tumba el bloque (ni
                    # se pierde lo ya leído y pagado de las demás).
                    return sin_imagen(idx, origen, pagina,
                                      f"No se pudo sacar la imagen de la hoja: {e}"[:120])
                if self._cancelado.is_set():
                    # Se canceló mientras se dibujaba esta hoja: ya no se
                    # pide (con la ventana cerrada se seguía pagando).
                    return sin_imagen(idx, origen, pagina, NO_LEIDA_AL_CERRAR)
                if sin_credito:
                    # Se acabó el crédito en otra hoja: no se pide nada más.
                    # La imagen sí se queda, para leerla cuando haya saldo.
                    return idx, (a_disco(img), origen, pagina,
                                 sin_leer(img, origen, pagina))
                try:
                    leido = extractor.extraer(img, origen, pagina)
                    consumo.extend(leido.consumos or [(
                        leido.modelo, leido.tokens_entrada, leido.tokens_salida)])
                    datos = leido.crudo
                    leidas.append(idx)
                except SinCredito as e:
                    # No se tira lo ya leído (y pagado): esta hoja y las que
                    # faltan quedan en rojo para leerlas cuando haya saldo.
                    sin_credito.append(str(e))
                    datos = sin_leer(img, origen, pagina)
                except Exception as e:  # una factura ilegible no tumba el lote
                    # Lo pagado por los intentos fallidos también cuenta.
                    consumo.extend(getattr(e, "consumos", []) or [])
                    # Sin nombre inventado: la hoja queda vacía y en rojo, con
                    # el motivo, en lugar de un proveedor «(NO SE PUDO LEER)».
                    datos = {"emisor_nombre": None, "lineas_iva": [{}],
                             "_error": str(e)[:120]}
                    self.fallos.append((origen, pagina, str(e)[:120]))
                return idx, (a_disco(img), origen, pagina, datos)

            hechas = 0
            ex = ThreadPoolExecutor(max_workers=hilos_lectura())
            try:
                futuros = [ex.submit(tarea, i) for i in range(total)]
                for fut in as_completed(futuros):
                    idx, reg = fut.result()
                    registros[idx] = reg
                    hechas += 1
                    self.progreso.emit(hechas, total)
            finally:
                # Si algo corta el lote, las hojas que aún no han empezado se
                # cancelan: no se sigue pagando por nada.
                ex.shutdown(wait=True, cancel_futures=True)
                # Ya no queda ningún hilo dibujando: los PDF se cierran antes
                # de avisar a la ventana, que al acabar el bloque mueve el
                # original o borra la parte (en Windows, abierto no se puede).
                hojas.cerrar()
                self._registrar_consumo(consumo)

            if sin_credito:
                self.sin_credito = sin_credito[0]
                if not leidas:
                    raise SinCredito(sin_credito[0])
            nombre, nif = detectar_cliente([d for *_, d in registros])
            procesadas = preparar_lote(registros, nombre, nif)
            self.terminado.emit(procesadas, nombre, nif, registros)
        except Exception as e:  # noqa
            if hojas is not None:
                hojas.cerrar()
            self.fallo.emit(str(e))

    def _registrar_consumo(self, consumo) -> None:
        """Lo gastado en Gemini, con los tokens reales de cada respuesta."""
        modelo, coste_lote = "", 0.0
        for m, entrada, salida in consumo:
            modelo = modelo or m
            coste_lote += costes.registrar(m, entrada, salida)
        if consumo:
            self.gasto.emit(modelo, round(coste_lote, 6))


class HiloEscaneo(QThread):
    """El escaneo, fuera del hilo de la ventana: un taco de 30 hojas tarda."""
    progreso = Signal(int)      # hojas escaneadas hasta ahora
    terminado = Signal(str)     # ruta del PDF
    fallo = Signal(str)

    def __init__(self, destino, opciones):
        super().__init__()
        self.destino = destino
        self.opciones = opciones

    def run(self):
        try:
            ruta = escaner.escanear(
                self.destino, device_id=self.opciones["device_id"],
                dpi=self.opciones["dpi"],
                alimentador=self.opciones["alimentador"],
                duplex=self.opciones["duplex"],
                modo_color=self.opciones.get("modo_color", "color"),
                nombre_dispositivo=self.opciones.get("nombre_dispositivo", ""),
                progreso=self.progreso.emit)
            self.terminado.emit(ruta)
        except Exception as e:
            self.fallo.emit(str(e))


# Los hilos del archivo que siguen vivos. Un QThread que Python suelta
# mientras trabaja tumba el programa («Destroyed while thread is still
# running»): aquí se guardan hasta que la ventana los da por terminados.
VIVOS: set = set()


def soltar_hilo(hilo) -> None:
    VIVOS.discard(hilo)


class HiloArchivo(QThread):
    """El archivo del cliente tras exportar (un PDF por factura, la copia del
    Excel y el expediente), sin parar la ventana: con 800 líneas eran 19 s
    sin responder. `trabajo` es un ventana_archivo.ArchivoExportacion: lo que
    haya que contar, y el fallo si lo hay, quedan en él para avisarlo."""
    progreso = Signal(str)        # cómo va, para la barra de estado
    hecho = Signal(object)        # este mismo hilo, al acabar

    def __init__(self, trabajo):
        super().__init__()
        self.trabajo = trabajo
        VIVOS.add(self)

    def run(self):
        try:
            self.trabajo.hacer(self.progreso.emit)
        except Exception as error:  # noqa: se apunta y se avisa al terminar
            self.trabajo.error = error
            self.trabajo.detalle = traceback.format_exc()
        self.hecho.emit(self)


class HiloActualizacion(QThread):
    resultado = Signal(object)   # Actualizacion o None
    error = Signal(str)

    def run(self):
        try:
            self.resultado.emit(updater.comprobar())
        except Exception as e:  # sin red, API caida, etc.
            self.error.emit(str(e))


class HiloDescargaActualizacion(QThread):
    progreso = Signal(int)
    terminado = Signal(str)
    error = Signal(str)

    def __init__(self, actualizacion):
        super().__init__()
        self.actualizacion = actualizacion

    def run(self):
        try:
            ruta = updater.descargar(
                self.actualizacion, progreso=self.progreso.emit)
            self.terminado.emit(ruta)
        except Exception as e:
            self.error.emit(str(e))


class HiloLocalizar(QObject):
    """Pide a Gemini dónde está cada dato en varias hojas, sin parar la mesa.

    Va en un hilo de Python «de fondo» (daemon), no en un QThread: se pone en
    marcha solo al acabar de leer y una consulta puede tardar; si se cierra el
    programa a mitad, no hay que esperarla ni puede tumbar el cierre.
    """
    hecho = Signal(str, object)     # clave de la imagen, [Caja]
    gasto = Signal(str, float)      # modelo, coste de todas las consultas
    terminado = Signal(int, int)    # hojas señaladas, hojas que fallaron

    def __init__(self, api_key, modelo, trabajos):
        super().__init__()
        self.api_key = api_key
        self.modelo = modelo
        self.trabajos = list(trabajos)   # [(clave, imagen, peticiones)]
        self.cancelado = False
        self._hilo = None

    def start(self):
        import threading
        self._hilo = threading.Thread(target=self.run, daemon=True,
                                      name="localizar-datos")
        self._hilo.start()

    def isRunning(self) -> bool:
        return bool(self._hilo and self._hilo.is_alive())

    def wait(self, milisegundos: int = 0) -> bool:
        if self._hilo:
            self._hilo.join(milisegundos / 1000 if milisegundos else None)
        return not self.isRunning()

    def cancelar(self):
        self.cancelado = True

    def run(self):
        from concurrent.futures import ThreadPoolExecutor
        from facturas_excel import localizar
        consumo, bien, mal = [], 0, 0

        def tarea(trabajo):
            if self.cancelado:
                raise RuntimeError("cancelado")
            clave, img, lista = trabajo
            # La imagen se lee del disco aquí, fuera de la ventana. Si ya no
            # está (se borraron los ejemplos), esa hoja no se puede señalar.
            img = imagen_hoja.como_bytes(img)
            if not img:
                raise FileNotFoundError("la imagen de la hoja ya no está")
            return clave, localizar.pedir(self.api_key, self.modelo, img, lista)

        ex = ThreadPoolExecutor(max_workers=min(4, hilos_lectura()))
        try:
            for futuro in [ex.submit(tarea, t) for t in self.trabajos]:
                try:
                    clave, (cajas, consumos) = futuro.result()
                except Exception:   # una hoja que no se localiza no importa
                    mal += 1
                    continue
                consumo.extend(consumos)
                bien += 1
                if not self.cancelado:
                    self.hecho.emit(clave, cajas)
        finally:
            ex.shutdown(wait=not self.cancelado, cancel_futures=True)
            # Lo pedido ya no hace falta: no se queda retenido con el hilo.
            self.trabajos = []
        coste = sum(costes.registrar(m, e, s, facturas=0) for m, e, s in consumo)
        if self.cancelado:
            return
        if consumo:
            self.gasto.emit(consumo[0][0], round(coste, 6))
        self.terminado.emit(bien, mal)
