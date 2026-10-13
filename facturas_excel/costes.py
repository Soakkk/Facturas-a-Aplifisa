"""Que modelo de Gemini se esta usando y cuanto cuesta.

La API de Gemini NO deja consultar el saldo de la cuenta (eso solo se ve en la
consola de Google), asi que el gasto se lleva aqui: cada respuesta dice cuantos
tokens ha gastado y con que modelo, y se multiplica por la tarifa. Se acumula
por meses y se compara con el tope que ponga el usuario, para que nunca haya
una sorpresa a fin de mes.
"""

from __future__ import annotations

import math
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
    # Claude (Anthropic), revisado el 2026-10-13. Lo que Claude ya tenia
    # guardado de la hoja anterior se cuenta aparte (ver
    # extraccion.RespuestaClaude): aqui va la tarifa normal.
    "claude-opus-5-5": (4.00, 20.00),
}
# gemini-3.8-flash no esta en la tabla a proposito: no se inventa su tarifa.
# Mientras no se escriba en Configuracion -> Modelos de lectura se estima con
# PRECIO_DESCONOCIDO y la barra lo indica con «(tarifa estimada)».
# Modelo que no esta en la tabla: se cobra como el Flash mas caro. Mejor
# pasarse en la cuenta que quedarse corto y pillarse los dedos con el tope.
PRECIO_DESCONOCIDO = (0.75, 3.75)

EUROS_POR_DOLAR = 0.92     # aproximado; se puede afinar en ajustes.json
# Euros al mes. Era 5 (el limite que tiene puesto en Google); el 13/10/2026,
# para probar la lectura con Claude, el usuario pidio 20 € (Claude + Gemini).
TOPE_POR_DEFECTO = 20.0
# Ese cambio a 20 € se aplica UNA vez al actualizar a la 1.27.0, aunque
# tuviera guardado otro; si despues lo cambia a mano, manda lo suyo.
_TOPE_1_27_APLICADO = "tope_20_euros_1_27"

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
    tabla = dict(PRECIOS)
    # Tarifas escritas por el usuario (Configuracion -> Modelos de lectura):
    # mandan sobre la tabla, para no tener que esperar a una actualizacion
    # cuando Google publica o cambia un precio.
    propias = ajustes.leer("precios_modelos", {}) or {}
    if isinstance(propias, dict):
        for clave, valor in propias.items():
            try:
                entrada, salida = (float(v) for v in valor)
            except (TypeError, ValueError):
                continue
            tabla[_normaliza(clave)] = (entrada, salida)
    encajes = [k for k in tabla if nombre.startswith(k)]
    if not encajes:
        return PRECIO_DESCONOCIDO, False
    return tabla[max(encajes, key=len)], True


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
def _col():
    """El gasto por meses, en la base de datos local (antes gasto.json)."""
    from .almacen import Coleccion
    return Coleccion("gasto", dir_datos(), legado=_ruta(),
                     convertir=lambda antiguo: {
                         k: v for k, v in (antiguo.get("meses") or {}).items()
                         if isinstance(v, dict)})


def _leer() -> dict:
    return {"meses": _col().leer_todo()}


def mes(dia: Optional[date] = None) -> str:
    return f"{dia or date.today():%Y-%m}"


def registrar(modelo: str, tokens_entrada: int, tokens_salida: int,
              facturas: int = 1, dia: Optional[date] = None) -> float:
    """Anota el gasto del mes y devuelve lo que ha costado esa llamada."""
    importe = coste(modelo, tokens_entrada, tokens_salida)
    def sumar(ficha):
        ficha = dict(ficha or {"facturas": 0, "tokens_entrada": 0,
                               "tokens_salida": 0, "coste": 0.0})
        ficha["facturas"] = ficha.get("facturas", 0) + facturas
        ficha["tokens_entrada"] = ficha.get("tokens_entrada", 0) + (tokens_entrada or 0)
        ficha["tokens_salida"] = ficha.get("tokens_salida", 0) + (tokens_salida or 0)
        ficha["coste"] = round(ficha.get("coste", 0.0) + importe, 6)
        ficha["ultimo_modelo"] = _normaliza(modelo)
        return ficha
    try:
        # Leer y sumar en la misma transacción: las hojas se leen a la vez
        # en varios hilos y ninguna suma debe pisar a otra.
        _col().modificar(mes(dia), sumar)
    except Exception:
        pass  # no poder anotar el gasto no debe tumbar la app
    return importe


def gasto_del_mes(dia: Optional[date] = None) -> float:
    return round(_leer().get("meses", {}).get(mes(dia), {}).get("coste", 0.0), 6)


def facturas_del_mes(dia: Optional[date] = None) -> int:
    return int(_leer().get("meses", {}).get(mes(dia), {}).get("facturas", 0))


def _subir_tope_una_vez() -> None:
    """El tope pasa a 20 € una sola vez (ver TOPE_POR_DEFECTO)."""
    try:
        if ajustes.leer(_TOPE_1_27_APLICADO):
            return
        ajustes.guardar(_TOPE_1_27_APLICADO, True)
        ajustes.guardar("tope_mensual", TOPE_POR_DEFECTO)
    except Exception:
        pass  # no poder guardarlo no debe tumbar la app


def tope() -> float:
    _subir_tope_una_vez()
    try:
        return float(ajustes.leer("tope_mensual", TOPE_POR_DEFECTO))
    except (TypeError, ValueError):
        return TOPE_POR_DEFECTO


def guardar_tope(euros: float) -> None:
    # Lo que pone el usuario manda sobre el cambio a 20 € de la 1.27.0.
    ajustes.guardar(_TOPE_1_27_APLICADO, True)
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
        from .extraccion import PROVEEDOR_CLAUDE, proveedor_lectura
        if proveedor_lectura() == PROVEEDOR_CLAUDE:
            # El gasto junta Claude y Gemini: el límite de Google solo mira
            # lo de Gemini, así que no se puede decir que fallarán.
            return (f"Ha superado el tope de gasto del mes ({_eur(tope())}). "
                    f"Lleva {_eur(gasto_del_mes())} entre Claude y Gemini.")
        return (f"Ha superado el tope de gasto del mes ({_eur(tope())}). "
                f"Lleva {_eur(gasto_del_mes())}. Si Google tiene ese mismo "
                f"límite, las próximas facturas fallarán.")
    if pct >= 80:
        return (f"Lleva gastado el {pct:.0f} % del tope del mes "
                f"({_eur(gasto_del_mes())} de {_eur(tope())}).")
    return ""


# ------------------------------------------------- cuanto ocupa una factura
# Gemini cobra las imagenes por "baldosas": una imagen pequeña (menos de 384 px
# de lado) son 258 tokens, y si no, se parte en cuadros de 768x768 y cada uno
# cuenta 258. Por eso mandar la pagina a mas puntos por pulgada multiplica el
# gasto, mientras que el color o el tamaño del PDF no cambian nada.
TOKENS_BALDOSA = 258
LADO_BALDOSA = 768
LADO_MINIMO = 384

A4_PULGADAS = (8.27, 11.69)
SALIDA_POR_FACTURA = 400      # tokens de respuesta, medidos con facturas reales


def tokens_imagen(ancho: int, alto: int) -> int:
    if ancho <= LADO_MINIMO and alto <= LADO_MINIMO:
        return TOKENS_BALDOSA
    columnas = -(-ancho // LADO_BALDOSA)      # division redondeando hacia arriba
    filas = -(-alto // LADO_BALDOSA)
    return columnas * filas * TOKENS_BALDOSA


def tokens_de_pagina(ppp: int) -> int:
    """Tokens de una factura A4 mandada a Gemini a esos puntos por pulgada."""
    return tokens_imagen(int(A4_PULGADAS[0] * ppp), int(A4_PULGADAS[1] * ppp))


# Claude (Opus 5.5) cobra la imagen por cuadros de 28x28 puntos: si un lado
# pasa de 2576 px la reduce, y nunca cuenta mas de 4784 tokens por imagen.
# Ademas van las instrucciones (unos 3.500 tokens, casi todas releidas de la
# hoja anterior a 0,05 veces la tarifa) y la respuesta, con lo que piensa
# antes de contestar: ESTIMADA hasta medirla con facturas reales (el gasto
# real sale de cada respuesta, no de aqui).
LADO_CUADRO_CLAUDE = 28
LADO_MAXIMO_CLAUDE = 2576
TOKENS_MAXIMOS_IMAGEN_CLAUDE = 4784
INSTRUCCIONES_CLAUDE = 3500 * 0.05 + 50
SALIDA_POR_FACTURA_CLAUDE = 2000


def tokens_imagen_claude(ancho: float, alto: float) -> int:
    escala = min(1.0, LADO_MAXIMO_CLAUDE / max(ancho, alto, 1))
    ancho, alto = ancho * escala, alto * escala

    def cuadros(a, b):
        return math.ceil(a / LADO_CUADRO_CLAUDE) * math.ceil(b / LADO_CUADRO_CLAUDE)

    tokens = cuadros(ancho, alto)
    if tokens > TOKENS_MAXIMOS_IMAGEN_CLAUDE:
        factor = math.sqrt(TOKENS_MAXIMOS_IMAGEN_CLAUDE / tokens)
        tokens = min(TOKENS_MAXIMOS_IMAGEN_CLAUDE,
                     cuadros(ancho * factor, alto * factor))
    return tokens


def tokens_de_pagina_claude(ppp: int) -> int:
    """Tokens de entrada (equivalentes) de una factura A4 mandada a Claude."""
    imagen = tokens_imagen_claude(A4_PULGADAS[0] * ppp, A4_PULGADAS[1] * ppp)
    return int(imagen + INSTRUCCIONES_CLAUDE)


def coste_por_factura(ppp: int, modelo: str = "") -> float:
    """Lo que cuesta leer UNA factura a esa calidad: con ese modelo o, si no
    se dice, con lo elegido para leer (con Claude, Claude más la lectura de
    Gemini si la doble lectura es «siempre»; con Gemini, el ultimo modelo que
    haya contestado o el mas caro de los Flash si aun no se sabe)."""
    if not modelo:
        from .extraccion import (
            DOBLE_SIEMPRE, MODELO_CLAUDE, PROVEEDOR_CLAUDE, modelos_gemini,
            modo_doble_lectura, proveedor_lectura,
        )
        if proveedor_lectura() == PROVEEDOR_CLAUDE:
            gemini = (coste_por_factura(ppp, modelos_gemini()[0])
                      if modo_doble_lectura() == DOBLE_SIEMPRE else 0.0)
            return coste_por_factura(ppp, MODELO_CLAUDE) + gemini
    if not modelo:
        modelo = ultimo_modelo()
        if _normaliza(modelo).startswith("claude"):
            # Con Gemini elegido, lo último leído con Claude (de una prueba)
            # no vale para estimar: se estima con el Gemini principal.
            from .extraccion import modelos_gemini
            modelo = modelos_gemini()[0]
    if _normaliza(modelo).startswith("claude"):
        return coste(modelo, tokens_de_pagina_claude(ppp), SALIDA_POR_FACTURA_CLAUDE)
    return coste(modelo, tokens_de_pagina(ppp), SALIDA_POR_FACTURA)


def ultimo_modelo() -> str:
    """El modelo que contesto la ultima vez (para estimar con lo que se paga)."""
    meses = _leer().get("meses", {})
    for clave in sorted(meses, reverse=True):
        modelo = meses[clave].get("ultimo_modelo")
        if modelo:
            return modelo
    return ""
