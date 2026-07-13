"""Procesa un PDF (o carpeta) de facturas escaneadas y genera gastos.xlsx y
ventas.xlsx listos para importar en Aplifisa. Autodetecta el cliente por NIF.

Uso:
  python scripts/procesar_pdf.py "ruta.pdf"

La API key se toma de GEMINI_API_KEY (o del almacen seguro).
Guarda una cache JSON para no volver a llamar a Gemini en cada ejecucion.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from facturas_excel.claves import leer_api_key
from facturas_excel.config_columnas import leer_config
from facturas_excel.exportar import exportar_excel
from facturas_excel.extraccion import Extractor
from facturas_excel.pdf import cargar_imagenes
from facturas_excel.procesar import construir, detectar_cliente
from facturas_excel.validacion import validar

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESCRITORIO = os.path.join(os.path.expanduser("~"), "Desktop")


def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/procesar_pdf.py \"ruta_al_pdf_de_facturas.pdf\"")
        return
    ruta = sys.argv[1]

    api_key = leer_api_key()
    if not api_key:
        print("Falta la API key (GEMINI_API_KEY o almacen seguro).")
        return

    cache_path = os.path.join(RAIZ, "cache2_" +
                              os.path.splitext(os.path.basename(ruta))[0] + ".json")
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            cache = json.load(fh)

    print("Renderizando paginas...")
    imagenes = cargar_imagenes([ruta], dpi=150)
    print(f"{len(imagenes)} paginas.")

    extractor = Extractor(api_key)
    registros = []  # (origen, pagina, datos)
    for origen, pagina, png in imagenes:
        clave = f"{os.path.basename(origen)}#{pagina}"
        if clave in cache:
            datos = cache[clave]
        else:
            print(f"  Gemini -> pagina {pagina}...")
            datos = extractor.extraer(png, origen, pagina).crudo
            cache[clave] = datos
            with open(cache_path, "w", encoding="utf-8") as fh:
                json.dump(cache, fh, ensure_ascii=False, indent=2)
            time.sleep(1)
        registros.append((origen, pagina, datos))

    # Autodetectar cliente
    nombre_cli, nif_cli = detectar_cliente([d for _, _, d in registros])
    print(f"\nCliente detectado: {nombre_cli}  (NIF {nif_cli})")

    gastos, ventas, resumen = [], [], []
    for origen, pagina, datos in registros:
        pr = construir(datos, nif_cli, nombre_cli, origen, pagina)
        (gastos if pr.tipo == "gasto" else ventas).extend(pr.facturas)
        estado = validar(pr.facturas[0]).estado
        if pr.aviso and estado == "ok":
            estado = "revisar"
        sub = f"/{pr.gxx}" if pr.gxx else ""
        resumen.append((pagina, pr.tipo, pr.cuenta, sub, estado,
                        datos.get("num_factura"), pr.facturas[0].nombre))

    cfg_g = leer_config(os.path.join(RAIZ, "config", "gastos.xml"))
    cfg_v = leer_config(os.path.join(RAIZ, "config", "ingresos.xml"))
    if gastos:
        exportar_excel(gastos, cfg_g, os.path.join(ESCRITORIO, "gastos.xlsx"))
    if ventas:
        exportar_excel(ventas, cfg_v, os.path.join(ESCRITORIO, "ventas.xlsx"))

    print("\n===== RESUMEN =====")
    for pag, tipo, cuenta, sub, estado, num, nombre in resumen:
        print(f"  p{pag:>2} [{tipo:5}] {estado:7} cta {cuenta}{sub:5} {num}  {nombre}")
    print(f"\nGastos: {len(gastos)} lineas  |  Ventas: {len(ventas)} lineas")
    base_g = sum(f.base_iva or 0 for f in gastos)
    base_v = sum(f.base_iva or 0 for f in ventas)
    print(f"Suma bases gastos: {base_g:.2f}  |  Suma bases ventas: {base_v:.2f}")
    print("Generados en el Escritorio: gastos.xlsx / ventas.xlsx")


if __name__ == "__main__":
    main()
