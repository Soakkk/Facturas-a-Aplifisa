"""Prepara una orden segura para revisar el modelo de lectura con Codex.

La aplicacion no cambia de modelo por su cuenta: que uno sea mas nuevo o mas
barato no demuestra que lea mejor las facturas. Este modulo deja preparada una
solicitud reproducible para que Codex consulte las fuentes oficiales, conserve
la calidad como requisito y publique una actualizacion solo cuando proceda.
"""

from __future__ import annotations

import os

from .extraccion import MODELOS
from .rutas import dir_datos


FICHERO_SOLICITUD = "solicitud-revision-gemini.md"


def modelo_principal() -> str:
    return MODELOS[0]


def texto_solicitud(version_app: str) -> str:
    modelo = modelo_principal()
    return f"""Revisa el modelo de Gemini de mi proyecto público
Soakkk/Facturas-a-Aplifisa (aplicación instalada v{version_app}).

El modelo principal actual es {modelo}. Mi prioridad absoluta es mantener o
mejorar la calidad de lectura de las facturas; NO quiero bajar calidad para
ahorrar dinero ni cambiar de modelo solo porque exista uno más nuevo.

Haz lo siguiente:
1. Consulta únicamente la documentación oficial de Gemini para comprobar si
   {modelo} sigue disponible, su fecha de retirada y su precio actual.
2. Revisa si existe otro modelo estable, no preview, que pueda mejorar la
   lectura de facturas escaneadas. Compara también el coste, pero trátalo como
   información secundaria, nunca como motivo para perder calidad.
3. Comprueba la compatibilidad del SDK google-genai y actualiza la tabla de
   precios del programa si Google la ha cambiado.
4. Si el modelo actual continúa siendo la opción segura, no cambies nada y
   dímelo. Si conviene migrar, conserva el actual como respaldo mientras siga
   disponible, ejecuta todos los tests y publica la actualización mediante el
   procedimiento del repositorio. No uses aliases latest como modelo principal.
5. No incluyas facturas, nombres, NIF ni importes reales en el repositorio.
"""


def guardar_solicitud(version_app: str) -> tuple[str, str]:
    texto = texto_solicitud(version_app)
    ruta = os.path.join(dir_datos(), FICHERO_SOLICITUD)
    with open(ruta, "w", encoding="utf-8", newline="\n") as archivo:
        archivo.write(texto)
    return texto, ruta
