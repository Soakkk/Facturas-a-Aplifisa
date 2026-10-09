"""La lectura de Gemini, con la forma que espera el programa (1.26).

Gemini devuelve casi siempre lo que pide el ESQUEMA, pero no siempre: sin
esquema (el respaldo tras un error 400) o en una respuesta «desbocada» pueden
llegar listas donde va un texto, NaN o 10**400 donde va un importe, textos de
miles de caracteres, cientos de líneas de IVA o claves que el programa usa por
dentro. Una sola hoja así tiraba el bloque entero de 25 hojas ya pagadas,
paraba la cola, impedía guardar las muestras o, con una «última página» de mil
millones, llenaba la memoria al exportar (fuzzing «lecturas absurdas»,
09/10/2026).

A la entrada de la doble lectura (doble_lectura.combinar) cada dato queda con
su tipo, sus valores posibles y un tamaño máximo: los del ESQUEMA y las claves
internas que el programa conoce. Lo demás se quita. Lo que se corrige se
apunta en «_saneado» y la fila sale en ámbar diciendo qué (aviso_saneado).
"""

from __future__ import annotations

import math

from .extraccion import ESQUEMA, _num

_PROPIEDADES = ESQUEMA["properties"]

# Lo que se ve en el aviso: el asesor no tiene por qué saber cómo se llama
# cada dato por dentro.
ETIQUETAS = {
    "emisor_nombre": "nombre del emisor", "emisor_nif": "NIF del emisor",
    "receptor_nombre": "nombre del destinatario",
    "receptor_nif": "NIF del destinatario", "num_factura": "nº de factura",
    "fecha": "fecha", "fecha_operacion": "fecha de operación",
    "estado_pagina_factura": "qué hoja de la factura es",
    "lineas_iva": "desglose de IVA", "base_irpf": "base de la retención",
    "pct_irpf": "% de retención", "cuota_irpf": "retención",
    "suplidos": "suplidos", "es_bien_inversion": "bien de inversión",
    "total": "total", "sustituye_a": "factura a la que sustituye",
    "manuscrito_en_importes": "importes a mano",
    "cuenta_gasto": "cuenta de gasto", "subclave_gxx": "subclave de gasto",
    "cuenta_ingreso": "cuenta de ingreso",
    "subclave_ingreso": "subclave de ingreso", "concepto_texto": "concepto",
    "tipo_documento": "tipo de documento", "moneda": "moneda",
    "mencion_iva": "mención de IVA", "posible_no_deducible": "IVA no deducible",
    "confianza": "confianza",
}

# Tamaño máximo de cada texto. Por encima de los topes con los que se
# construye la fila (nombre 120, nº de factura 60): esos ya recortan y
# avisan solos; esto solo para lo desbocado (un nombre de 10.000 letras).
LARGO = {"num_factura": 200, "sustituye_a": 200, "emisor_nif": 40,
         "receptor_nif": 40, "fecha": 40, "fecha_operacion": 40, "moneda": 20,
         "cuenta_gasto": 100, "cuenta_ingreso": 100, "subclave_gxx": 40,
         "subclave_ingreso": 40}
LARGO_POR_DEFECTO = 300
NUMEROS_LINEA = ("base", "tipo_iva", "cuota_iva", "pct_requiv", "cuota_requiv")
# Las páginas de un PDF de verdad: una «última página» de mil millones creaba
# al exportar una lista así de larga (más de 2 GB).
PAGINA_MAXIMA = 10_000
_SI = {"true", "si", "sí", "yes", "1"}
_NO = {"false", "no", "0", ""}


# ------------------------------------------------------------ cada tipo
def _texto(valor, largo: int = LARGO_POR_DEFECTO):
    """(texto o None, corregido). Los caracteres invisibles NO se tocan aquí:
    de ellos se encargan texto.limpiar y texto.reparar al construir la fila."""
    if valor is None:
        return None, False
    if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
        return None, True                  # una lista o un dict no es un texto
    if isinstance(valor, float) and not math.isfinite(valor):
        return None, True
    if isinstance(valor, int) and abs(valor) >= 10 ** 30:
        return None, True                  # ni se puede pasar a texto entero
    texto = str(valor)
    if len(texto) > largo:
        return texto[:largo], True
    return texto, False


def _numero(valor):
    """(número o None, corregido): NaN, infinito, 10**400 o un billón no son
    importes de una factura (ver validacion.importe_posible)."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None, False
    if isinstance(valor, str) and len(valor) > 40:
        return None, True                  # 5000 cifras seguidas
    if not isinstance(valor, (str, int, float)) or isinstance(valor, bool):
        return None, True
    numero = _num(valor)
    return numero, numero is None


def _booleano(valor):
    """(sí/no, corregido). «false» escrito como texto NO es verdadero."""
    if valor is None or isinstance(valor, bool):
        return bool(valor), False
    if isinstance(valor, str) and valor.strip().lower() in _SI | _NO:
        return valor.strip().lower() in _SI, False
    if isinstance(valor, (int, float)) and valor in (0, 1):
        return bool(valor), False
    return False, True


def _opcion(valor, posibles):
    """(una de las opciones o None, corregido)."""
    if valor is None or valor == "":
        return None, False
    texto = valor.strip().lower() if isinstance(valor, str) else None
    if texto in posibles:
        return texto, False
    return None, True


def _lineas(valor):
    """(líneas de IVA con sus cinco importes, corregido)."""
    if valor is None:
        return [], False
    if not isinstance(valor, list):
        return [], True
    lineas, corregido = [], False
    for linea in valor:
        if not isinstance(linea, dict):
            corregido = True
            continue
        limpia = {}
        for campo in NUMEROS_LINEA:
            limpia[campo], mal = _numero(linea.get(campo))
            corregido = corregido or mal
        lineas.append(limpia)
    return lineas, corregido


def _del_esquema(clave: str, valor):
    """(valor saneado, corregido) de una clave del ESQUEMA, según su tipo."""
    propiedad = _PROPIEDADES[clave]
    tipos = propiedad.get("type")
    tipos = tipos if isinstance(tipos, list) else [tipos]
    if "enum" in propiedad:
        return _opcion(valor, propiedad["enum"])
    if "array" in tipos:
        return _lineas(valor)
    if "number" in tipos:
        return _numero(valor)
    if "boolean" in tipos:
        return _booleano(valor)
    return _texto(valor, LARGO.get(clave, LARGO_POR_DEFECTO))


# ------------------------------------------------------ claves internas
def _entero(valor, minimo=1, maximo=PAGINA_MAXIMA):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None, False
    if isinstance(valor, float) and not (math.isfinite(valor) and valor.is_integer()):
        return None, False
    return (int(valor), True) if minimo <= valor <= maximo else (None, False)


def _texto_corto(largo):
    def validar(valor):
        texto, corregido = _texto(valor, largo)
        return texto, isinstance(valor, str) and not corregido
    return validar


def _uno_de(*posibles):
    return lambda valor: (valor, True) if valor in posibles else (None, False)


def _lista(elemento, maximo):
    def validar(valor):
        if not isinstance(valor, (list, tuple)) or len(valor) > maximo:
            return None, False
        salida = []
        for x in valor:
            limpio, bueno = elemento(x)
            if not bueno:
                return None, False
            salida.append(limpio)
        return salida, True
    return validar


def _pagina_de(valor):
    """[origen, página] de una unión hecha a mano."""
    if not isinstance(valor, (list, tuple)) or len(valor) != 2:
        return None, False
    origen, bueno = _texto_corto(1000)(valor[0])
    pagina, bien = _entero(valor[1])
    return ([origen, pagina], True) if bueno and bien else (None, False)


def _escalar(valor):
    """Un valor de una diferencia de la doble lectura, tal como se leyó."""
    if valor is None or isinstance(valor, bool):
        return valor, True
    if isinstance(valor, (int, float)):
        return (valor, True) if _num(valor) is not None else (None, False)
    return _texto_corto(LARGO_POR_DEFECTO)(valor)


def _discrepancia(valor):
    from .doble_lectura import CAMPOS_COMPARADOS
    campos = {c for c, _ in CAMPOS_COMPARADOS} | {"lineas_iva"}
    campo = valor.get("campo") if isinstance(valor, dict) else None
    if not isinstance(campo, str) or campo not in campos:
        return None, False
    salida = {"campo": campo}
    for clave, validar in (("etiqueta", _texto_corto(100)),
                           ("valor_1", _escalar), ("valor_2", _escalar)):
        salida[clave], bueno = validar(valor.get(clave))
        if not bueno:
            return None, False
    for clave in ("lineas_1", "lineas_2"):
        if clave in valor:
            salida[clave] = _lineas(valor[clave])[0]
    return salida, True


def _lectura_2(valor):
    if not isinstance(valor, dict):
        return None, False
    otra = sanear(valor, internas=False)
    otra.pop("_saneado", None)
    return otra, True


# Las que pone el propio programa (combinar, unir hojas, el Worker), cada una
# con su forma. Cualquier otra que empiece por «_» se quita.
INTERNAS = {
    "_error": _texto_corto(300), "_error_2": _texto_corto(300),
    "_modelo_1": _texto_corto(100), "_modelo_2": _texto_corto(100),
    "_verificacion": _uno_de("simple", "doble", ""),
    "_lectura_2": _lectura_2,
    "_discrepancias": _lista(_discrepancia, 40),
    "_ultima_pagina_consolidada": _entero,
    "_estado_ultima_pagina": _uno_de(
        *_PROPIEDADES["estado_pagina_factura"]["enum"]),
    "_union_inferida": _uno_de(True, False),
    "_union_manual": _uno_de(True, False),
    "_motivo_union_inferida": _texto_corto(300),
    "_paginas_union_inferida": _lista(_entero, 500),
    "_paginas_union_manual": _lista(_pagina_de, 500),
    "_saneado": _lista(_texto_corto(300), 20),
}


# ------------------------------------------------------------ la lectura
def sanear(datos, internas: bool = True) -> dict:
    """La lectura con solo las claves del ESQUEMA y las internas conocidas,
    cada una con su tipo y su tamaño; en «_saneado», lo que se ha corregido."""
    if not isinstance(datos, dict):
        return {"_saneado": ["la lectura no era un objeto JSON"]}
    salida, notas, ajenas = {}, [], []
    for clave, valor in datos.items():
        if clave in _PROPIEDADES:
            salida[clave], corregido = _del_esquema(clave, valor)
            if corregido:
                notas.append(_nota(clave, valor))
        elif internas and clave in INTERNAS:
            limpio, bueno = INTERNAS[clave](valor)
            if bueno:
                salida[clave] = limpio
            else:
                notas.append(f"dato interno {clave} con otra forma")
        else:
            ajenas.append(str(clave)[:30])
    if ajenas:
        notas.append("datos de más: " + ", ".join(sorted(ajenas)[:5])
                     + ("…" if len(ajenas) > 5 else ""))
    notas = list(salida.pop("_saneado", None) or []) + notas
    if notas:
        salida["_saneado"] = notas[:20]
    return salida


def _nota(clave: str, valor) -> str:
    """Qué se ha corregido, con lo leído si es una opción corta."""
    nota = ETIQUETAS.get(clave, clave)
    if "enum" in _PROPIEDADES[clave] and isinstance(valor, str):
        from .texto import visible
        nota += f" «{visible(valor[:30])}»"
    return nota


def aviso_saneado(datos) -> str:
    """El aviso ámbar de una lectura que se ha tenido que sanear ("" si no)."""
    notas = datos.get("_saneado") if isinstance(datos, dict) else None
    if not notas or not isinstance(notas, list):
        return ""
    return ("La lectura de Gemini traía datos sin la forma esperada ("
            + "; ".join(str(n) for n in notas[:6])
            + ("…" if len(notas) > 6 else "")
            + "): se ha dejado en blanco, recortado o quitado lo que no "
            "encajaba. Compruébela con el documento.")
