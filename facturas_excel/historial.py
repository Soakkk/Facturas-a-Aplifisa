"""Facturas ya exportadas a Aplifisa, por cliente.

La deteccion de duplicados solo miraba el lote cargado. Una factura escaneada
en dos trimestres, o un lote exportado dos veces tras «Vaciar todo», entraba
dos veces en la contabilidad sin ningun aviso. Cada factura que sale en un
Excel verificado queda apuntada (NIF de la contraparte + numero + fecha +
tipo) para señalarla si vuelve a aparecer.

Desde la 1.17 esto vive en el registro de facturas (registro_facturas.py),
que guarda ademas el recorrido completo y el PDF de cada una. Este modulo se
mantiene con los mismos nombres para quien ya lo usaba.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, Optional

from . import registro_facturas as _registro

clave = _registro.clave
buscar = _registro.buscar
olvidar = _registro.olvidar
del_ejercicio = _registro.del_ejercicio
exportadas_de = _registro.exportadas_de


def registrar(cliente_nif: str, facturas_por_tipo: Dict[str, Iterable],
              archivos: Dict[str, str], cliente_nombre: str = "",
              cuando: Optional[datetime] = None, leidas_en: Optional[dict] = None) -> int:
    """Apunta las facturas que acaban de salir en un Excel verificado."""
    return _registro.exportar(cliente_nif, facturas_por_tipo, archivos,
                              cliente_nombre, cuando, leidas_en)


def texto_aviso(info: dict) -> str:
    archivo = f" en {info['archivo']}" if info.get("archivo") else ""
    return (f"YA EXPORTADA el {info.get('exportada', '?')}{archivo}: esta "
            "factura ya salió hacia Aplifisa en otro lote. Si la vuelve a "
            "importar, quedará registrada dos veces.")
