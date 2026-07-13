"""Genera Excels de PRUEBA con datos ficticios para validar que el gestor
fiscal los importa bien. Crea, para gastos, dos variantes:

  - PRUEBA_gastos_TEXTO_coma.xlsx  (numeros como texto: 1234,56)
  - PRUEBA_gastos_NUMERO.xlsx      (numeros reales de Excel: 1234.56)

Importa las dos en el gestor (config de COMPRAS/GASTOS) y dinos cual carga
los importes correctamente. Igual para ventas.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from facturas_excel.config_columnas import leer_config
from facturas_excel.exportar import MODO_NUMERO, MODO_TEXTO, exportar_excel
from facturas_excel.modelo import Factura

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESCRITORIO = os.path.join(os.path.expanduser("~"), "Desktop")


def facturas_gastos():
    return [
        Factura(
            num_factura="A-2025/114", fecha="15/03/2026", fecha_operacion="15/03/2026",
            concepto="Material de oficina", base_iva=100.00, pct_iva=21, cuota_iva=21.00,
            nif="B73123456", nombre="Suministros Murcia SL", total_impreso=121.00,
        ),
        Factura(
            num_factura="2026-0087", fecha="02/04/2026", fecha_operacion="02/04/2026",
            concepto="Reparacion vehiculo", base_iva=250.50, pct_iva=21, cuota_iva=52.61,
            nif="30012345Z", nombre="Talleres Lopez", total_impreso=303.11,
        ),
        Factura(
            num_factura="FRA-5521", fecha="20/04/2026", fecha_operacion="20/04/2026",
            concepto="Comida cliente", base_iva=45.45, pct_iva=10, cuota_iva=4.55,
            nif="B30999888", nombre="Restaurante El Puerto SL", total_impreso=50.00,
        ),
    ]


def main():
    cfg_gastos = leer_config(os.path.join(RAIZ, "config", "gastos.xml"))
    facturas = facturas_gastos()

    salidas = [
        (MODO_TEXTO, os.path.join(ESCRITORIO, "PRUEBA_gastos_TEXTO_coma.xlsx")),
        (MODO_NUMERO, os.path.join(ESCRITORIO, "PRUEBA_gastos_NUMERO.xlsx")),
    ]
    for modo, ruta in salidas:
        exportar_excel(facturas, cfg_gastos, ruta, modo_numeros=modo)
        print("Generado:", ruta)

    print("\nColumnas usadas (segun gastos.xml):")
    for campo, letra in sorted(cfg_gastos.columnas.items(), key=lambda x: x[1]):
        print(f"  {letra}: {campo}")


if __name__ == "__main__":
    main()
