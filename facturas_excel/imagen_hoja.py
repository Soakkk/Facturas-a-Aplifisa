"""La imagen de lectura de cada hoja vive en disco, no en memoria.

Cada hoja que se lee se guarda en muestras_revision/imagenes/<huella>.jpg
(la muestra local de lo leído). Antes el lote se quedaba además con sus
bytes: con un PDF de 450 hojas eran 80 MB en memoria, y otros 80 en cada
guardado de la sesión, que se reescribía entera unas veinte veces. Ahora el
lote guarda un «asa» de unos cien bytes que dice cuál es la imagen, y se lee
del disco solo cuando hace falta: el visor al cambiar de hoja, o señalar los
datos en el documento.

Si la imagen ya no está en el disco (se borró la carpeta de ejemplos), el
asa da b"": la miniatura sale vacía, como con una imagen que no se puede
abrir, y nada se rompe. Las sesiones de versiones anteriores traen los
bytes: al abrirlas se pasan a disco con `Conversor`.

Aquí no se importa Qt.
"""

from __future__ import annotations

import hashlib

from . import muestras_revision


class ImagenHoja:
    """La imagen de una hoja guardada en las muestras (sin sus bytes)."""

    __slots__ = ("sha", "extension", "tam", "clave")

    def __init__(self, sha: str, extension: str, tam: int, clave: str):
        self.sha = sha              # SHA256: el nombre del fichero
        self.extension = extension  # ".jpg", ".png" o ".bin"
        self.tam = tam              # bytes de la imagen
        # SHA1 de los bytes: la clave con la que se guardan los recuadros
        # de «dónde está cada dato» (localizar.clave_imagen), también en las
        # sesiones de antes.
        self.clave = clave

    def ruta(self):
        return muestras_revision.carpeta() / "imagenes" / (self.sha + self.extension)

    def datos(self) -> bytes:
        """Los bytes de la imagen, o b"" si ya no está en el disco."""
        try:
            return self.ruta().read_bytes()
        except OSError:
            return b""

    def existe(self) -> bool:
        try:
            return self.ruta().is_file()
        except OSError:
            return False

    def __bytes__(self) -> bytes:
        return self.datos()

    def __bool__(self) -> bool:
        return self.tam > 0

    def __eq__(self, otra) -> bool:
        # Dos hojas son la misma si su imagen es la misma: igual que cuando
        # el lote comparaba los bytes.
        if isinstance(otra, ImagenHoja):
            return self.sha == otra.sha
        if isinstance(otra, (bytes, bytearray)):
            return (len(otra) == self.tam
                    and hashlib.sha256(otra).hexdigest() == self.sha)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.sha)

    def __reduce__(self):
        # En la sesión solo va esto: unos cien bytes por hoja.
        return (ImagenHoja, (self.sha, self.extension, self.tam, self.clave))

    def __repr__(self) -> str:
        return f"ImagenHoja({self.sha[:12]}{self.extension}, {self.tam} B)"


def a_disco(imagen: bytes) -> ImagenHoja:
    """Guarda la imagen en las muestras (si no estaba) y devuelve su asa.

    Lanza OSError si no se puede escribir: entonces el lote se queda con los
    bytes, como antes (ver `Conversor`)."""
    datos = bytes(imagen)
    sha, extension = muestras_revision.guardar_imagen(datos)
    return ImagenHoja(sha, extension, len(datos), hashlib.sha1(datos).hexdigest())


def como_bytes(imagen) -> bytes:
    """Los bytes de la imagen de una hoja, venga como asa o como bytes."""
    if isinstance(imagen, ImagenHoja):
        return imagen.datos()
    if isinstance(imagen, (bytes, bytearray)):
        return bytes(imagen)
    return b""


class Conversor:
    """Pasa a disco las imágenes de un lote, cada una una sola vez.

    La misma hoja está a la vez en lo leído (crudos), en lo procesado y en
    las filas: es el mismo objeto, y los tres se quedan con la misma asa. Si
    una imagen no se puede escribir, se queda en memoria con sus bytes (y
    se apunta el fallo): una muestra que no se guarda no puede costar la
    miniatura.
    """

    def __init__(self):
        # id(bytes) -> (bytes, asa): se guarda el objeto para que su id no
        # se reutilice mientras dura la conversión.
        self._hechas: dict = {}
        self.fallos: list = []

    def __call__(self, imagen):
        if not isinstance(imagen, (bytes, bytearray)) or not imagen:
            return imagen
        hecha = self._hechas.get(id(imagen))
        if hecha is not None:
            return hecha[1]
        try:
            asa = a_disco(imagen)
        except OSError as error:
            self.fallos.append(error)
            asa = imagen
        self._hechas[id(imagen)] = (imagen, asa)
        return asa

    def registros(self, registros) -> list:
        """(imagen, origen, página, datos) con la imagen ya en disco."""
        return [(self(r[0]), *r[1:]) for r in registros or []]

    def procesadas(self, procesadas) -> list:
        """(imagen, factura procesada) con la imagen ya en disco."""
        return [(self(imagen), pr) for imagen, pr in procesadas or []]

    def bloques(self, bloques) -> None:
        """Cambia, en su sitio, las imágenes de todos los bloques del lote."""
        for bloque in bloques or []:
            if bloque.get("procesadas"):
                bloque["procesadas"][:] = self.procesadas(bloque["procesadas"])
            if bloque.get("crudos"):
                bloque["crudos"][:] = self.registros(bloque["crudos"])
