"""Texto que se puede escribir en cualquier sitio (Excel, XML, PDF, ficheros).

Algunos nombres llegan con un carácter de control invisible en lugar de la
letra con tilde («JOS?» por «JOSÉ»): es lo que da el texto copiado de un PDF
cuya letra no trae su tabla de caracteres (cada documento usa un código
distinto). El .xlsx es XML y no los admite: openpyxl se negaba a escribir la
celda y la exportación entera fallaba (errores.log del 08 y 09/10/2026).
"""

from __future__ import annotations

import re
import unicodedata
from itertools import groupby

# Los que el XML de un .xlsx no admite y no son un espacio: se quitan. También
# los no-caracteres y las mitades sueltas de un par UTF-16 (el Excel se guarda
# pero luego no se puede volver a abrir).
_INVISIBLES = re.compile("[\x00-\x08\x0e-\x1b￾￿\ud800-\udfff]")
# Separadores de control que Excel tampoco admite: valen como un espacio (la
# 1.24.0 ya los convertía en espacio al recortar el nombre).
_COMO_ESPACIO = re.compile("[\x0b\x0c\x1c-\x1f]")


def tiene_invisibles(texto) -> bool:
    return bool(texto) and _INVISIBLES.search(str(texto)) is not None


def sin_invisibles(texto: str) -> str:
    return _INVISIBLES.sub("", _COMO_ESPACIO.sub(" ", texto))


def limpiar(texto):
    """(texto limpio, si traía algún invisible). Lo que no es texto, tal cual."""
    if not isinstance(texto, str):
        return texto, False
    habia = tiene_invisibles(texto)
    limpio = sin_invisibles(texto)
    if limpio != texto:
        limpio = " ".join(limpio.split())
    return limpio, habia


def visible(texto) -> str:
    """Para enseñarlo: el invisible como «·» (se ve dónde estaba)."""
    return _INVISIBLES.sub("·", _COMO_ESPACIO.sub(" ", str(texto or "")))


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn").upper()


def reparar(roto, candidatos):
    """El nombre bueno de entre los conocidos (del MISMO NIF) que encaja con
    el roto poniendo «una letra o ninguna» donde está cada invisible. Si
    encajan dos nombres distintos, ninguno: lo decide una persona. Dos que
    solo se diferencian en la tilde son el mismo: gana el que la lleva."""
    if not tiene_invisibles(roto):
        return None
    # Cada tanda de invisibles seguidos es un hueco de «ninguna a n letras»;
    # lo demás, tal cual. Ver _encaja.
    trozos = [(len(trozo), "") if invisible else (0, trozo)
              for invisible, trozo in (
                  (k, "".join(g)) for k, g in groupby(
                      _sin_tildes(_COMO_ESPACIO.sub(" ", str(roto))),
                      key=lambda c: _INVISIBLES.match(c) is not None))]
    # El propio roto sin el carácter no es «el bueno»: es el nombre al que le
    # falta la letra (aprendido, por ejemplo, al exportar esa misma fila).
    sin_letra = " ".join(sin_invisibles(str(roto)).split()).upper()
    buenos = {}
    for candidato in candidatos or ():
        candidato = str(candidato or "").strip()
        if not candidato or tiene_invisibles(candidato):
            continue
        if " ".join(candidato.split()).upper() == sin_letra:
            continue
        base = _sin_tildes(candidato)
        if _encaja(trozos, base):
            actual = buenos.get(base)
            tildes = sum(1 for c in candidato if ord(c) > 127)
            if actual is None or tildes > sum(1 for c in actual if ord(c) > 127):
                buenos[base] = candidato
    return next(iter(buenos.values())) if len(buenos) == 1 else None


def _encaja(trozos, texto: str) -> bool:
    """Si `texto` es la sucesión de los trozos: un literal, o un hueco de 0 a
    n letras (que no sean un salto de línea, como el «.» de antes).

    Antes era una expresión regular con un «.{0,n}» por tanda, y con nombres
    como «A·A·A·…» frente a un candidato «AAAA…B» retrocedía de forma
    exponencial: con 28 tandas, 5 s parado (fuzzing, 09/10/2026). Aquí se
    lleva el conjunto de posiciones a las que se puede llegar, que nunca pasa
    de len(texto) + 1: el coste es como mucho letras × huecos."""
    largo = len(texto)
    if sum(len(literal) for _hueco, literal in trozos) > largo:
        return False
    posiciones = {0}
    for hueco, literal in trozos:
        if literal:
            posiciones = {p + len(literal) for p in posiciones
                          if texto.startswith(literal, p)}
        else:
            nuevas = set()
            for p in posiciones:
                nuevas.add(p)
                for q in range(p, min(p + hueco, largo)):
                    if texto[q] == "\n":
                        break
                    nuevas.add(q + 1)
            posiciones = nuevas
        if not posiciones:
            return False
    return largo in posiciones


def escapar_invisibles(texto: str) -> str:
    """Para errores.log: el carácter de control escrito como \\x01, que al
    copiarlo y pegarlo no se pierde."""
    return "".join(c if c in "\n\t" or ord(c) >= 32 else f"\\x{ord(c):02x}"
                   for c in str(texto))
