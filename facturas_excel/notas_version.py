"""Notas de parche mostradas una vez tras instalar cada versión."""

from __future__ import annotations

from . import ajustes


NOTAS = {
    "1.13.0": """
<h2>Novedades de la versión 1.13.0</h2>
<ul>
  <li><b>Cola para lotes grandes:</b> puede añadir más PDF mientras Gemini
      trabaja; se procesan por turnos sin bloquear el lote completo.</li>
  <li><b>PDF largos por partes:</b> un documento de 100 páginas se divide
      automáticamente en 4 bloques de 25 mediante PyMuPDF.</li>
  <li><b>Excel consolidado y parciales:</b> se crea el archivo completo para
      importar en Aplifisa y un Excel de control por cada parte.</li>
  <li><b>Gemini con límite de espera:</b> una página atascada termina como
      incidencia y la cola continúa con las siguientes.</li>
  <li><b>Sesión, archivo y revisión:</b> se mantienen las mejoras de guardado
      por cliente/ejercicio, recuperación del trabajo y revisión manual.</li>
</ul>
<p><b>Importante:</b> en Aplifisa importe solo el Excel consolidado. Los
Excel por partes son para control o recuperación.</p>
""",
}


def contenido(version: str) -> str:
    return NOTAS.get(version, "<h2>Novedades</h2><p>Mejoras y correcciones.</p>")


def ya_vistas(version: str) -> bool:
    return ajustes.leer("notas_version_vistas", "") == version


def marcar_vistas(version: str) -> None:
    ajustes.guardar("notas_version_vistas", version)
