"""Que modelo de Gemini se esta usando y cuanto cuesta.

La API de Gemini NO deja consultar el saldo de la cuenta (eso solo se ve en la
consola de Google), asi que el gasto se lleva aqui: cada respuesta dice cuantos
tokens ha gastado y con que modelo, y se multiplica por la tarifa. Se acumula
por meses y se compara con el tope que ponga el usuario, para que nunca haya
una sorpresa a fin de mes.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Dict, Optional, Tuple

from . import ajustes
from .rutas import dir_datos

# Tarifas de pago por uso, en DOLARES por millon de tokens (entrada, salida).
# Revisado el 2026-09-02 en https://ai.google.dev/gemini-api/docs/pricing
# OJO: 3.6/3.7 Flash estan en precio de lanzamiento hasta el 31/12/2026; a
# partir del 1/1/2027 pasan a 1,50 / 7,50 (el doble). Repasar la tabla entonces.
PRECIOS: Dict[str, Tuple[float, float]] = {
    "gemini-3.7-flash": (0.75, 3.75),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.30, 2.50),
    "gemini-3.1-pro": (2.00, 12.00),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.0-flash": (0.10, 0.40),
}
# Modelo que no esta en la tabla: se cobra como el Flash mas caro. Mejor
# pasarse en la cuenta que quedarse corto y pillarse los dedos con el tope.
PRECIO_DESCONOCIDO = (0.75, 3.75)

EUROS_POR_DOLAR = 0.92     # aproximado; se puede afinar en ajustes.json
TOPE_POR_DEFECTO = 5.0     # euros al mes (el limite que tiene puesto en Google)

_FICHERO = "gasto.json"


def _ruta() -> str:
    return os.path.join(dir_datos(), _FICHERO)


def _normaliza(modelo: str) -> str:
    return str(modelo or "").lower().replace("models/", "").strip()


def precio_de(modelo: str) -> Tuple[Tuple[float, float], bool]:
    """(precio entrada, precio salida) y si es una tarifa conocida.

    Los nombres reales llevan cola ('gemini-3.7-flash-preview-11-2026'), asi
    que vale la clave mas larga que encaje por delante.
    """
    nombre = _normaliza(modelo)
    encajes = [k for k in PRECIOS if nombre.startswith(k)]
    if not encajes:
        return PRECIO_DESCONOCIDO, False
    return PRECIOS[max(encajes, key=len)], True


def euros_por_dolar() -> float:
    try:
        return float(ajustes.leer("euros_por_dolar", EUROS_POR_DOLAR))
    except (TypeError, ValueError):
        return EUROS_POR_DOLAR


def coste(modelo: str, tokens_entrada: int, tokens_salida: int) -> float:
    """Lo que cuesta en euros esa llamada."""
    (p_in, p_out), _ = precio_de(modelo)
    dolares = (tokens_entrada or 0) / 1e6 * p_in + (tokens_salida or 0) / 1e6 * p_out
    return round(dolares * euros_por_dolar(), 6)


# ------------------------------------------------------------------ almacen
def _leer() -> dict:
    try:
        with open(_ruta(), encoding="utf-8") as fh:
            datos = json.load(fh)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def _escribir(datos: dict) -> None:
    try:
        with open(_ruta(), "w", encoding="utf-8") as fh:
            json.dump(datos, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass  # no poder anotar el gasto no debe tumbar la app


def mes(dia: Optional[date] = None) -> str:
    return f"{dia or date.today():%Y-%m}"


def registrar(modelo: str, tokens_entrada: int, tokens_salida: int,
              facturas: int = 1, dia: Optional[date] = None) -> float:
    """Anota el gasto del mes y devuelve lo que ha costado esa llamada."""
    importe = coste(modelo, tokens_entrada, tokens_salida)
    datos = _leer()
    meses = datos.setdefault("meses", {})
    ficha = meses.setdefault(mes(dia), {"facturas": 0, "tokens_entrada": 0,
                                        "tokens_salida": 0, "coste": 0.0})
    ficha["facturas"] += facturas
    ficha["tokens_entrada"] += tokens_entrada or 0
    ficha["tokens_salida"] += tokens_salida or 0
    ficha["coste"] = round(ficha["coste"] + importe, 6)
    ficha["ultimo_modelo"] = _normaliza(modelo)
    _escribir(datos)
    return importe


def gasto_del_mes(dia: Optional[date] = None) -> float:
    return round(_leer().get("meses", {}).get(mes(dia), {}).get("coste", 0.0), 6)


def facturas_del_mes(dia: Optional[date] = None) -> int:
    return int(_leer().get("meses", {}).get(mes(dia), {}).get("facturas", 0))


def tope() -> float:
    try:
        return float(ajustes.leer("tope_mensual", TOPE_POR_DEFECTO))
    except (TypeError, ValueError):
        return TOPE_POR_DEFECTO


def guardar_tope(euros: float) -> None:
    ajustes.guardar("tope_mensual", round(float(euros), 2))


def porcentaje_gastado() -> float:
    limite = tope()
    return 0.0 if limite <= 0 else round(gasto_del_mes() / limite * 100, 1)


def _eur(v: float) -> str:
    """Importes pequeños: se enseñan con los decimales que hagan falta para
    que no salga siempre '0,00 €' (un lote entero cuesta centimos)."""
    if v and abs(v) < 0.01:
        return f"{v:.4f}".replace(".", ",") + " €"
    return f"{v:.2f}".replace(".", ",") + " €"


def resumen(modelo: str = "", coste_lote: float = 0.0) -> str:
    """La linea que ve el usuario: modelo, coste del lote y gasto del mes."""
    partes = []
    if modelo:
        (_, _), conocido = precio_de(modelo)
        partes.append(f"Modelo: {_normaliza(modelo)}"
                      + ("" if conocido else " (tarifa estimada)"))
    if coste_lote:
        partes.append(f"este lote {_eur(coste_lote)}")
    partes.append(f"mes: {_eur(gasto_del_mes())} de {_eur(tope())}")
    return "  ·  ".join(partes)


def aviso_tope() -> str:
    """Aviso cuando el gasto del mes se acerca al tope (vacio si va sobrado)."""
    pct = porcentaje_gastado()
    if pct >= 100:
        return (f"Ha superado el tope de gasto del mes ({_eur(tope())}). "
                f"Lleva {_eur(gasto_del_mes())}. Si Google tiene ese mismo "
                f"límite, las próximas facturas fallarán.")
    if pct >= 80:
        return (f"Lleva gastado el {pct:.0f} % del tope del mes "
                f"({_eur(gasto_del_mes())} de {_eur(tope())}).")
    return ""
