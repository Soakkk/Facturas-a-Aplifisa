# Revisión de facturas completas y ejemplos reales

## Cambios de funcionamiento

- El total se comprueba sumando todas las líneas de la factura, también después de editar o eliminar una. Los descuadres del desglose y las facturas incompletas deben corregirse antes de exportar.
- Las copias idénticas se apartan completas. Si otra lectura del mismo número, NIF, ejercicio y tipo trae datos distintos, ambas quedan en conflicto; elimine la copia incorrecta completa después de compararlas.
- Una cuenta que no pertenece al catálogo de gasto/ingreso seleccionado impide exportar. Cambiar el tipo requiere comprobar también cuenta y contraparte.
- Las correcciones propagadas invalidan la revisión anterior de las facturas afectadas.
- La unión automática rechaza números o NIF contradictorios; una referencia de sustitución solo aparta un candidato compatible e inequívoco.

## Facturas con cabecera y resumen en hojas distintas

La primera hoja puede aportar identificación y la última únicamente base, IVA y total. Se mantiene la unión cuando hay continuidad de páginas y señales de inicio/continuación/final, sin datos contradictorios.

Si la unión depende de la continuidad y falta un número repetido, aparece un aviso para comprobar las páginas asociadas. Revise ambas hojas y marque la factura como revisada cuando haya confirmado que pertenecen al mismo documento. El cuadre de importes por sí solo no demuestra esa asociación.

La unión funciona también entre partes internas de 25 páginas. Si la factura anterior fue editada, revisada, eliminada o apartada, no se reconstruye automáticamente: se conserva la decisión y se indica la posible continuación. «Unir hojas» permite resolver los casos manualmente y conserva las correcciones de otras facturas del lote.

## Ejemplos reales para revisión

Al abrir un documento o recibirlo del escáner se guarda una copia local del original antes de llamar a Gemini. Se guardan también las lecturas recibidas por página y versiones de los datos corregidos con sus avisos. Una misma copia no se duplica por volver a guardarla.

Ubicación en Windows:

```
%APPDATA%\FacturasAplifisa\muestras_revision
```

En **Ayuda → Abrir carpeta de ejemplos para revisión** puede consultar el archivo.

En **Ayuda → Preparar ZIP de ejemplos para revisión…** elija dónde guardar el ZIP. Incluye el archivo de ejemplos acumulado: originales, imágenes de páginas, lecturas y revisiones. Adjunte ese ZIP a la conversación para que el asistente pueda examinar casos reales. Guardarlo no lo envía automáticamente.

Las revisiones se conservan después de cambios, al guardar/cerrar, antes de vaciar el lote y al preparar el ZIP. El archivo de ejemplos es independiente del lote: «Vaciar todo» no borra los ejemplos guardados. Si falta espacio o no se puede escribir, el programa lo avisa y permite continuar trabajando con las facturas.

Los JSON incluyen versión de aplicación y de formato. Cada factura conserva la identidad del original capturado, aunque se reutilice su ruta para otro escaneo. El ZIP no utiliza el fichero de sesión como único soporte: lecturas y revisiones son JSON legible.

## Verificación de desarrollo

Se añadieron pruebas de regresión de integridad, identidad, continuidad, conservación de decisiones humanas, captura de ejemplos y ZIP. Las pruebas utilizan un perfil temporal propio y datos ficticios; no modifican los datos reales del asesor.

Esta documentación describe cambios de la rama de desarrollo. Su disponibilidad en el programa instalado depende de publicar e instalar la versión correspondiente.
