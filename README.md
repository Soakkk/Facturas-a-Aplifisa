# Facturas a Aplifisa

App de escritorio (Windows) para asesorías: lee **facturas escaneadas** con IA
(Google Gemini), detecta automáticamente al cliente, clasifica cada factura como
**gasto o venta** con su **cuenta contable (PGC PYMES)**, y genera el **Excel**
que importa el programa de gestión fiscal **Aplifisa** (Apuntes → Captura masiva
→ Desde fichero Excel).

## Flujo

1. **Cargar facturas** (PDF escaneado o imágenes) — se procesan en paralelo.
   También se pueden arrastrar sobre la ventana o recibir directamente desde
   Escáner Fotos mediante `FacturasAplifisa.exe --import "lote.pdf"`.
2. El programa **detecta al cliente** (el NIF que se repite en el lote) y, por
   cada factura, decide si es **gasto** (el cliente recibe) o **venta** (el
   cliente emite) y quién es la contraparte.
3. **Tabla de revisión** con semáforo de control de calidad:
   - 🟢 todo cuadra (cuota = base × tipo, total coincide, NIF válido)
   - 🟡 revisar (confianza media/baja, NIF dudoso, rol ambiguo…)
   - 🔴 error (descuadres, faltan campos obligatorios)
   Con la **imagen de la factura al lado** para corregir al vuelo; al hacer clic
   se abre una vista previa grande. Una fila ámbar solo se exporta después de
   pulsar **Marcar revisada**.
4. **Exportar** `gastos.xlsx` / `ingresos.xlsx` → importar en Aplifisa con la
   configuración de columnas incluida (`config/gastos.xml` / `ingresos.xml`).
   Los duplicados, documentos sustituidos, suplidos y bienes de inversión se
   apartan de la exportación rutinaria para tratarlos manualmente.
5. Los PDF creados desde el escáner quedan archivados automáticamente como
   `Cliente / Ejercicio / Gastos` o `Cliente / Ejercicio / Ingresos`. Las dos
   carpetas se crean juntas y el ejercicio se obtiene de la fecha de factura.
   Desde **Escaneos guardados** se puede crear el ZIP completo del ejercicio
   para adjuntarlo después como documentación digitalizada en Aplifisa.
6. El lote en curso se conserva al cerrar el programa, incluidas las
   correcciones y los bloques acumulados. Solo **Vaciar todo** inicia una sesión
   nueva. Los Excel se nombran `CLIENTE_gastos.xlsx` y
   `CLIENTE_ingresos.xlsx`.

La interfaz sigue el mismo sistema visual que Generador de avisos fiscales:
cabecera azul marino, flujo por pasos, superficies claras y estados de revisión
visibles sin perder la imagen original.

## Requisitos

- Windows 10/11.
- **API key de Google Gemini** (aistudio.google.com), recomendable con
  facturación activada. Se guarda cifrada en el Almacén de credenciales de
  Windows (botón 🔑 de la app).

## Instalación y actualizaciones

Instalador en las [releases de Facturas a Aplifisa](https://github.com/Soakkk/Facturas-a-Aplifisa/releases).
La app comprueba actualizaciones al arrancar y se actualiza sola.

## Desarrollo

```
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m facturas_excel.app
```

Release (exe + instalador + subida a GitHub): `python scripts/release.py`

## Privacidad

Las facturas se envían a la API de Gemini solo para extraer sus datos. Con
facturación activada, Google no usa esos datos para entrenar modelos. Las
cachés y Excels generados quedan fuera del repositorio (`.gitignore`).
