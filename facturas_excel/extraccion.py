"""Extraccion de datos de facturas con Gemini (Google).

Gemini devuelve EMISOR y DESTINATARIO por separado (para autodetectar quien es
el cliente de la asesoria: el NIF que se repite en todo el lote), los importes,
y una propuesta de CUENTA contable (plan PGC PYMES) segun el criterio de la
asesoria. La decision gasto/venta y la contraparte se calculan despues, en
procesar.py, una vez detectado el cliente.
"""

from __future__ import annotations

import json
import math
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

from google import genai
from google.genai import types

from .validacion import importe_posible

# Modelos de lectura (septiembre de 2026).
#
# Se usan modelos FIJOS, nunca los alias "-latest": un alias salta solo al
# modelo que Google saque, y con el saltarian tambien la tarifa y la forma de
# leer las facturas sin avisar. Hasta la 1.13 el respaldo eran precisamente
# esos alias; ahora el respaldo es otro modelo fijo y los dos se pueden
# cambiar en Configuracion -> Modelos de lectura.
#   - gemini-3.8-flash: el mas preciso para leer documentos escaneados.
#   - gemini-3.7-flash: el anterior; hace de respaldo y de segunda lectura.
MODELO_PRINCIPAL = "gemini-3.8-flash"
MODELO_RESPALDO = "gemini-3.7-flash"
MODELOS = [MODELO_PRINCIPAL, MODELO_RESPALDO]
MODELOS_CONOCIDOS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"]

# Doble lectura: "siempre" (cada hoja la leen los dos modelos), "dudosas" (la
# segunda solo si la primera no cuadra, trae un NIF invalido o confianza no
# alta) o "no".
DOBLE_SIEMPRE, DOBLE_DUDOSAS, DOBLE_NO = "siempre", "dudosas", "no"
DOBLE_POR_DEFECTO = DOBLE_SIEMPRE


# Lectura con Claude (prueba, octubre de 2026). Se elige en Configuracion ->
# Modelos de lectura -> «Quien lee las facturas». Con Claude, la PRIMERA
# lectura la hace Claude Opus 5.5 con su propia API key y la SEGUNDA (y el
# respaldo si Claude falla) el Gemini principal de siempre: dos IA de empresas
# distintas casi nunca leen mal igual el mismo digito. Con Gemini, todo sigue
# exactamente como hasta ahora.
PROVEEDOR_GEMINI, PROVEEDOR_CLAUDE = "gemini", "claude"
PROVEEDOR_POR_DEFECTO = PROVEEDOR_GEMINI
MODELO_CLAUDE = "claude-opus-5-5"
# Cuanto «piensa» Claude antes de contestar. En Opus 5.5 no se puede apagar;
# «medium» es su valor normal. Mas esfuerzo = mas tokens de salida pagados.
ESFUERZOS_CLAUDE = ("low", "medium", "high")
ESFUERZO_CLAUDE_POR_DEFECTO = "medium"
# Claude piensa antes de escribir: tarda mas que Gemini en contestar. Y si
# una hoja larga se vuelve a pedir con el tope ampliado de tokens, se le da
# mas tiempo (el SDK calcula una hora por cada 128.000 tokens; 10 min como
# mucho, que es lo que admite sin ir «en directo»).
TIEMPO_LIMITE_CLAUDE = 240           # segundos
TIEMPO_LIMITE_CLAUDE_AMPLIADO = 600  # segundos, con MAX_TOKENS_AMPLIADO


def tiempo_limite_claude(tope: Optional[int] = None) -> int:
    return TIEMPO_LIMITE_CLAUDE_AMPLIADO if (tope or 0) > MAX_TOKENS_SALIDA \
        else TIEMPO_LIMITE_CLAUDE


def proveedor_lectura() -> str:
    """«gemini» (como siempre) o «claude» (Opus 5.5 + Gemini)."""
    from . import ajustes
    proveedor = str(ajustes.leer("proveedor_lectura", PROVEEDOR_POR_DEFECTO) or "")
    return proveedor if proveedor in (PROVEEDOR_GEMINI, PROVEEDOR_CLAUDE) \
        else PROVEEDOR_POR_DEFECTO


def esfuerzo_claude() -> str:
    from . import ajustes
    esfuerzo = str(ajustes.leer("esfuerzo_claude", ESFUERZO_CLAUDE_POR_DEFECTO) or "")
    return esfuerzo if esfuerzo in ESFUERZOS_CLAUDE else ESFUERZO_CLAUDE_POR_DEFECTO


def es_claude(modelo: str) -> bool:
    return str(modelo or "").lower().replace("models/", "").startswith("claude")


def nombre_ia(modelo: str) -> str:
    """Para los avisos: quien ha contestado (o no)."""
    return "Claude" if es_claude(modelo) else "Gemini"


def modelos_gemini() -> List[str]:
    """[principal, respaldo] de Gemini segun los ajustes, sin repetir."""
    from . import ajustes
    principal = str(ajustes.leer("modelo_principal", MODELO_PRINCIPAL) or "").strip()
    respaldo = str(ajustes.leer("modelo_respaldo", MODELO_RESPALDO) or "").strip()
    salida = []
    for modelo in (principal or MODELO_PRINCIPAL, respaldo):
        if modelo and modelo not in salida and "latest" not in modelo:
            salida.append(modelo)
    return salida or list(MODELOS)


def modelos_configurados() -> List[str]:
    """Los modelos con que se lee, en orden: el primero hace la primera
    lectura; el segundo, la segunda y el respaldo.

    Con Gemini, [principal, respaldo] como siempre. Con Claude, Claude Opus
    5.5 delante y detras los de Gemini."""
    if proveedor_lectura() == PROVEEDOR_CLAUDE:
        return [MODELO_CLAUDE] + modelos_gemini()
    return modelos_gemini()


def modo_doble_lectura() -> str:
    from . import ajustes
    modo = str(ajustes.leer("doble_lectura", DOBLE_POR_DEFECTO) or "")
    return modo if modo in (DOBLE_SIEMPRE, DOBLE_DUDOSAS, DOBLE_NO) \
        else DOBLE_POR_DEFECTO


# Tiempo maximo que se espera a Gemini por pagina. Sin esto una peticion que
# se queda colgada bloquea el hilo PARA SIEMPRE: con 70 paginas el lote se
# quedaba en "69/70" y no terminaba nunca (04/09/2026).
TIEMPO_LIMITE = 90       # segundos

# Tope de lo que puede contestar Gemini por hoja (tokens de salida, que
# incluyen lo que «piensa»). El JSON del esquema ocupa unos 500 tokens y con
# 12 líneas de IVA no llega a 1.500; con el pensamiento en LOW sobra. Sin
# tope, una respuesta desbocada (cifras o artículos repetidos) podía llegar a
# 65.000 tokens pagados y a cientos de KB por hoja en la sesión y las
# muestras. Sin esquema el modelo piensa lo que quiere: el doble de margen.
MAX_TOKENS_SALIDA = 8192
# Si aun así una respuesta llega cortada por el tope (no rota: Gemini dice que
# paró por los tokens), se vuelve a pedir con este. Una hoja legítima larga
# (80-100 líneas de artículos en una página) cabe, y no se paga tres veces la
# misma respuesta cortada para acabar en rojo; una desbocada sigue sin llegar
# a los 65.000.
MAX_TOKENS_AMPLIADO = 4 * MAX_TOKENS_SALIDA


class SinCredito(Exception):
    """La API key no tiene credito / facturacion activa (no reintentar)."""


class DemasiadasPeticiones(Exception):
    """Google pide ir más despacio (429) y no ha bastado con esperar."""


class TiempoAgotado(Exception):
    """Gemini no contesto a tiempo: esa pagina se da por no leida."""


class ModeloNoDisponible(Exception):
    """El modelo pedido no existe o Google lo ha retirado."""


class ClaudeNoDisponible(ModeloNoDisponible):
    """Claude no puede leer (API key mala, sin saldo, sin clave): se deja de
    pedir a Claude en ese bloque y las hojas las lee Gemini. NO para la
    lectura como SinCredito: la API key de Gemini sigue valiendo."""


class ErrorLectura(Exception):
    """Una hoja no se pudo leer; lleva lo que ya se habia pagado por ella."""

    def __init__(self, mensaje: str, consumos=None):
        super().__init__(mensaje)
        self.consumos = list(consumos or [])


# Sin crédito de verdad (prepago agotado, facturación sin activar). OJO: el
# 429 de «demasiadas peticiones por minuto» dice «check your plan and billing
# details»; por eso no basta con ver «billing» (se tiraban bloques ya leídos y
# pagados como si no hubiera saldo).
_SIN_CREDITO = ("depleted", "prepayment", "credit", "requires billing",
                "billing to be enabled", "billing is not enabled",
                "billing has not been enabled", "billing_disabled")

# Cuántas veces se espera y se repite una hoja cuando Google pide calma.
ESPERAS_POR_CUOTA = 5
ESPERA_MAXIMA = 60       # segundos


def _es_sin_credito(e: Exception) -> bool:
    texto = str(e).lower()
    return any(k in texto for k in _SIN_CREDITO)


def _es_limite_de_peticiones(e: Exception) -> bool:
    """429 / RESOURCE_EXHAUSTED por ir deprisa, no por falta de saldo."""
    texto = str(e).lower()
    return (getattr(e, "code", None) == 429
            or re.search(r"\b429\b", texto) is not None
            or "resource_exhausted" in texto) and not _es_sin_credito(e)


def _es_cuota_diaria(e: Exception) -> bool:
    """La cuota del día no vuelve esperando un minuto."""
    texto = str(e).lower()
    return "perday" in texto or "per day" in texto or "daily" in texto


def _segundos_de_espera(e: Exception, vez: int) -> float:
    """Lo que pide Google (retryDelay) o 5, 10, 20, 40… sin pasar de 60."""
    base = 5 * (2 ** vez)
    pedido = re.search(r"retry_?delay\W+(\d+(?:\.\d+)?)\s*s", str(e).lower())
    if pedido:
        base = max(base, float(pedido.group(1)))
    return min(ESPERA_MAXIMA, base) + random.uniform(0, 1)


def _es_modelo_retirado(e: Exception) -> bool:
    texto = str(e).lower()
    return ("404" in texto or "not_found" in texto or "not found" in texto
            or "no longer available" in texto or "deprecated" in texto) \
        and "model" in texto


def _es_error_de_esquema(e: Exception) -> bool:
    texto = str(e).lower()
    return "400" in texto and ("schema" in texto or "thinking" in texto)


def _es_timeout(e: Exception) -> bool:
    texto = (type(e).__name__ + " " + str(e)).lower()
    return "timeout" in texto or "timed out" in texto


# ------------------------------------------------- errores propios de Claude
def _estado_http(e: Exception):
    """El codigo HTTP de un error del SDK de Claude (None si no lo trae)."""
    try:
        return int(getattr(e, "status_code", None))
    except (TypeError, ValueError):
        return None


def _clave_rechazada_claude(e: Exception) -> bool:
    """401/403: la API key de Claude no vale (mal copiada, revocada…)."""
    return _estado_http(e) in (401, 403)


def _saturado_claude(e: Exception) -> bool:
    """Claude ocupado (529) o un fallo suyo pasajero (500-504), o un corte de
    red: se espera un poco y se vuelve a pedir, como el 503 de Gemini."""
    if _estado_http(e) in (500, 502, 503, 504, 529):
        return True
    if any(c.__name__ == "APIConnectionError" for c in type(e).__mro__):
        return True
    return "overloaded" in str(e).lower()


def _error_de_esquema_claude(e: Exception) -> bool:
    """El formato cerrado de la respuesta no lo ha aceptado Claude."""
    texto = str(e).lower()
    return _estado_http(e) == 400 and (
        "schema" in texto or "output_config" in texto or "json_schema" in texto)


def _limite_de_gasto_claude(e: Exception) -> bool:
    """El 429 de Claude que no es por ir deprisa sino por el tope de gasto
    del mes de la cuenta (error_code «enforced_spend_limit_reached»)."""
    cuerpo = getattr(e, "body", None)
    error = cuerpo.get("error") if isinstance(cuerpo, dict) else None
    detalles = error.get("details") if isinstance(error, dict) else None
    if isinstance(detalles, dict) and \
            detalles.get("error_code") == "enforced_spend_limit_reached":
        return True
    return "enforced_spend_limit_reached" in str(e)


def _espera_pedida_claude(e: Exception) -> float:
    """Los segundos que pide Claude en la cabecera retry-after (0 si nada)."""
    cabeceras = getattr(getattr(e, "response", None), "headers", None)
    try:
        return float(cabeceras.get("retry-after") or 0) if cabeceras else 0.0
    except (TypeError, ValueError):
        return 0.0

# Criterio contable que sigue Gemini para proponer el concepto de un GASTO.
# La lista de conceptos NO es libre: es la que ofrece Aplifisa (catalogo en
# config/conceptos_aplifisa.csv). Se le da entera para que elija de ahi y no se
# invente cuentas que luego no existen al importar.
def _lista_conceptos(tipo: str) -> str:
    from .conceptos import catalogo
    return chr(10).join(f"  {c} ({g}) {d}" for c, g, d in catalogo(tipo)
                        if c != "200")


_CRITERIO_CUENTAS = """CONCEPTOS DE GASTO (si la factura es una COMPRA del
cliente). Elige UNO de esta lista EXACTA y devuelve su cuenta y su subclave.
No uses ninguna cuenta que no este aqui:
{conceptos}

CONCEPTOS DE INGRESO (si la factura la EMITE el cliente). Misma norma:
{ingresos}

CRITERIO DE LA ASESORIA (importante):
- COMBUSTIBLE (gasoleo, gasoil, gasolina, diesel, AdBlue) y gasolineras o areas
  de servicio -> 628 (G16) SUMINISTROS GAS. El gasoleo y sus derivados van al
  gas, NO a otros suministros.
- Luz/electricidad -> 628 (G14).  Agua -> 628 (G15).
- Telefono, movil, internet, fibra -> 628 (G17).
- Talleres, reparaciones, recambios, neumaticos -> 622 (G13). Aplica criterio
  real: una "bomba de agua" en una factura de taller es reparacion, no agua.
- Notario, registro, abogado, gestoria, asesoria -> 623 (G19).
- Seguros -> 625 (G20).  Comisiones y gastos de banco -> 626 (G22).
- Alquileres y renting -> 621 (G12).  Publicidad -> 627 (G22).
- Mensajeria y portes -> 624 (G22).  Material de oficina -> 629 (G22).
- Impuestos y tasas municipales (IVTM, basuras) -> 631 (G26).
- Mercaderia para revender -> 600 (G01).
- Si no encaja en ninguno con claridad, usa 629 (G22) OTROS SERVICIOS.
- En los INGRESOS: venta de genero -> 700 (I01); trabajos, obras, reparto,
  alquileres y demas servicios -> 705 (I01); subvenciones -> 740/741/746;
  intereses cobrados -> 760 (I02).""".format(
    conceptos=_lista_conceptos("gasto"), ingresos=_lista_conceptos("ingreso"))

_PROMPT = f"""Eres un experto en contabilidad espanola. Analiza esta factura escaneada.

Identifica las DOS partes de la factura, cada una con su nombre y NIF/CIF:
- EMISOR: quien emite/cobra la factura.
- DESTINATARIO: el cliente que recibe/paga la factura.

{_CRITERIO_CUENTAS}

MUY IMPORTANTE — LOS IMPORTES, SOLO LOS IMPRESOS. Usa siempre los IMPORTES
impresos por el emisor. IGNORA cualquier importe escrito a mano: totales
manuscritos, cifras rodeadas con un circulo, lineas tachadas, "NO" junto a un
articulo o el total impreso tachado con una raya. Aunque el total impreso este
tachado y al lado haya otro a mano, devuelve SIEMPRE el impreso.

FACTURAS DE VARIAS PAGINAS: la imagen puede ser una hoja intermedia o la ultima
hoja de una factura cuya cabecera estaba en la pagina anterior. Lee tambien el
pie de pagina: si alli se repiten el numero de factura y la fecha, devuelvelos
en num_factura y fecha aunque no aparezca otra cabecera. Extrae de esta hoja el
resumen fiscal (bases, IVA, recargo y total) aunque los datos del destinatario
solo estuvieran en la primera. No inventes las partes que no se vean: dejalas a
null. Indica ademas si la hoja es "unica", "inicio", "intermedia" o "final":
- "inicio": tiene cabecera y lineas de articulos, pero no el resumen fiscal final.
- "intermedia": continua lineas de articulos sin cabecera ni resumen final.
- "final": continua una factura anterior y contiene sus ultimos articulos o el
  resumen fiscal definitivo, aunque no repita numero o destinatario.
- "unica": contiene por si sola cabecera y resumen fiscal definitivo.
No confundas un SUBTOTAL DE ARTICULOS al final de una hoja inicial/intermedia
con la base imponible o el total de la factura. En esas hojas deja lineas_iva y
total vacios/null. El resumen fiscal de la hoja final es el que manda.

EN CAMBIO, EL NIF Y EL NUMERO SI PUEDEN VENIR A MANO. El asesor anota a mano el
CIF/NIF cuando el impreso no se lee o es confuso, y numera las facturas para los
requerimientos de Hacienda. Asi que:
- Si el NIF/CIF impreso falta o esta borroso y hay uno escrito a mano
  (normalmente al pie, tipo "CIF: A78923125"), USA EL ESCRITO A MANO.
- Si el numero de factura impreso falta y hay uno a mano, usalo.
- Esas anotaciones NO son un error de la factura: estan puestas a proposito.

Devuelve SOLO un JSON con esta estructura exacta:
{{
  "emisor_nombre": "...", "emisor_nif": "...",
  "receptor_nombre": "...", "receptor_nif": "...",
  "num_factura": "...",
  "fecha": "dd/mm/aaaa",
  "fecha_operacion": "dd/mm/aaaa o null",
  "estado_pagina_factura": "unica/inicio/intermedia/final",
  "lineas_iva": [{{"base": 0.0, "tipo_iva": 0.0, "cuota_iva": 0.0,
                  "pct_requiv": null, "cuota_requiv": null}}],
  "base_irpf": null, "pct_irpf": null, "cuota_irpf": null,
  "suplidos": null,
  "es_bien_inversion": false,
  "total": 0.0,
  "sustituye_a": null,
  "manuscrito_en_importes": false,
  "cuenta_gasto": "cuenta del concepto de GASTO que le corresponderia",
  "subclave_gxx": "la subclave GXX de ESE MISMO concepto (siempre, no solo en la 628)",
  "cuenta_ingreso": "cuenta del concepto de INGRESO que le corresponderia",
  "subclave_ingreso": "la subclave IXX de ese concepto de ingreso",
  "concepto_texto": "descripcion breve del gasto/venta",
  "tipo_documento": "factura",
  "moneda": "EUR",
  "mencion_iva": "ninguna",
  "posible_no_deducible": "no",
  "confianza": "alta/media/baja segun lo legible que este la factura"
}}
Numeros con punto decimal. Si la factura tiene varios tipos de IVA, pon una
entrada por cada tipo en lineas_iva. Si un dato no aparece, usa null.

RECARGO DE EQUIVALENCIA: si la factura desglosa un "Recargo Equivalencia",
"Recargo Equivalent" o "REC.EQUIV", va DENTRO de su linea de lineas_iva
(pct_requiv y cuota_requiv), porque CADA TIPO DE IVA LLEVA SU PROPIO RECARGO:
IVA 21% -> 5,2% (tabaco: 1,75%) ; IVA 10% -> 1,4% ; IVA 4% -> 0,5%. Su base
es la misma que la
base de esa linea. Es un impuesto MAS que se suma al total, no un descuento.
Si esa linea no lleva recargo, deja los dos a null.

SUPLIDOS: si la factura identifica expresamente un importe como "suplidos",
"suplido" o cantidad pagada por cuenta del cliente, devuelve ese importe en
"suplidos". Los suplidos NO forman parte de la base imponible ni llevan IVA,
pero se SUMAN al total a pagar. Copia solamente el importe que figure como tal;
no deduzcas un suplido solo porque haya una diferencia en el total. Si no
aparece identificado, deja "suplidos" a null.

BIENES DE INVERSION: pon "es_bien_inversion" a true SOLO cuando la factura
corresponda claramente a la compra de un inmovilizado duradero (maquinaria,
vehiculo, mobiliario, equipo informatico, inmueble, etc.), no a una reparacion,
recambio, consumible o gasto corriente. Estas facturas se revisan manualmente.

FACTURA QUE SUSTITUYE A OTRA: si el documento dice que sustituye/anula/rectifica
a otro (p.ej. "Sustituye al doc.n: 4532023141", "POST-FACTURACION", factura
rectificativa), pon en "sustituye_a" el numero del documento al que sustituye.
Si no lo dice, null.

ABONOS Y SIGNO DETRAS DEL NUMERO — CUIDADO, ES FACIL EQUIVOCARSE. Algunos
proveedores (Coca-Cola) imprimen los numeros negativos con el signo menos
DETRAS: "15,51-" significa MENOS 15,51, NO 15,51. Se ve en cantidades ("1,00-"),
importes ("28,20-") y totales ("TOTAL: 15,51- EUROS").
Si la factura es un ABONO / devolucion / rectificativa (sus importes llevan el
menos detras), devuelve TODOS los importes en NEGATIVO con el signo delante:
base, cuota_iva, cuota_requiv y total. NUNCA los pases a positivo: un abono
registrado en positivo cobra al cliente lo que habia que devolverle.

QUE DOCUMENTO ES: en "tipo_documento" pon "factura" si es una factura normal;
"factura_simplificada" si es un tique o factura simplificada; "rectificativa"
si es una factura rectificativa o abono; "proforma", "albaran", "presupuesto",
"pedido" o "recibo" si el titulo dice que es eso y NO una factura; "copia" si
pone "copia" o "duplicado"; "otro" si no es nada de lo anterior.

MONEDA: el codigo de la moneda de los importes ("EUR", "USD", "GBP"...). Si
los importes van en euros o no se indica, "EUR".

MENCION DE IVA: si la factura lleva una mencion como "Inversion del sujeto
pasivo", "ISP", "art. 84 LIVA", "Reverse charge" o "Autoliquidacion", pon
"inversion_sujeto_pasivo"; si dice "entrega/adquisicion intracomunitaria" o
"art. 25 LIVA", "intracomunitaria"; si es exportacion/importacion,
"exportacion"; si dice "exenta" (art. 20 LIVA), "exenta"; si dice "no sujeta",
"no_sujeta". Si no lleva ninguna, "ninguna".

GASTO QUE PUEDE NO DEDUCIR EL IVA: en "posible_no_deducible" pon
"restauracion" (una comida o consumicion en restaurante, cafeteria o bar),
"regalo" (regalos o atenciones a clientes), "alimentos_tabaco", "joyas" o
"espectaculos" SOLO si es para consumo propio, no si es mercancia para
vender o material de la actividad (las bebidas que compra un bar, las joyas
de una joyeria: eso es "no"). Si no, "no".

ANOTACIONES A MANO: pon "manuscrito_en_importes" a true SOLO si lo escrito a
mano toca a los IMPORTES (un total corregido, una cifra tachada, un articulo
marcado con "NO"): eso si hay que revisarlo. Un CIF anotado, una numeracion o
una firma de "RECIBI MERCANCIAS" NO cuentan: son normales y no se avisa de
ellas."""


TIPOS_DOCUMENTO = ["factura", "factura_simplificada", "rectificativa",
                   "proforma", "albaran", "presupuesto", "pedido", "recibo",
                   "copia", "otro"]
MENCIONES_IVA = ["ninguna", "inversion_sujeto_pasivo", "intracomunitaria",
                 "exportacion", "exenta", "no_sujeta"]
NO_DEDUCIBLES = ["no", "restauracion", "regalo", "alimentos_tabaco", "joyas",
                 "espectaculos"]


def _anulable(tipo: str) -> dict:
    return {"type": [tipo, "null"]}


_LINEA = {
    "type": "object",
    "properties": {
        "base": _anulable("number"), "tipo_iva": _anulable("number"),
        "cuota_iva": _anulable("number"), "pct_requiv": _anulable("number"),
        "cuota_requiv": _anulable("number"),
    },
    "required": ["base", "tipo_iva", "cuota_iva", "pct_requiv", "cuota_requiv"],
}

# Formato CERRADO de la respuesta: los importes llegan como numeros (no como
# "1.234" que puede ser mil doscientos o uno coma dos), las opciones cerradas
# solo pueden ser una de las previstas y no falta ninguna clave.
ESQUEMA = {
    "type": "object",
    "properties": {
        "emisor_nombre": _anulable("string"), "emisor_nif": _anulable("string"),
        "receptor_nombre": _anulable("string"),
        "receptor_nif": _anulable("string"),
        "num_factura": _anulable("string"), "fecha": _anulable("string"),
        "fecha_operacion": _anulable("string"),
        "estado_pagina_factura": {
            "type": "string", "enum": ["unica", "inicio", "intermedia", "final"]},
        "lineas_iva": {"type": "array", "items": _LINEA},
        "base_irpf": _anulable("number"), "pct_irpf": _anulable("number"),
        "cuota_irpf": _anulable("number"), "suplidos": _anulable("number"),
        "es_bien_inversion": {"type": "boolean"},
        "total": _anulable("number"),
        "sustituye_a": _anulable("string"),
        "manuscrito_en_importes": {"type": "boolean"},
        "cuenta_gasto": _anulable("string"), "subclave_gxx": _anulable("string"),
        "cuenta_ingreso": _anulable("string"),
        "subclave_ingreso": _anulable("string"),
        "concepto_texto": _anulable("string"),
        "tipo_documento": {"type": "string", "enum": TIPOS_DOCUMENTO},
        "moneda": _anulable("string"),
        "mencion_iva": {"type": "string", "enum": MENCIONES_IVA},
        "posible_no_deducible": {"type": "string", "enum": NO_DEDUCIBLES},
        "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
    },
}
ESQUEMA["required"] = list(ESQUEMA["properties"])


# ------------------------------------------------------------------ Claude
def _a_claude(nodo):
    """El ESQUEMA en la forma que acepta Claude.

    Claude exige todo objeto cerrado (additionalProperties: false) y admite
    como mucho 16 datos «de dos tipos» (texto o null) por respuesta; el
    nuestro tiene 24. Asi que los TEXTOS que pueden faltar se piden como texto
    («» si no estan; al leer se vuelven null, ver _vacios_a_null) y solo los
    IMPORTES conservan el null (anyOf numero/null): un importe a 0 y uno que
    no esta no son lo mismo."""
    if isinstance(nodo, list):
        return [_a_claude(n) for n in nodo]
    if not isinstance(nodo, dict):
        return nodo
    nuevo = {}
    for clave, valor in nodo.items():
        if clave == "properties":
            nuevo[clave] = {k: _a_claude(v) for k, v in valor.items()}
        elif clave == "items":
            nuevo[clave] = _a_claude(valor)
        else:
            nuevo[clave] = valor
    tipo = nuevo.get("type")
    if isinstance(tipo, list):
        otros = [t for t in tipo if t != "null"]
        if otros == ["string"]:
            nuevo["type"] = "string"
        else:
            del nuevo["type"]
            nuevo = {"anyOf": [dict(nuevo, type=t) for t in otros]
                     + [{"type": "null"}]}
    if nuevo.get("type") == "object":
        nuevo["additionalProperties"] = False
    return nuevo


ESQUEMA_CLAUDE = _a_claude(ESQUEMA)
# Los textos que en Gemini pueden venir a null y en Claude llegan como «».
_TEXTOS_ANULABLES = tuple(
    campo for campo, definicion in ESQUEMA["properties"].items()
    if definicion.get("type") == ["string", "null"])

# Lo que acompaña a la imagen en el mensaje a Claude (las instrucciones van
# aparte, en el «system», que se reutiliza de una hoja a otra).
_PETICION_CLAUDE = (
    "Lee esta hoja y devuelve el JSON. Si un texto no aparece en la hoja, "
    "dejalo vacio (\"\"); si un importe no aparece, null.")

# Lo que cuesta lo que Claude ya tenia guardado de la hoja anterior (las
# instrucciones, iguales en todas): escribirlo la primera vez cuesta 1,25
# veces la tarifa de entrada y releerlo, 0,05 veces en Opus 5.5 (0,20 $
# frente a 4 $ por millon). Se cuenta como tokens de entrada «equivalentes»
# para que el gasto del mes salga con la tarifa normal de entrada.
CACHE_ESCRITURA = 1.25
CACHE_LECTURA = 0.05


def _vacios_a_null(datos: dict) -> dict:
    """Los textos que Claude deja en «» porque no estan pasan a null, como
    los devuelve Gemini: el resto del programa no nota la diferencia."""
    for campo in _TEXTOS_ANULABLES:
        valor = datos.get(campo)
        if isinstance(valor, str) and not valor.strip():
            datos[campo] = None
    return datos


class RespuestaClaude:
    """La respuesta de Claude con la forma que el resto de la lectura usa de
    la de Gemini: el texto, el modelo que ha contestado, los tokens y si
    paro por el tope de tokens."""

    def __init__(self, resp):
        self.stop_reason = getattr(resp, "stop_reason", None)
        self.text = "".join(
            getattr(bloque, "text", "") or "" for bloque in
            (getattr(resp, "content", None) or [])
            if getattr(bloque, "type", "") == "text")
        self.model_version = str(getattr(resp, "model", "") or "")
        uso = getattr(resp, "usage", None)

        def _n(nombre):
            try:
                return int(getattr(uso, nombre, 0) or 0)
            except (TypeError, ValueError):
                return 0

        entrada = (_n("input_tokens")
                   + round(_n("cache_creation_input_tokens") * CACHE_ESCRITURA)
                   + round(_n("cache_read_input_tokens") * CACHE_LECTURA))
        # En Claude lo que «piensa» ya va dentro de output_tokens.
        self.usage_metadata = _Uso(entrada, _n("output_tokens"))
        motivo = "MAX_TOKENS" if self.stop_reason == "max_tokens" \
            else str(self.stop_reason or "").upper()
        self.candidates = [_Candidato(motivo)]


@dataclass
class _Uso:
    prompt_token_count: int
    candidates_token_count: int
    thoughts_token_count: int = 0


@dataclass
class _Candidato:
    finish_reason: str


@dataclass
class DatosFactura:
    crudo: dict
    origen: str = ""
    pagina: int = 0
    # Lo que ha costado leer esta factura: el modelo que ha contestado de
    # verdad y sus tokens (suma de todas las llamadas).
    modelo: str = ""
    tokens_entrada: int = 0
    tokens_salida: int = 0
    # (modelo, tokens de entrada, tokens de salida) de CADA llamada: con la
    # doble lectura hay dos modelos con tarifas distintas.
    consumos: list = field(default_factory=list)


class Extractor:
    def __init__(self, api_key: str, modelos: Optional[List[str]] = None,
                 modo_doble: Optional[str] = None,
                 clave_claude: Optional[str] = None):
        self.client = genai.Client(
            api_key=api_key,
            # El SDK lo quiere en milisegundos.
            http_options=types.HttpOptions(timeout=TIEMPO_LIMITE * 1000))
        self.modelos = list(modelos or modelos_configurados())
        self.modo_doble = modo_doble or modo_doble_lectura()
        self._con_esquema = True
        # Claude: su cliente se crea al pedirle la primera hoja (con Gemini
        # elegido no se crea nunca) con su propia API key.
        self._clave_claude = clave_claude
        self._cliente_claude = None
        self._con_esquema_claude = True
        self._esfuerzo_claude = esfuerzo_claude()
        # Hojas que se iban a leer con Claude y ha leído solo Gemini, y el
        # primer motivo: la ventana lo avisa al acabar el bloque.
        self._hojas_sin_claude = 0
        self._motivo_claude = ""
        self._motivo_claude_definitivo = False
        # Modelos que Google ha dado por retirados: no se vuelven a pedir en
        # las siguientes hojas del mismo bloque.
        self._retirados: set = set()
        # Cuando Google pide calma (429), esperan todas las hojas a la vez:
        # si no, las diez que se leen a la vez volverían a chocar. Cada IA
        # lleva su propia espera: que Claude pida calma no para a Gemini.
        self._cerrojo = threading.Lock()
        self._pausa_hasta = {}      # «gemini»/«claude» -> hasta cuando
        self._sin_cuota = {}        # «gemini»/«claude» -> el aviso
        # Al cerrar el programa no se espera a Google: se deja de pedir.
        self.cancelado = threading.Event()

    @staticmethod
    def _ia(modelo: str) -> str:
        return PROVEEDOR_CLAUDE if es_claude(modelo) else PROVEEDOR_GEMINI

    def _pausar(self, segundos: float, ia: str = PROVEEDOR_GEMINI) -> None:
        with self._cerrojo:
            self._pausa_hasta[ia] = max(self._pausa_hasta.get(ia, 0.0),
                                        time.monotonic() + segundos)

    def _esperar_pausa(self, ia: str = PROVEEDOR_GEMINI) -> None:
        """Espera a trozos cortos: si se cierra el programa, deja de esperar."""
        resto = self._pausa_hasta.get(ia, 0.0) - time.monotonic()
        while resto > 0 and not self.cancelado.is_set():
            trozo = min(resto, 0.5)
            time.sleep(trozo)
            resto -= trozo

    def _pedir(self, modelo: str, img: bytes, tope: Optional[int] = None):
        """La petición a la IA, esperando cuando pide ir más despacio.

        Si ni así hay sitio (o es la cuota del día), las hojas que quedan no
        se piden: se quedan en rojo para leerlas luego, y lo leído se queda."""
        ia = self._ia(modelo)
        for vez in range(ESPERAS_POR_CUOTA + 1):
            if self._sin_cuota.get(ia):
                raise DemasiadasPeticiones(self._sin_cuota[ia])
            self._esperar_pausa(ia)
            if self.cancelado.is_set():
                raise DemasiadasPeticiones(
                    "No leída: se cerró el programa mientras se leía.")
            try:
                if ia == PROVEEDOR_CLAUDE:
                    return self._pedir_claude(modelo, img, tope)
                return self.client.models.generate_content(
                    model=modelo,
                    contents=[types.Part.from_bytes(data=img, mime_type="image/jpeg"),
                              _PROMPT],
                    config=self._config(tope),
                )
            except Exception as e:
                if not _es_limite_de_peticiones(e):
                    raise
                if ia == PROVEEDOR_CLAUDE and _limite_de_gasto_claude(e):
                    # El tope de gasto mensual de la cuenta de Claude no
                    # vuelve esperando: hasta el mes que viene.
                    self._sin_cuota[ia] = (
                        "Claude ha llegado al límite de gasto mensual de su "
                        "cuenta (platform.claude.com → Billing → Limits).")
                    raise DemasiadasPeticiones(self._sin_cuota[ia]) from e
                if _es_cuota_diaria(e) or vez == ESPERAS_POR_CUOTA:
                    motivo = ("demasiadas peticiones"
                              + (" hoy" if _es_cuota_diaria(e) else " seguidas"))
                    if ia == PROVEEDOR_CLAUDE:
                        # Con Claude la hoja no se pierde: la lee Gemini.
                        self._sin_cuota[ia] = (
                            f"Claude ha pedido parar ({motivo}): el resto del "
                            "bloque lo lee Gemini.")
                    else:
                        self._sin_cuota[ia] = (
                            f"Gemini ha pedido parar ({motivo}): esta hoja no "
                            "se ha leído. Vuelva a cargarla más tarde.")
                    raise DemasiadasPeticiones(self._sin_cuota[ia]) from e
                espera = _segundos_de_espera(e, vez)
                if ia == PROVEEDOR_CLAUDE:
                    espera = min(ESPERA_MAXIMA, max(espera, _espera_pedida_claude(e)))
                self._pausar(espera, ia)

    # ------------------------------------------------------------- Claude
    def _claude(self):
        """El cliente de Claude, creado una sola vez aunque lo pidan diez
        hojas a la vez. Sin API key de Claude no se puede: esa lectura falla
        y la hace Gemini (la ventana ya avisa antes de empezar)."""
        with self._cerrojo:
            if self._cliente_claude is None:
                from . import claves
                clave = (self._clave_claude or claves.leer_api_key_claude() or "").strip()
                if not clave:
                    raise ClaudeNoDisponible(
                        "Falta la API key de Claude (Configuración → API key "
                        "de Claude…).")
                import anthropic
                # Los reintentos los lleva este modulo (como con Gemini), no
                # el SDK: asi el tiempo maximo por hoja es el que se dice.
                self._cliente_claude = anthropic.Anthropic(
                    api_key=clave, timeout=TIEMPO_LIMITE_CLAUDE, max_retries=0)
            return self._cliente_claude

    def _pedir_claude(self, modelo: str, img: bytes, tope: Optional[int] = None):
        """Una hoja a Claude: las instrucciones de siempre (guardadas de una
        hoja a la siguiente, que asi casi no se pagan), la imagen y el mismo
        formato cerrado de respuesta que a Gemini."""
        import base64
        cliente = self._claude()
        mime = "image/png" if (img or b"").startswith(b"\x89PNG") else "image/jpeg"
        salida = {"effort": self._esfuerzo_claude}
        if self._con_esquema_claude:
            salida["format"] = {"type": "json_schema", "schema": ESQUEMA_CLAUDE}
        resp = cliente.messages.create(
            model=modelo,
            max_tokens=tope or MAX_TOKENS_SALIDA,
            system=[{"type": "text", "text": _PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": mime,
                    "data": base64.standard_b64encode(img).decode("ascii")}},
                {"type": "text", "text": _PETICION_CLAUDE},
            ]}],
            output_config=salida,
            timeout=tiempo_limite_claude(tope),
        )
        return RespuestaClaude(resp)

    # ------------------------------------------------------------ llamadas
    def _config(self, tope: Optional[int] = None):
        tope = tope or MAX_TOKENS_SALIDA
        if not self._con_esquema:
            return types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=2 * tope)
        return types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=ESQUEMA,
            max_output_tokens=tope,
            # LOW: estos modelos no admiten MINIMAL y la temperatura se
            # ignora. Pensar poco basta para copiar datos y va mas rapido.
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.LOW))

    def _llamar(self, modelo: str, img: bytes, tope: Optional[int] = None):
        """Una respuesta de ese modelo, con reintentos solo ante saturacion."""
        ultimo = None
        claude = es_claude(modelo)
        for intento in range(3):
            try:
                return self._pedir(modelo, img, tope)
            except (DemasiadasPeticiones, ModeloNoDisponible):
                raise
            except Exception as e:  # 503, red, etc.
                ultimo = e
                msg = str(e).lower()
                if claude and (_estado_http(e) == 402
                               or getattr(e, "type", None) == "billing_error"):
                    raise ClaudeNoDisponible(
                        "Claude no acepta el cobro de tu cuenta (pago o "
                        "facturación). Revísalo en platform.claude.com "
                        "(Billing).") from e
                if claude and _clave_rechazada_claude(e):
                    raise ClaudeNoDisponible(
                        "La API key de Claude no es válida o no tiene permiso. "
                        "Cópiala de nuevo de platform.claude.com en "
                        "Configuración → API key de Claude…") from e
                if _es_sin_credito(e):
                    if claude:
                        raise ClaudeNoDisponible(
                            "Tu API key de Claude no tiene crédito. Añade "
                            "saldo en platform.claude.com (Billing).") from e
                    raise SinCredito(
                        "Tu API key no tiene crédito/facturación activa. "
                        "Activa la facturación en aistudio.google.com y añade saldo."
                    ) from e
                if _es_modelo_retirado(e):
                    raise ModeloNoDisponible(
                        f"El modelo {modelo} no está disponible: {e}") from e
                if claude:
                    if self._con_esquema_claude and _error_de_esquema_claude(e):
                        # Si Claude no acepta el formato cerrado, sigue
                        # leyendo con el formato libre (el JSON que pide el
                        # texto de las instrucciones).
                        self._con_esquema_claude = False
                        continue
                elif self._con_esquema and _es_error_de_esquema(e):
                    # Un modelo que no admita el formato cerrado sigue
                    # leyendo con el formato libre de siempre.
                    self._con_esquema = False
                    continue
                if _es_timeout(e):
                    # Un tiron de red se reintenta una vez; si vuelve a
                    # colgarse, esta pagina se marca y el lote sigue.
                    if intento == 0:
                        continue
                    limite = tiempo_limite_claude(tope) if claude else TIEMPO_LIMITE
                    raise TiempoAgotado(
                        f"{nombre_ia(modelo)} no contestó en {limite} segundos "
                        f"(se intentó dos veces).") from e
                if "503" in msg or "unavailable" in msg or (
                        claude and _saturado_claude(e)):
                    time.sleep(2 * (intento + 1))
                    continue
                raise
        raise ultimo

    def _generar(self, img: bytes):
        """Respuesta del primer modelo que conteste (principal, luego respaldo)."""
        ultimo = None
        for modelo in self._disponibles():
            try:
                return self._llamar(modelo, img)
            except (SinCredito, TiempoAgotado):
                raise
            except ModeloNoDisponible as e:
                self._retirados.add(modelo)
                ultimo = e
            except Exception as e:
                ultimo = e
        raise ultimo

    def _leer_con(self, modelo: str, img: bytes, pagina: int):
        """(datos, modelo real, consumos) de un modelo concreto."""
        consumos = []
        ultimo_texto = ""
        tope = None
        for _ in range(3):  # Gemini a veces emite JSON invalido; reintentar
            try:
                resp = self._llamar(modelo, img, tope)
            except (SinCredito, ModeloNoDisponible):
                raise
            except Exception as e:
                raise ErrorLectura(str(e), consumos) from e
            # Los reintentos tambien se pagan: se suman todos.
            real, entrada, salida = _consumo(resp)
            consumos.append((real or modelo, entrada, salida))
            if getattr(resp, "stop_reason", None) == "refusal":
                # Claude se ha negado a leerla: volver a pedirla daria lo
                # mismo. La lee la otra IA (doble lectura o respaldo).
                raise ErrorLectura(
                    f"{nombre_ia(modelo)} no ha querido leer esta hoja "
                    f"(pag {pagina}).", consumos)
            ultimo_texto = resp.text or ""
            datos = _parse_json_tolerante(ultimo_texto)
            if isinstance(datos, dict):
                if es_claude(modelo):
                    datos = _vacios_a_null(datos)
                return datos, (real or modelo), consumos
            if _cortada_por_el_tope(resp):
                tope = MAX_TOKENS_AMPLIADO
        raise ErrorLectura(
            f"No se pudo leer el JSON de {nombre_ia(modelo)} (pag {pagina}): "
            f"{ultimo_texto[:200]}", consumos)

    def _claude_parado(self) -> bool:
        """Claude ha pedido parar (cuota o límite de gasto) en este bloque."""
        return bool(self._sin_cuota.get(PROVEEDOR_CLAUDE))

    def _disponibles(self) -> List[str]:
        # Claude, si ha pedido parar, deja de contar para el resto del
        # bloque: lee la pareja de Gemini, como con Gemini elegido. (Gemini
        # sin cuota sigue como siempre: sus hojas quedan en rojo para volver
        # a leerlas.)
        claude_parado = self._claude_parado()
        return [m for m in self.modelos if m not in self._retirados
                and not (claude_parado and es_claude(m))]

    # ------------------------------------------ lo que Claude no ha leído
    def _apuntar_fallo_claude(self, motivo: str, definitivo: bool = False) -> None:
        """El motivo para el aviso: el primero, salvo que llegue uno que deja
        a Claude fuera el resto del bloque (sin saldo, clave mala, límite):
        ese es el que importa."""
        with self._cerrojo:
            if definitivo and not self._motivo_claude_definitivo:
                self._motivo_claude = str(motivo or "")[:300]
                self._motivo_claude_definitivo = True
            elif not self._motivo_claude:
                self._motivo_claude = str(motivo or "")[:300]

    def aviso_claude(self) -> str:
        """Para la ventana: cuántas hojas no ha leído Claude en este bloque y
        por qué (vacío si las ha leído todas o si no se lee con Claude)."""
        if not self._hojas_sin_claude:
            return ""
        motivo = self._motivo_claude or "Claude no estaba disponible."
        return (f"Claude no ha leído {self._hojas_sin_claude} hoja(s) de este "
                f"bloque; las ha leído Gemini. Motivo: {motivo}")

    def _leer_uno(self, img: bytes, pagina: int, empezar_por: int = 0):
        """Lee con el primer modelo disponible, saltando los retirados."""
        disponibles = self._disponibles()[empezar_por:]
        ultimo = None
        consumos = []
        for modelo in disponibles:
            try:
                datos, real, gastado = self._leer_con(modelo, img, pagina)
                return datos, real, consumos + gastado
            except SinCredito as e:
                # Lo pagado a un modelo anterior (una lectura de Claude que no
                # valio) tambien cuenta aunque se pare.
                e.consumos = consumos + list(getattr(e, "consumos", None) or [])
                raise
            except ModeloNoDisponible as e:
                self._retirados.add(modelo)
                ultimo = e
                if es_claude(modelo):
                    self._apuntar_fallo_claude(str(e), definitivo=True)
            except ErrorLectura as e:
                consumos.extend(e.consumos)
                ultimo = e
                if es_claude(modelo):
                    self._apuntar_fallo_claude(
                        str(e), definitivo=self._claude_parado())
        if ultimo is None:
            ultimo = ModeloNoDisponible("No hay ningún modelo de lectura disponible.")
        raise ErrorLectura(str(ultimo), consumos)

    # --------------------------------------------------------------- lectura
    def extraer(self, img: bytes, origen: str = "", pagina: int = 0) -> DatosFactura:
        from .doble_lectura import combinar, es_dudosa

        disponibles = self._disponibles()
        modo = self.modo_doble if len(disponibles) >= 2 else DOBLE_NO
        consumos: list = []

        if modo == DOBLE_SIEMPRE:
            from concurrent.futures import ThreadPoolExecutor
            sin_credito = None
            with ThreadPoolExecutor(max_workers=2) as ex:
                futuros = [ex.submit(self._leer_con, m, img, pagina)
                           for m in disponibles[:2]]
                resultados = []
                for modelo, fut in zip(disponibles[:2], futuros):
                    try:
                        datos, real, gastado = fut.result()
                        consumos.extend(gastado)
                        resultados.append((datos, real, ""))
                    except SinCredito as e:
                        # Se para, pero después de recoger la otra lectura:
                        # ya está pagada y su gasto tiene que contar.
                        sin_credito = sin_credito or e
                        resultados.append((None, modelo, str(e)))
                    except ModeloNoDisponible as e:
                        self._retirados.add(modelo)
                        resultados.append((None, modelo, str(e)))
                        if es_claude(modelo):
                            self._apuntar_fallo_claude(str(e), definitivo=True)
                    except Exception as e:
                        # ErrorLectura… o cualquier rareza de ESTA lectura:
                        # la del otro modelo puede ser buena y no se tira.
                        consumos.extend(getattr(e, "consumos", None) or [])
                        resultados.append((None, modelo, str(e)[:300]))
                        if es_claude(modelo):
                            self._apuntar_fallo_claude(
                                str(e), definitivo=self._claude_parado())
            if sin_credito is not None:
                sin_credito.consumos = list(consumos)
                raise sin_credito
            (d1, m1, e1), (d2, m2, e2) = resultados
            if d1 is None and d2 is None:
                raise ErrorLectura(e1 or e2, consumos)
            if d1 is None:
                crudo = combinar(d2, None, m2, "", error_2=e1)
            elif d2 is None:
                crudo = combinar(d1, None, m1, "", error_2=e2)
            else:
                crudo = combinar(d1, d2, m1, m2)
        else:
            d1, m1, gastado = self._leer_uno(img, pagina)
            consumos.extend(gastado)
            crudo = combinar(d1, None, m1, "")
            # Lo combinado, no lo leído tal cual: ya viene saneado («false»
            # escrito como texto no es «hay importes a mano»).
            if modo == DOBLE_DUDOSAS and es_dudosa(crudo):
                otro = next((m for m in self._disponibles() if m != self._base(m1)), None)
                if otro:
                    try:
                        d2, m2, gastado = self._leer_con(otro, img, pagina)
                        consumos.extend(gastado)
                        crudo = combinar(d1, d2, m1, m2)
                    except SinCredito as e:
                        # La primera lectura ya está pagada: cuenta.
                        e.consumos = list(consumos)
                        raise
                    except Exception as e:
                        # ErrorLectura… o cualquier rareza de la segunda: la
                        # primera ya está leída (y pagada) y no se tira.
                        consumos.extend(getattr(e, "consumos", None) or [])
                        crudo = combinar(d1, None, m1, "", error_2=str(e)[:300])

        if any(es_claude(m) for m in self.modelos) and not any(
                es_claude(crudo.get(c)) for c in ("_modelo_1", "_modelo_2")):
            # Se leía con Claude y esta hoja la ha leído solo Gemini: se
            # cuenta para avisar al acabar el bloque (no en silencio).
            with self._cerrojo:
                self._hojas_sin_claude += 1

        return DatosFactura(
            crudo=crudo, origen=origen, pagina=pagina,
            modelo=crudo.get("_modelo_1", ""),
            tokens_entrada=sum(c[1] for c in consumos),
            tokens_salida=sum(c[2] for c in consumos),
            consumos=consumos)

    def _base(self, modelo_real: str) -> str:
        """El modelo configurado al que corresponde un nombre real con cola."""
        real = str(modelo_real or "").replace("models/", "")
        return next((m for m in self.modelos if real.startswith(m)), real)


def _consumo(resp):
    """(modelo real, tokens de entrada, tokens de salida) de una respuesta.

    Se lee con cuidado: si el SDK cambia estos campos, el programa tiene que
    seguir leyendo facturas aunque no pueda contar el gasto.
    """
    modelo = str(getattr(resp, "model_version", "") or "")
    uso = getattr(resp, "usage_metadata", None)

    def _n(nombre):
        try:
            return int(getattr(uso, nombre, 0) or 0)
        except (TypeError, ValueError):
            return 0

    # El "pensamiento" de los modelos nuevos se factura como salida.
    return modelo, _n("prompt_token_count"),         _n("candidates_token_count") + _n("thoughts_token_count")


def _cortada_por_el_tope(resp) -> bool:
    """Si Gemini dejó de escribir por el tope de tokens de salida."""
    try:
        motivo = resp.candidates[0].finish_reason
    except Exception:
        return False
    return str(getattr(motivo, "value", motivo) or "").upper().endswith("MAX_TOKENS")


def _entero_json(cifras: str):
    # Un entero de más de 15 cifras no es un importe, y con más de 4300
    # json.loads lanzaba ValueError, que no es un JSON roto: se saltaba los
    # reintentos y tiraba también la otra lectura, que era buena. Se queda
    # como texto: puede ser un nº de factura sin comillas (los de las
    # eléctricas tienen 16-20 cifras); donde va un importe, el saneado lo
    # deja en blanco y avisa.
    return int(cifras) if len(cifras.lstrip("-")) <= 15 else cifras


def _decimal_json(texto: str):
    numero = float(texto)          # «1e999» o 400 cifras: infinito
    return numero if math.isfinite(numero) else None


def _cargar_json(texto: str):
    """json.loads sin NaN, Infinity, 1e999 ni enteros enormes: quedan en null."""
    return json.loads(texto, parse_constant=lambda _literal: None,
                      parse_int=_entero_json, parse_float=_decimal_json)


def _parse_json_tolerante(texto: str):
    """Intenta parsear el JSON de Gemini, tolerando fallos habituales.

    Nunca lanza: lo que no se entiende es None y la hoja se vuelve a pedir
    (un JSON con miles de niveles anidados daba RecursionError)."""
    if not texto:
        return None
    try:
        return _cargar_json(texto)
    except RecursionError:
        return None
    except ValueError:             # JSONDecodeError incluido
        pass
    t = texto.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    ini, fin = t.find("{"), t.rfind("}")
    if ini != -1 and fin != -1:
        t = t[ini:fin + 1]
    t = re.sub(r",\s*([}\]])", r"\1", t)
    try:
        return _cargar_json(t)
    except (ValueError, RecursionError):
        return None


def _num(v):
    """El número leído, o None si no lo es o no puede ser un importe (NaN,
    infinito, 1e999, 10**400 o más de mil millones: ver importe_posible)."""
    n = _num_leido(v)
    return n if n is not None and importe_posible(n) else None


def _num_leido(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            return float(v)
        except OverflowError:       # un entero de cientos de cifras
            return None
    t = str(v).strip().replace("€", "").replace(" ", "")
    # Signo DETRAS del numero: Coca-Cola imprime asi los abonos ("15,51-" son
    # MENOS 15,51). Sin esto float() petaba y el importe se perdia entero.
    negativo = t.endswith("-")
    if negativo:
        t = t[:-1]
    if "," in t and "." in t:      # 1.234,56 -> el punto son los miles
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
    try:
        n = float(t)
    except ValueError:
        return None
    return -n if negativo else n
