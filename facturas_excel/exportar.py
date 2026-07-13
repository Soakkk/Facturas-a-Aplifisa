"""Genera el archivo .xlsx en la maqueta exacta que espera el gestor fiscal,
colocando cada campo en la columna que indica la configuracion (ConfigColumnas).
"""

from __future__ import annotations

from typing import List

from openpyxl import Workbook
from openpyxl.utils import column_index_from_string

from .config_columnas import ConfigColumnas, ETIQUETA_CABECERA
from .modelo import CAMPOS_IMPORTE, CAMPOS_PORCENTAJE, Factura

# Modo en que se escriben los numeros en las celdas:
#   "texto"  -> "1234,56" como texto (separador decimal coma)
#   "numero" -> 1234.56 como numero real de Excel
MODO_TEXTO = "texto"
MODO_NUMERO = "numero"


def _fmt_importe_texto(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")


def _fmt_porcentaje_texto(valor: float) -> str:
    # 21.0 -> "21" ; 21.5 -> "21,5"
    if float(valor).is_integer():
        return str(int(valor))
    return f"{valor:g}".replace(".", ",")


def _valor_celda(campo: str, valor, modo: str):
    """Devuelve el valor listo para escribir en la celda segun el tipo de campo."""
    if valor is None or valor == "":
        return None

    # Aplifisa: el NIF de la cuenta no puede llevar puntos, espacios ni guiones.
    if campo == "nif":
        return str(valor).strip().upper().replace(".", "").replace(" ", "").replace("-", "")

    es_numerico = campo in CAMPOS_IMPORTE or campo in CAMPOS_PORCENTAJE
    if not es_numerico:
        return str(valor)

    valor = float(valor)
    if modo == MODO_NUMERO:
        return round(valor, 2)

    # modo texto
    if campo in CAMPOS_PORCENTAJE:
        return _fmt_porcentaje_texto(valor)
    return _fmt_importe_texto(valor)


def exportar_excel(
    facturas: List[Factura],
    config: ConfigColumnas,
    ruta_salida: str,
    modo_numeros: str = MODO_TEXTO,
) -> str:
    """Escribe el .xlsx y devuelve la ruta.

    - Fila 1: cabecera (si config.incluye_cabecera).
    - Datos desde config.primera_fila.
    - Cada campo va a la columna (letra) que diga config.columnas.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Facturas"

    # Cabecera
    if config.incluye_cabecera:
        for campo, letra in config.columnas.items():
            col = column_index_from_string(letra)
            ws.cell(row=1, column=col, value=ETIQUETA_CABECERA.get(campo, campo))

    # Datos
    fila = config.primera_fila
    for factura in facturas:
        datos = factura.campos_dict()
        for campo, letra in config.columnas.items():
            valor = _valor_celda(campo, datos.get(campo), modo_numeros)
            if valor is not None:
                col = column_index_from_string(letra)
                celda = ws.cell(row=fila, column=col, value=valor)
                # Forzar texto cuando toca, para que Excel no reinterprete la coma
                if modo_numeros == MODO_TEXTO and (
                    campo in CAMPOS_IMPORTE or campo in CAMPOS_PORCENTAJE
                ):
                    celda.number_format = "@"
        fila += 1

    wb.save(ruta_salida)
    return ruta_salida
