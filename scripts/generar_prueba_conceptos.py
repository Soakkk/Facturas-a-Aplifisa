"""Experimento para descubrir QUE valor quiere el gestor en la columna 'Concepto'
para caer en una cuenta+subclave concreta (ej. 628 G17 telefonia/internet).

Cada fila lleva un formato candidato distinto en la columna Concepto (C).
Importa el Excel en el gestor (config COMPRAS/GASTOS), abre cada apunte y anota
en que Concepto ha caido cada fila. El nº de factura A-1..A-6 identifica la fila.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from facturas_excel.config_columnas import leer_config
from facturas_excel.exportar import exportar_excel
from facturas_excel.modelo import Factura

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESCRITORIO = os.path.join(os.path.expanduser("~"), "Desktop")

# objetivo de la prueba: telefonia/internet = 628 (G17)
CANDIDATOS = ["628", "G17", "628 G17", "628G17", "G17 628", "SUMINISTROS TELEFONIA E INTERNET"]


def main():
    cfg = leer_config(os.path.join(RAIZ, "config", "gastos.xml"))
    facturas = []
    for i, cand in enumerate(CANDIDATOS, start=1):
        facturas.append(Factura(
            num_factura=f"A-{i}", fecha="15/03/2026", fecha_operacion="15/03/2026",
            concepto=cand, base_iva=100.0, pct_iva=21, cuota_iva=21.0,
            nif="12345678Z", nombre=f"PRUEBA FILA {i} [{cand}]",
        ))
    ruta = os.path.join(ESCRITORIO, "PRUEBA_conceptos.xlsx")
    exportar_excel(facturas, cfg, ruta)
    print("Generado:", ruta)
    print("\nQue lleva la columna Concepto en cada fila:")
    for i, cand in enumerate(CANDIDATOS, start=1):
        print(f"  A-{i}: {cand!r}")


if __name__ == "__main__":
    main()
