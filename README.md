# Facturas a Aplifisa

App de escritorio (Windows) para asesorías: lee **facturas escaneadas** con IA
(Google Gemini), detecta automáticamente al cliente, clasifica cada factura como
**gasto o venta** con su **cuenta contable (PGC PYMES)**, y genera el **Excel**
que importa el programa de gestión fiscal **Aplifisa** (Apuntes → Captura masiva
→ Desde fichero Excel).

## Flujo

1. **Cargar facturas** (PDF escaneado o imágenes) — entran en una cola y cada
   bloque se procesa en paralelo. Los PDF largos se dividen internamente en
   partes internas de 25 páginas; pueden añadirse más documentos mientras la cola sigue.
   Esas partes son temporales, se eliminan al terminar y nunca aparecen en la
   documentación del cliente.
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
4. **Exportar** `GASTOS_CLIENTE.xlsx` / `INGRESOS_CLIENTE.xlsx` al Escritorio
   → importar en Aplifisa con la
   configuración de columnas incluida (`config/gastos.xml` / `ingresos.xml`).
   Aunque el PDF tenga 100 páginas o varios bloques, solo se genera el Excel
   consolidado que se importa en Aplifisa. Al comprobarlo correctamente, se
   eliminan los Excel temporales `parte_N_de_M` de ese cliente y tipo.
   Los duplicados, documentos sustituidos, suplidos y bienes de inversión se
   apartan de la exportación rutinaria para tratarlos manualmente.
5. Tanto los PDF creados desde el escáner como los cargados desde HP u otro
   programa quedan archivados automáticamente en el Escritorio como
   `Documentación Facturas / Cliente / Ejercicio / Gastos` o `Ingresos`. Los
   PDF externos se copian y su original no se mueve. Las dos carpetas se crean
   juntas y el ejercicio se obtiene de la fecha de factura. Los Excel no forman
   parte de este archivo permanente.
   Desde **Escaneos guardados** se puede crear el ZIP completo del ejercicio
   para adjuntarlo después como documentación digitalizada en Aplifisa.
6. El lote en curso se conserva al cerrar el programa, incluidas las
   correcciones y los bloques acumulados. Solo **Vaciar todo** inicia una sesión
   nueva. Los CIF/NIF/DNI corregidos manualmente se recuerdan por cliente o
   proveedor. Si una nueva lectura válida los contradice, no se cambia la
   memoria automáticamente: una discrepancia queda amarilla y, si tres o más
   facturas coinciden en el nuevo valor, el programa pide confirmación una sola
   vez. Los tickets de contado sin identificador siguen en amarillo.

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
