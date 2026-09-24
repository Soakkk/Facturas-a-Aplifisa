"""Facturas ya exportadas a Aplifisa, por cliente.

La deteccion de duplicados solo miraba el lote cargado. Una factura escaneada
en dos trimestres, o un lote exportado dos veces tras «Vaciar todo», entraba
dos veces en la contabilidad sin ningun aviso. Aqui se guarda cada factura que
sale en un Excel verificado (NIF de la contraparte + numero + fecha + tipo),
para señalarla si vuelve a aparecer.

%APPDATA%\\FacturasAplifisa\\facturas_exportadas.json
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Dict, Iterable, Optional

from .rutas import dir_datos

_FICHERO = "facturas_exportadas.json"


def _ruta() -> str:
    return os.path.join(dir_datos(), _FICHERO)


def _nif(valor) -> str:
    return re.sub(r"[\s.\-]+", "", str(valor or "")).upper()


def _numero(valor) -> str:
    return "".join(c for c in str(valor or "") if c.isalnum()).upper()


def clave(f, tipo: str) -> Optional[str]:
    """Identidad de una factura para el historial, o None si no se puede fijar.

    Sin numero o sin fecha legible no es seguro: dos tickets distintos del
    mismo dia se confundirian.
    """
    from .validacion import fecha_de
    numero = _numero(f.num_factura)
    dia = fecha_de(f.fecha) if f.fecha else None
    if not numero or not dia:
        return None
    lado = "venta" if tipo in ("venta", "ingreso") else "gasto"
    return f"{lado}|{_nif(f.nif)}|{numero}|{dia.isoformat()}"


def _cliente(cliente_nif: str, cliente_nombre: str = "") -> str:
    return _nif(cliente_nif) or f"NOMBRE:{str(cliente_nombre).strip().upper()}"


_cache: dict = {"mtime": None, "datos": None}


def _leer() -> dict:
    try:
        mtime = os.path.getmtime(_ruta())
    except OSError:
        return {"version": 1, "clientes": {}}
    if _cache["mtime"] == mtime and _cache["datos"] is not None:
        return _cache["datos"]
    try:
        with open(_ruta(), encoding="utf-8") as fh:
            datos = json.load(fh)
        if not isinstance(datos, dict) or not isinstance(datos.get("clientes"), dict):
            datos = {"version": 1, "clientes": {}}
    except (OSError, ValueError):
        datos = {"version": 1, "clientes": {}}
    _cache.update(mtime=mtime, datos=datos)
    return datos


def _guardar(datos: dict) -> None:
    ruta = _ruta()
    temporal = ruta + ".tmp"
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(temporal, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, indent=1, ensure_ascii=False)
    os.replace(temporal, ruta)
    _cache.update(mtime=None, datos=None)


def buscar(cliente_nif: str, f, tipo: str, cliente_nombre: str = "") -> Optional[dict]:
    """Datos de la exportacion anterior de esta factura, o None."""
    k = clave(f, tipo)
    if not k:
        return None
    return _leer()["clientes"].get(_cliente(cliente_nif, cliente_nombre), {}).get(k)


def registrar(cliente_nif: str, facturas_por_tipo: Dict[str, Iterable],
              archivos: Dict[str, str], cliente_nombre: str = "",
              cuando: Optional[datetime] = None) -> int:
    """Apunta las facturas que acaban de salir en un Excel verificado."""
    datos = _leer()
    datos = json.loads(json.dumps(datos))
    del_cliente = datos["clientes"].setdefault(_cliente(cliente_nif, cliente_nombre), {})
    momento = (cuando or datetime.now()).strftime("%d/%m/%Y %H:%M")
    nuevas = 0
    for tipo, facturas in facturas_por_tipo.items():
        for f in facturas:
            k = clave(f, tipo)
            if not k:
                continue
            if k not in del_cliente:
                nuevas += 1
            del_cliente[k] = {
                "exportada": momento,
                "archivo": os.path.basename(archivos.get(tipo, "")),
                "num_factura": f.num_factura, "nombre": f.nombre,
                "total": f.total_impreso,
            }
    try:
        _guardar(datos)
    except OSError:
        return 0
    return nuevas


def olvidar(cliente_nif: str, facturas_por_tipo: Dict[str, Iterable],
            cliente_nombre: str = "") -> int:
    """Quita del historial esas facturas (p. ej. si Aplifisa rechazo el Excel)."""
    datos = json.loads(json.dumps(_leer()))
    del_cliente = datos["clientes"].get(_cliente(cliente_nif, cliente_nombre), {})
    quitadas = 0
    for tipo, facturas in facturas_por_tipo.items():
        for f in facturas:
            k = clave(f, tipo)
            if k and del_cliente.pop(k, None) is not None:
                quitadas += 1
    if quitadas:
        try:
            _guardar(datos)
        except OSError:
            return 0
    return quitadas


def texto_aviso(info: dict) -> str:
    archivo = f" en {info['archivo']}" if info.get("archivo") else ""
    return (f"YA EXPORTADA el {info.get('exportada', '?')}{archivo}: esta "
            "factura ya salió hacia Aplifisa en otro lote. Si la vuelve a "
            "importar, quedará registrada dos veces.")
