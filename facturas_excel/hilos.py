"""Trabajos en segundo plano: leer con Gemini, escanear y actualizar."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from facturas_excel import ajustes, costes, escaner, updater
from facturas_excel.extraccion import Extractor, SinCredito
from facturas_excel.pdf import cargar_imagenes
from facturas_excel.procesar import detectar_cliente, preparar_lote


HILOS = 10  # hojas leidas a la vez (con la clave de pago de Gemini)


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

    def run(self):
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            imagenes = cargar_imagenes(
                self.rutas, dpi=int(ajustes.leer('lectura_ppp', 150)))
            if not imagenes:
                raise ValueError("No se encontraron páginas o imágenes compatibles.")
            extractor = Extractor(self.api_key)
            total = len(imagenes)
            registros = [None] * total

            consumo = []   # (modelo, tokens entrada, tokens salida) por llamada
            sin_credito = []

            def tarea(idx):
                origen, pagina, img = imagenes[idx]
                if sin_credito:
                    # Se acabó el crédito en otra hoja: no se pide nada más.
                    return idx, (img, origen, pagina, {
                        "emisor_nombre": None, "lineas_iva": [{}],
                        "_error": "No leída: la API key se quedó sin crédito"})
                try:
                    leido = extractor.extraer(img, origen, pagina)
                    consumo.extend(leido.consumos or [(
                        leido.modelo, leido.tokens_entrada, leido.tokens_salida)])
                    datos = leido.crudo
                except SinCredito:
                    sin_credito.append(True)
                    raise  # detiene todo el lote con aviso
                except Exception as e:  # una factura ilegible no tumba el lote
                    # Lo pagado por los intentos fallidos también cuenta.
                    consumo.extend(getattr(e, "consumos", []) or [])
                    # Sin nombre inventado: la hoja queda vacía y en rojo, con
                    # el motivo, en lugar de un proveedor «(NO SE PUDO LEER)».
                    datos = {"emisor_nombre": None, "lineas_iva": [{}],
                             "_error": str(e)[:120]}
                    self.fallos.append((origen, pagina, str(e)[:120]))
                return idx, (img, origen, pagina, datos)

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
                # Si algo corta el lote (sin crédito), las hojas que aún no
                # han empezado se cancelan: no se sigue pagando por nada.
                ex.shutdown(wait=True, cancel_futures=True)
                self._registrar_consumo(consumo)

            nombre, nif = detectar_cliente([d for *_, d in registros])
            procesadas = preparar_lote(registros, nombre, nif)
            self.terminado.emit(procesadas, nombre, nif, registros)
        except Exception as e:  # noqa
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
        coste = sum(costes.registrar(m, e, s, facturas=0) for m, e, s in consumo)
        if self.cancelado:
            return
        if consumo:
            self.gasto.emit(consumo[0][0], round(coste, 6))
        self.terminado.emit(bien, mal)
