# Fiabilidad y muestras locales — plan de implementación

**Objetivo:** corregir los riesgos prioritarios del análisis aprobado por el usuario y conservar ejemplos reales localmente con exportación ZIP explícita.
**Diseño aprobado:** validación conjunta de facturas, detección de duplicados completos, unión conservadora de páginas complementarias, identidad y cuentas coherentes; guardar documentos y sus lecturas/correcciones en Windows, generar ZIP para adjuntar al asistente.
**Arquitectura:** módulo de controles por documento compartido por la tabla y exportación. Identificador persistente por documento, manteniendo el formato de filas del Excel. Módulo independiente de muestras locales con escrituras atómicas y archivos deduplicados por contenido.
**Tecnología:** Python, PySide6, pytest; sin nuevas dependencias de ejecución.
**Restricciones:** catálogo existente; no cambiar modelo IA; no incluir datos reales en Git; no publicar instalador automáticamente; compatibilidad con sesiones antiguas.

## 1. Controles por documento
- [x] Añadir pruebas de edición 231→341, duplicado parcial, eliminación parcial, cuenta incompatible y corrección propagada. Ejecutar y observar fallos.
- [x] Añadir `documento_id` no exportable a Factura; construir lo asigna a todas sus líneas. `control_facturas.py` agrupa, comprueba integridad e identifica duplicados/conflictos.
- [x] Conectar controles a `_revalidar_todo`, invalidar revisiones de líneas relacionadas, retirar avisos aritméticos antiguos; `a_total_factura` actualiza el número de líneas.
- [x] Ejecutar pruebas nuevas y módulos existentes del núcleo.

## 2. Identidad y páginas
- [x] Probar NIF contradictorio del cliente, sustituciones ajenas, números distintos con marcadores inicio/final y páginas fiscales sin identificación.
- [x] Impedir unión automática con NIF/números incompatibles, conservar unión de hoja fiscal sin identidad con aviso revisable y cerrar la secuencia al llegar al final. Sustituciones exigen identidad y tipo coherentes.
- [x] Ejecutar pruebas de multipágina, cliente, sustituciones y flujo.

## 3. Muestras reales
- [x] Probar copia inmutable, deduplicación, lecturas por página, snapshots corregidos, ZIP y fallo de escritura con temporales.
- [x] Crear `muestras_revision.py`: `guardar_original(ruta)`, `guardar_lecturas(registros)`, `guardar_revision(filas)`, `exportar_zip(destino)`; almacenamiento en `%APPDATA%/FacturasAplifisa/muestras_revision`.
- [x] Conectar al escaneo antes de IA, al resultado de lectura y al guardado/cierre/vaciado/exportación. Menú Ayuda para carpeta y ZIP. Guardar las páginas recibidas incluso si no se identifican; errores de disco visibles, sin perder la cola.
- [x] Documentar uso y probar integración con datos ficticios.

## 4. Verificación y entrega
- [x] Ejecutar núcleo, regresiones y batería completa con aislamiento de datos de pruebas; distinguir limitaciones de Windows.
- [x] Revisar diff y compatibilidad; revisión independiente de código y resolver observaciones.
- [x] Crear commit y entregar parche/instrucciones y resumen de validación. Publicación del instalador queda como paso separado.

## Evidencia de ejecución

310 pruebas completas aprobadas en macOS antes de la entrega, con cinco avisos conocidos de SWIG. Revisión independiente detectó y se corrigieron enlaces a originales reutilizados, pérdida de decisiones humanas y continuidad entre tres partes. Pruebas remotas Windows aprobadas. Publicación autorizada por el usuario; instalador generado mediante el flujo oficial de etiquetas.
