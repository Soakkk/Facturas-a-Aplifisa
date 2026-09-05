"""Los PDF que va generando el escaneo: donde estan y que hacer con ellos.

Al escanear no siempre se sabe de quien son las facturas (el programa lo
averigua despues, por el NIF que se repite). Por eso un escaneo puede nacer
"sin identificar" y mudarse a la carpeta de su cliente en cuanto se sabe.

Nada se borra de verdad: lo que se quita va a una papelera dentro de la propia
carpeta de escaneos, por si acaso.
"""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

from . import ajustes
from .escaner import carpeta_por_defecto, nombre_libre, ruta_destino, sanear

SIN_IDENTIFICAR = "Sin identificar"
PAPELERA = "_Papelera"


def carpeta_escaneos() -> str:
    ruta = ajustes.leer("carpeta_escaneos", carpeta_por_defecto())
    os.makedirs(ruta, exist_ok=True)
    return ruta


def ruta_provisional(carpeta_base: str, tipo: str,
                     dia: Optional[date] = None) -> str:
    """Sitio para un escaneo del que aun no se sabe el cliente."""
    tipo = "ingresos" if str(tipo).lower().startswith("i") else "gastos"
    dia = dia or date.today()
    return nombre_libre(os.path.join(carpeta_base, SIN_IDENTIFICAR),
                        f"Escaneo_{tipo}_{dia:%Y-%m-%d}")


def sin_identificar(ruta: str) -> bool:
    partes = os.path.normpath(ruta).split(os.sep)
    return SIN_IDENTIFICAR in partes


def mover_a_cliente(ruta: str, cliente: str, tipo: str = "gastos",
                    dia: Optional[date] = None,
                    ejercicio: Optional[int] = None) -> str:
    """Muda el PDF a la carpeta del cliente con su nombre bueno.

    Devuelve la ruta nueva; si algo falla (el archivo esta abierto en otro
    programa, por ejemplo) devuelve la de antes: mover el archivo NUNCA debe
    costar el escaneo.
    """
    if not cliente or not os.path.exists(ruta):
        return ruta
    dia = dia or _fecha_de_archivo(ruta)
    ejercicio = int(ejercicio or dia.year)
    cliente_limpio = sanear(cliente)
    tipo_limpio = "ingresos" if str(tipo).lower().startswith("i") else "gastos"
    carpeta_tipo = "Ingresos" if tipo_limpio == "ingresos" else "Gastos"
    carpeta_final = os.path.join(_base_de(ruta), cliente_limpio,
                                 str(ejercicio), carpeta_tipo)
    if (os.path.normcase(os.path.dirname(os.path.abspath(ruta)))
            == os.path.normcase(os.path.abspath(carpeta_final))
            and os.path.basename(ruta).lower().startswith(
                f"{cliente_limpio}_{tipo_limpio}_{dia:%Y-%m-%d}".lower())):
        return ruta
    destino = ruta_destino(_base_de(ruta), cliente_limpio, tipo_limpio,
                           dia, ejercicio)
    if os.path.normcase(destino) == os.path.normcase(ruta):
        return ruta
    try:
        shutil.move(ruta, destino)
    except OSError:
        return ruta
    _limpiar_si_vacia(os.path.dirname(ruta))
    return destino


def carpeta_tipo_cliente(cliente: str, ejercicio: int, tipo: str,
                         carpeta_base: Optional[str] = None) -> str:
    """Carpeta documental estable: Cliente/Ejercicio/Gastos|Ingresos."""
    base = carpeta_base or carpeta_escaneos()
    cliente_limpio = sanear(cliente or "Cliente sin identificar")
    carpeta_tipo = ("Ingresos" if str(tipo).lower().startswith(("i", "v"))
                    else "Gastos")
    carpeta_ejercicio = os.path.join(base, cliente_limpio, str(int(ejercicio)))
    # Cada ejercicio queda preparado para reunir toda la documentación.
    for nombre in ("Ingresos", "Gastos"):
        os.makedirs(os.path.join(carpeta_ejercicio, nombre), exist_ok=True)
    return os.path.join(carpeta_ejercicio, carpeta_tipo)


def copiar_a_cliente(ruta: str, cliente: str, tipo: str = "gastos",
                     ejercicio: Optional[int] = None) -> str:
    """Copia un PDF externo al archivo documental sin tocar el original.

    Es el camino de los PDF creados con HP u otro programa. A diferencia de un
    escaneo provisional de la propia app, el archivo elegido por el usuario no
    se mueve ni se renombra en su ubicación de origen.
    """
    if not cliente or not os.path.isfile(ruta) or not ruta.lower().endswith(".pdf"):
        return ruta
    ejercicio = int(ejercicio or _fecha_de_archivo(ruta).year)
    carpeta = carpeta_tipo_cliente(cliente, ejercicio, tipo)
    if (os.path.normcase(os.path.dirname(os.path.abspath(ruta)))
            == os.path.normcase(os.path.abspath(carpeta))):
        return ruta
    base = sanear(os.path.splitext(os.path.basename(ruta))[0])
    destino = nombre_libre(carpeta, base)
    try:
        shutil.copy2(ruta, destino)
        return destino
    except OSError:
        return ruta


def ruta_excel_consolidado(cliente: str, ejercicio: int, tipo: str,
                           carpeta_base: Optional[str] = None) -> str:
    """Nombre libre para el Excel final, junto a sus PDF originales."""
    carpeta = carpeta_tipo_cliente(cliente, ejercicio, tipo, carpeta_base)
    cliente_limpio = sanear(cliente or "Cliente")
    tipo_limpio = "ingresos" if str(tipo).lower().startswith(("i", "v")) else "gastos"
    base = f"{cliente_limpio}_{int(ejercicio)}_{tipo_limpio}_consolidado"
    ruta = os.path.join(carpeta, base + ".xlsx")
    numero = 2
    while os.path.exists(ruta):
        ruta = os.path.join(carpeta, f"{base}_{numero}.xlsx")
        numero += 1
    return ruta


def _base_de(ruta: str) -> str:
    """Carpeta de escaneos a la que pertenece un PDF.

    Lo normal es que este dentro de la carpeta configurada; si el usuario lo ha
    movido a otro sitio, se usa la carpeta de su carpeta (esta en la de un
    cliente).
    """
    base = carpeta_escaneos()
    ruta_abs = os.path.normcase(os.path.abspath(ruta))
    if ruta_abs.startswith(os.path.normcase(os.path.abspath(base)) + os.sep):
        return base
    return os.path.dirname(os.path.dirname(ruta))


def _fecha_de_archivo(ruta: str) -> date:
    """La fecha que lleva el propio nombre (es la del escaneo); si no la lleva,
    la del archivo. Asi renombrar o mover un PDF no le cambia la fecha."""
    encaje = re.search(r"(\d{4})-(\d{2})-(\d{2})", os.path.basename(ruta))
    if encaje:
        try:
            return date(*(int(g) for g in encaje.groups()))
        except ValueError:
            pass
    try:
        return datetime.fromtimestamp(os.path.getmtime(ruta)).date()
    except OSError:
        return date.today()


def _limpiar_si_vacia(carpeta: str) -> None:
    """Recoge hacia arriba las carpetas vacías hasta la raíz configurada."""
    limite = os.path.normcase(os.path.abspath(carpeta_escaneos()))
    try:
        actual = os.path.abspath(carpeta)
        while (os.path.normcase(actual) != limite
               and os.path.normcase(actual).startswith(limite + os.sep)
               and os.path.isdir(actual) and not os.listdir(actual)):
            os.rmdir(actual)
            actual = os.path.dirname(actual)
    except OSError:
        pass


@dataclass
class Escaneo:
    ruta: str
    cliente: str
    nombre: str
    fecha: date
    tamano: int          # bytes
    ejercicio: Optional[int] = None
    tipo: str = ""

    @property
    def tamano_texto(self) -> str:
        mb = self.tamano / (1024 * 1024)
        if mb >= 1:
            return f"{mb:.1f} MB".replace(".", ",")
        return f"{max(1, round(self.tamano / 1024))} KB"


def listar(carpeta_base: Optional[str] = None) -> List[Escaneo]:
    """Todos los PDF escaneados, del mas nuevo al mas viejo. La papelera no."""
    base = carpeta_base or carpeta_escaneos()
    encontrados: List[Escaneo] = []
    for raiz, carpetas, archivos in os.walk(base):
        carpetas[:] = [c for c in carpetas if c != PAPELERA]
        for archivo in archivos:
            if not archivo.lower().endswith(".pdf"):
                continue
            ruta = os.path.join(raiz, archivo)
            relativo = os.path.relpath(raiz, base)
            partes = [] if relativo == "." else relativo.split(os.sep)
            cliente = partes[0] if partes else "—"
            ejercicio = (int(partes[1]) if len(partes) >= 2
                         and partes[1].isdigit() else None)
            tipo = (partes[2].lower() if len(partes) >= 3
                    and partes[2].lower() in {"gastos", "ingresos"}
                    else _tipo_de_nombre(ruta))
            try:
                tamano = os.path.getsize(ruta)
            except OSError:
                continue
            encontrados.append(Escaneo(
                ruta=ruta,
                cliente=cliente if os.path.normcase(raiz) != os.path.normcase(base) else "—",
                nombre=archivo,
                fecha=_fecha_de_archivo(ruta),
                tamano=tamano,
                ejercicio=ejercicio,
                tipo=tipo))
    return sorted(encontrados, key=lambda e: (e.fecha, e.nombre), reverse=True)


def a_papelera(ruta: str) -> str:
    """Quita un escaneo de en medio SIN borrarlo: se queda en _Papelera."""
    base = carpeta_escaneos()
    papelera = os.path.join(base, PAPELERA)
    os.makedirs(papelera, exist_ok=True)
    destino = os.path.join(papelera, os.path.basename(ruta))
    n = 2
    while os.path.exists(destino):
        raiz, ext = os.path.splitext(os.path.basename(ruta))
        destino = os.path.join(papelera, f"{raiz}_{n}{ext}")
        n += 1
    shutil.move(ruta, destino)
    _limpiar_si_vacia(os.path.dirname(ruta))
    return destino


def renombrar_cliente(ruta: str, cliente: str) -> str:
    """Corrige a mano de quien es un escaneo (se movio mal o se tecleo mal)."""
    return mover_a_cliente(ruta, sanear(cliente), _tipo_de_nombre(ruta),
                           ejercicio=_ejercicio_de_ruta(ruta))


def _ejercicio_de_ruta(ruta: str) -> Optional[int]:
    """Ejercicio ya presente en una ruta Cliente/Ejercicio/Tipo."""
    for parte in reversed(os.path.normpath(ruta).split(os.sep)[:-1]):
        if len(parte) == 4 and parte.isdigit():
            valor = int(parte)
            if 1900 <= valor <= 2200:
                return valor
    return None


def _tipo_de_nombre(ruta: str) -> str:
    return "ingresos" if "_ingresos_" in os.path.basename(ruta).lower() else "gastos"


def comprimir_ejercicio(carpeta_base: str, cliente: str, ejercicio: int) -> str:
    """Crea un ZIP con Ingresos y Gastos para adjuntarlo después en Aplifisa."""
    cliente = sanear(cliente)
    ejercicio = int(ejercicio)
    carpeta_cliente = os.path.join(carpeta_base, cliente)
    origen = os.path.join(carpeta_cliente, str(ejercicio))
    if not os.path.isdir(origen):
        raise ValueError(f"No existe el ejercicio {ejercicio} de {cliente}.")
    pdfs = []
    for tipo in ("Ingresos", "Gastos"):
        carpeta_tipo = os.path.join(origen, tipo)
        if not os.path.isdir(carpeta_tipo):
            continue
        pdfs.extend(os.path.join(carpeta_tipo, nombre)
                    for nombre in sorted(os.listdir(carpeta_tipo))
                    if nombre.lower().endswith(".pdf"))
    if not pdfs:
        raise ValueError("Ese ejercicio no contiene ningún PDF.")

    base_nombre = f"{cliente}_{ejercicio}_documentacion_digitalizada"
    destino = os.path.join(carpeta_cliente, base_nombre + ".zip")
    numero = 2
    while os.path.exists(destino):
        destino = os.path.join(carpeta_cliente, f"{base_nombre}_{numero}.zip")
        numero += 1
    temporal = destino + ".tmp"
    try:
        with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=6) as comprimido:
            comprimido.writestr("Ingresos/", "")
            comprimido.writestr("Gastos/", "")
            for pdf in pdfs:
                comprimido.write(pdf, os.path.relpath(pdf, origen))
        os.replace(temporal, destino)
    except Exception:
        try:
            if os.path.exists(temporal):
                os.remove(temporal)
        except OSError:
            pass
        raise
    return destino


def abrir(ruta: str) -> None:
    """Abre el PDF (o su carpeta) con lo que tenga puesto Windows."""
    try:
        os.startfile(ruta)  # noqa: solo Windows, que es donde corre esto
    except (OSError, AttributeError):
        pass
