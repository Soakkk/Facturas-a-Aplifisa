## Cómo va el programa y qué necesito de ti

Actualizado el 2 de septiembre de 2026 (versión 1.10.3). Apunta abajo lo que
veas y lo leo en la siguiente sesión de trabajo.

---

### Lo que se ha resuelto hoy (pruébalo)

**Escanear.** El botón «Escanear facturas» (Ctrl+E) maneja el alimentador de tu
HP, guarda el PDF en `Documentos\Facturas escaneadas\<CLIENTE>` con el nombre
puesto y lo mete solo en el lote. No hace falta ni decirle de quién es: lo
detecta por el NIF y coloca el PDF él solo. Eliges color (b/n, grises, color) y
calidad (75-300 ppp) en la misma ventana. En «Escaneos» (Ctrl+L) tienes todos
los PDF generados, para reabrirlos, recolocarlos o quitarlos de en medio.

**Varios PDF en un Excel.** Cada carga o escaneo es un «bloque» que se suma al
lote. Un requerimiento de 60 facturas se escanea en tres tandas y sale un solo
Excel. Cada bloque se puede quitar por separado, y «Vaciar todo» empieza de cero.

**Facturas que se pierden o se repiten.** Si el alimentador arrastra dos hojas
pegadas, esa factura no daba ningún aviso. Ahora salta por dos vías: el recuento
de hojas (si le dices cuántas pones) y el salto en la numeración («falta la
09/25»). Las repetidas siguen saliendo en rojo.

**Quién es tu cliente.** Con un taco de facturas del mismo proveedor las dos
partes salen las mismas veces y antes se elegía al azar. Ahora pregunta, se
acuerda de tu respuesta para siempre, y el botón «Cambiar cliente…» rehace el
lote sin volver a pagar la lectura.

**Las cuentas.** El programa lleva dentro tu catálogo de conceptos de Aplifisa
(gastos e ingresos, con sus subclaves) y Gemini elige de esa lista, no de una
idea general del PGC. Se comprueba que la pareja cuenta+subclave exista, y da
igual que Gemini conteste `628` o `628 (G16) SUMINISTROS GAS`. El gasóleo va a
628 (G16), como tú lo tienes. **La prestación de servicios va al 705** (al 700
solo la venta de género), y también cuando el respaldo por palabras clave tiene
que decidir sin Gemini.

**Suplidos.** Se leen los que la factura identifica como tales, van en su
columna, se suman al total sin mezclarse con la base ni el IVA, y se exportan al
campo Suplidos de Aplifisa. El cuadre del total ya cuenta con ellos.

**El resumen.** «Comprobación de totales por bloque» suma cada PDF por separado
y desglosa el IVA por tipos en la misma celda (`10%: 12,34 € · 21%: 56,78 €`).
Se puede ocultar (botón «Ocultar» o menú Ver). La miniatura del documento se
pulsa para verla grande.

**Lo que cuesta.** Abajo a la derecha: el modelo de Gemini, lo que ha costado el
lote y lo que llevas del mes. Un lote de 24 facturas costó 7 céntimos.

---

### Lo que me falta saber de ti

1. **¿Te falta alguna cuenta** de las que usas en el catálogo?

2. **Los pares de tipo y recargo.** ¿Son siempre IVA 21 % → 5,2 %, 10 % → 1,4 %
   y 4 % → 0,5 %? Si me lo confirmas, el programa caza solo los errores de
   lectura del recargo.

3. **Una factura que pone «Copia duplicada»**: ¿se registra igual o se descarta?
   Si se descarta, el programa puede detectar ese sello y avisarte, como ya hace
   con las sustituidas.

4. **Un proveedor que factura sin recargo** a un cliente que está en recargo de
   equivalencia: entiendo que también va por el total factura. ¿Correcto?

5. **Un proveedor con dos CIF en la cabecera** (dos sedes): ¿cuál es el bueno
   para la cuenta?

---

### Lo más útil que puedes hacer

**Cuadrar el total de un lote.** Compara el total que da el programa con el
tuyo. Si no cuadran, dímelo aunque no sepas por qué: así salió el abono que se
estaba registrando en positivo, y no lo habría encontrado de otra forma.

**Si algo sale en ámbar o en rojo y no debería**, dímelo con la factura delante
y con lo que pone el aviso (el «!» de la fila). Es más fácil afinar el criterio
con un caso real que adivinarlo.

---

### Cosas que ya sé y estoy mirando

- Al escanear se cuela a veces la banda de otra factura en la misma hoja: hay
  dos «TOTAL FACTURA» en la página y podría coger el que no es.
- Fotografiar con el móvil **no gasta más créditos**: encuadra llenando la foto
  con la factura y se leerá mejor sin pagar más.
- **Abanica el taco** antes de meterlo en el alimentador y no lo cargues muy
  alto: así arrastra menos hojas pegadas.
- Pendiente de valorar: el archivo digital ordenado por cliente, ejercicio, tipo
  y periodo; vigilar una carpeta para procesar solo lo que llegue (útil para las
  fotos del móvil); y que la app de Escáner Fotos mande aquí el PDF mejorado.
