"""Texto que se puede escribir en cualquier sitio (Excel, XML, PDF).

Algunos nombres llegan con un carácter de control invisible en lugar de la
letra con tilde («JOS?» por «JOSÉ»). El .xlsx es XML y no los admite: openpyxl
se negaba a escribir la celda y la exportación entera fallaba.
"""

from __future__ import annotations

import re

# Los caracteres de control que no admite el XML de un .xlsx (los mismos que
# rechaza openpyxl): todos los de 0 a 31 salvo el tabulador y los saltos.
_INVISIBLES = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def tiene_invisibles(texto) -> bool:
    return bool(texto) and _INVISIBLES.search(str(texto)) is not None


def sin_invisibles(texto: str) -> str:
    return _INVISIBLES.sub("", texto)
