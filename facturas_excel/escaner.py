"""Escaneo directo desde el programa, con el escaner de Windows (WIA).

El programa ES el escaner: se pulsa Escanear, el alimentador traga el taco de
facturas, se arma un PDF con nombre de cliente y tipo (gastos/ingresos), se
guarda en su carpeta y entra solo en el lote. Sin abrir la app del fabricante
ni tener que buscar donde ha dejado el archivo.

WIA viene de serie en Windows y ve la multifuncion sin instalar nada aparte
(solo hace falta pywin32 para hablar con el COM). El PDF se arma con PyMuPDF,
que ya se usa para leer los PDF.
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import date
from typing import Callable, List, Optional, Tuple

# --- Constantes de WIA (las de la documentacion de Microsoft) ---
TIPO_ESCANER = 1

P_MANEJO_PAPEL = 3088       # WIA_DPS_DOCUMENT_HANDLING_SELECT
P_ESTADO_PAPEL = 3087       # WIA_DPS_DOCUMENT_HANDLING_STATUS
P_PAGINAS = 3096            # WIA_DPS_PAGES
ALIMENTADOR = 0x001
CRISTAL = 0x002
DUPLEX = 0x004
PAPEL_LISTO = 0x001         # FEED_READY

P_RES_H, P_RES_V = 6147, 6148
P_INI_H, P_INI_V = 6149, 6150
P_ANCHO, P_ALTO = 6151, 6152
P_TIPO_DATO = 4103          # 0=B/N, 2=grises, 3=color
COLOR, GRISES = 3, 2

# Formatos de imagen de WIA. OJO: muchos escaneres (la HP M148 entre ellos)
# SOLO entregan BMP; pedirles JPEG da "El parametro no es correcto". Se pide lo
# que cada aparato diga que sabe dar y se convierte despues.
FORMATO_JPEG = "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}"
FORMATO_BMP = "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"
FORMATO_PNG = "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}"
EXTENSION = {FORMATO_JPEG: "jpg", FORMATO_BMP: "bmp", FORMATO_PNG: "png"}

# Como describe WIA lo que admite cada propiedad.
SUBTIPO_RANGO, SUBTIPO_LISTA = 1, 2

# Sin papel en el alimentador: es el final normal de un taco, no un fallo.
HRESULT_SIN_PAPEL = (0x80210003, 0x80210002)

DPI_POR_DEFECTO = 200       # suficiente para leer facturas sin inflar el PDF
A4_PULGADAS = (8.27, 11.69)
MAX_PAGINAS = 200           # tope de seguridad por si el alimentador se atasca


class SinEscaner(Exception):
    """No hay ningun escaner disponible en el equipo."""


class ErrorEscaneo(Exception):
    """El escaneo no se pudo completar (papel, cable, driver...)."""


# ---------------------------------------------------------------- nombres
def sanear(texto: str) -> str:
    """Nombre de archivo/carpeta valido en Windows a partir de lo que sea."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r'[<>:"/\\|?*]', " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip(" .")
    return texto[:60] or "Sin nombre"


def ruta_destino(carpeta_base: str, cliente: str, tipo: str,
                 dia: Optional[date] = None) -> str:
    """Carpeta del cliente y nombre con cliente, tipo y fecha, sin pisar nada.

    <base>\\<CLIENTE>\\<CLIENTE>_<gastos|ingresos>_<aaaa-mm-dd>[_2].pdf
    """
    cliente = sanear(cliente or "Cliente sin identificar")
    tipo = "ingresos" if str(tipo).lower().startswith("i") else "gastos"
    dia = dia or date.today()
    return nombre_libre(os.path.join(carpeta_base, cliente),
                        f"{cliente}_{tipo}_{dia:%Y-%m-%d}")


def nombre_libre(carpeta: str, base: str) -> str:
    """`carpeta/base.pdf`, numerado si ya existe (no se pisa nada)."""
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, f"{base}.pdf")
    n = 2
    while os.path.exists(ruta):
        ruta = os.path.join(carpeta, f"{base}_{n}.pdf")
        n += 1
    return ruta


def carpeta_por_defecto() -> str:
    return os.path.join(os.path.expanduser("~"), "Documents", "Facturas escaneadas")


# ---------------------------------------------------------------- WIA
def _gestor():
    try:
        import win32com.client  # noqa: import diferido (solo Windows)
    except ImportError as e:  # pragma: no cover - en Windows siempre esta
        raise SinEscaner(
            "Falta el componente de Windows para escanear (pywin32).") from e
    return win32com.client.Dispatch("WIA.DeviceManager")


def escaneres() -> List[Tuple[str, str]]:
    """Escaneres disponibles: [(id, nombre)]. Lista vacia si no hay ninguno."""
    try:
        gestor = _gestor()
    except SinEscaner:
        return []
    encontrados = []
    for info in gestor.DeviceInfos:
        try:
            if info.Type != TIPO_ESCANER:
                continue
            nombre = ""
            for prop in info.Properties:
                if prop.Name == "Name":
                    nombre = str(prop.Value)
                    break
            encontrados.append((info.DeviceID, nombre or info.DeviceID))
        except Exception:  # un dispositivo raro no debe ocultar los demas
            continue
    return encontrados


def _conectar(device_id: Optional[str]):
    gestor = _gestor()
    disponibles = escaneres()
    if not disponibles:
        raise SinEscaner(
            "Windows no ve ningún escáner. Compruebe que la impresora está "
            "encendida y conectada.")
    if not device_id or device_id not in [i for i, _ in disponibles]:
        device_id = disponibles[0][0]
    for info in gestor.DeviceInfos:
        if info.DeviceID == device_id:
            return info.Connect()
    raise SinEscaner("No se pudo conectar con el escáner elegido.")


def _ajustar(prop, valor):
    """El valor mas parecido que admita esa propiedad.

    Cada escaner tiene sus limites (la HP solo hace 75/150/200/300 ppp y no
    pasa de 1700x3000 puntos). Colar un valor fuera de rango no da un aviso:
    revienta el escaneo entero con "El parametro no es correcto".
    """
    try:
        subtipo = prop.SubType
        if subtipo == SUBTIPO_RANGO:
            return min(max(valor, prop.SubTypeMin), prop.SubTypeMax)
        if subtipo == SUBTIPO_LISTA:
            opciones = [v for v in prop.SubTypeValues]
            if opciones and valor not in opciones:
                return min(opciones, key=lambda v: abs(v - valor))
    except Exception:
        pass
    return valor


def _poner(propiedades, prop_id, valor) -> bool:
    """Cambia una propiedad WIA si el aparato la admite (muchos no admiten
    todas, y ponerse tozudo con una sola aborta el escaneo entero)."""
    try:
        for prop in propiedades:
            if prop.PropertyID == prop_id:
                prop.Value = _ajustar(prop, valor)
                return True
    except Exception:
        pass
    return False


def _formato_de(item) -> str:
    """Formato en el que este escaner sabe entregar la imagen."""
    try:
        formatos = [str(f).upper() for f in item.Formats]
    except Exception:
        formatos = []
    for candidato in (FORMATO_JPEG, FORMATO_BMP, FORMATO_PNG):
        if candidato.upper() in formatos:
            return candidato
    return formatos[0] if formatos else FORMATO_BMP


def _a_jpeg(ruta: str) -> str:
    """Convierte a JPEG lo que no lo sea (un BMP de A4 a 200 ppp son 10 MB:
    un taco de 30 hojas dejaria un PDF imposible de mandar)."""
    if ruta.lower().endswith((".jpg", ".jpeg")):
        return ruta
    try:
        from PIL import Image
        destino = os.path.splitext(ruta)[0] + ".jpg"
        with Image.open(ruta) as imagen:
            imagen.convert("RGB").save(destino, "JPEG", quality=80, optimize=True)
        os.remove(ruta)
        return destino
    except Exception:
        return ruta          # peor es quedarse sin la hoja


def _preparar(dispositivo, dpi: int, alimentador: bool, duplex: bool,
              color: bool):
    modo = (ALIMENTADOR | (DUPLEX if duplex else 0)) if alimentador else CRISTAL
    _poner(dispositivo.Properties, P_MANEJO_PAPEL, modo)
    if alimentador:
        _poner(dispositivo.Properties, P_PAGINAS, 0)   # 0 = hasta vaciarlo
    item = dispositivo.Items[1]
    _poner(item.Properties, P_TIPO_DATO, COLOR if color else GRISES)
    _poner(item.Properties, P_RES_H, dpi)
    _poner(item.Properties, P_RES_V, dpi)
    _poner(item.Properties, P_INI_H, 0)
    _poner(item.Properties, P_INI_V, 0)
    # Los margenes se piden en puntos a esa resolucion, y _ajustar los recorta
    # a lo que de el aparato (a 300 ppp un A4 se sale del maximo de la HP).
    _poner(item.Properties, P_ANCHO, int(A4_PULGADAS[0] * dpi))
    _poner(item.Properties, P_ALTO, int(A4_PULGADAS[1] * dpi))
    return item


def _hay_papel(dispositivo) -> Optional[bool]:
    """True/False si el aparato lo sabe decir; None si no informa."""
    try:
        for prop in dispositivo.Properties:
            if prop.PropertyID == P_ESTADO_PAPEL:
                return bool(int(prop.Value) & PAPEL_LISTO)
    except Exception:
        pass
    return None


def _es_sin_papel(error) -> bool:
    """El alimentador se ha vaciado: fin normal del taco."""
    codigos = [getattr(error, "hresult", None)]
    args = getattr(error, "args", None) or []
    codigos += [a for a in args if isinstance(a, int)]
    detalle = args[2] if len(args) > 2 and isinstance(args[2], tuple) else ()
    codigos += [a for a in detalle if isinstance(a, int)]
    return any((c or 0) & 0xFFFFFFFF in HRESULT_SIN_PAPEL for c in codigos)


def capturar_paginas(dispositivo, carpeta_temporal: str, dpi: int = DPI_POR_DEFECTO,
                     alimentador: bool = True, duplex: bool = False,
                     color: bool = True,
                     progreso: Optional[Callable[[int], None]] = None) -> List[str]:
    """Pasa el taco entero y devuelve las rutas de las paginas (JPEG).

    Se separa de `escanear` para poder probarla con un escaner de mentira.
    """
    if alimentador and _hay_papel(dispositivo) is False:
        raise ErrorEscaneo(
            "El alimentador está vacío: ponga las facturas en la bandeja de "
            "arriba y vuelva a intentarlo.")
    item = _preparar(dispositivo, dpi, alimentador, duplex, color)
    formato = _formato_de(item)
    extension = EXTENSION.get(formato, "bmp")
    paginas: List[str] = []
    while len(paginas) < MAX_PAGINAS:
        try:
            imagen = item.Transfer(formato)
        except Exception as e:
            if paginas and _es_sin_papel(e):
                break            # se acabo el taco: normal
            if paginas:
                raise ErrorEscaneo(
                    f"Se escanearon {len(paginas)} hoja(s) y el escáner falló "
                    f"en la siguiente: {e}") from e
            raise ErrorEscaneo(f"No se pudo escanear: {e}") from e
        ruta = os.path.join(carpeta_temporal,
                            f"pag_{len(paginas) + 1:03d}.{extension}")
        imagen.SaveFile(ruta)
        paginas.append(_a_jpeg(ruta))
        if progreso:
            progreso(len(paginas))
        if not alimentador:
            break                # cristal: una hoja por escaneo
    if not paginas:
        raise ErrorEscaneo("No se escaneó ninguna hoja.")
    return paginas


def armar_pdf(paginas: List[str], destino: str) -> str:
    """Junta las imagenes escaneadas en un PDF (una pagina por hoja)."""
    import fitz  # PyMuPDF, ya se usa para leer los PDF

    documento = fitz.open()
    try:
        for ruta in paginas:
            with fitz.open(ruta) as imagen:
                documento.insert_pdf(fitz.open("pdf", imagen.convert_to_pdf()))
        os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
        documento.save(destino)
    finally:
        documento.close()
    return destino


def escanear(destino: str, device_id: Optional[str] = None,
             dpi: int = DPI_POR_DEFECTO, alimentador: bool = True,
             duplex: bool = False, color: bool = True,
             progreso: Optional[Callable[[int], None]] = None) -> str:
    """Escanea el taco y deja el PDF en `destino`. Devuelve la ruta."""
    import tempfile

    try:
        import pythoncom
        pythoncom.CoInitialize()   # el escaneo va en su propio hilo
    except Exception:
        pass
    dispositivo = _conectar(device_id)
    with tempfile.TemporaryDirectory(prefix="escaneo_") as tmp:
        paginas = capturar_paginas(dispositivo, tmp, dpi, alimentador, duplex,
                                   color, progreso)
        return armar_pdf(paginas, destino)
