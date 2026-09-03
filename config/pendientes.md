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

**Recargo de equivalencia.** Si el lote trae facturas con recargo, aparece
arriba un desplegable para decir cómo se registran las de ese cliente:
**minorista** (sin 303: cada gasto por el TOTAL de la factura) o **mayorista en
estimación directa** (con su desglose de IVA y recargo). Se pregunta la primera
vez, se recuerda por NIF y se puede cambiar cuando quiera: el lote se rehace al
momento sin volver a leer nada. Si el lote no tiene recargo, el desplegable ni
aparece. Además se comprueban los pares 21→5,2 / 10→1,4 / 4→0,5.

**Tus anotaciones a mano.** El programa ya distingue: el CIF que anotas cuando
no se lee, y la numeración que pones para los requerimientos, **se usan y no dan
aviso**. Solo avisa si lo escrito a mano toca a los IMPORTES (un total corregido
o una línea tachada), que ahí sí manda lo impreso. Antes avisaba de cualquier
anotación, y por eso te salían todas las facturas en ámbar.

**Lo que corriges a mano se queda guardado.** Si cambias el **nombre**, el
**NIF** o la **cuenta y subclave** de un proveedor, el programa lo recuerda para
ese proveedor y lo aplica al resto de sus facturas del lote y a las de los
próximos. Es lo mismo que hace Aplifisa cuando le dices el concepto de una
cuenta la primera vez. Lo escrito a mano manda: no lo pisa ninguna lectura.

**Contraste con tu registro de Aplifisa (botón «Comprobar registro», o Ctrl+R).**
Saca de Aplifisa el «Listado de apuntes» en PDF, pásaselo al programa y te dice, apunte a apunte,
qué cuadra y qué no: **facturas que no llegaron a registrarse**, apuntes que
están en Aplifisa y no en el lote (registrados a mano, de otro lote o
duplicados), y los que entraron **con otro importe**. Compara también los
totales de base e IVA. Es gratis: ese PDF lleva texto y se lee sin IA.
Ojo: tiene que ser el PDF que imprime Aplifisa, no un escaneo en papel. Si lo
arrastras a la ventana por error, el programa lo reconoce y te ofrece
contrastarlo en vez de mandarlo a Gemini (que costaría dinero y no serviría).

**El orden de los apuntes lo eliges tú.** Al exportar se pregunta: **en el orden
del PDF escaneado** (el apunte nº 3 es la hoja 3 — lo que hace falta en un
requerimiento, para poder seguir el listado contra el taco de papel numerado) o
**por fecha de factura** (lo normal en el registro trimestral). Importa porque
Aplifisa numera las facturas recibidas según entran. Las líneas de una misma
factura (varios tipos de IVA, o el suplido) nunca se separan.

**Doble contraste al exportar.** Después de escribir el Excel, el programa lo
**vuelve a leer y lo compara con la pantalla**, línea por línea y celda por
celda. Si algo no coincide (una línea de menos, un importe cambiado), avisa en
rojo y te dice que NO lo importes. Si todo cuadra, te enseña cuántas líneas y
qué totales han quedado en cada archivo, para que los compares con el resumen.

**El mismo proveedor, escrito igual.** El NIF se guarda siempre sin guiones ni
puntos (venía «A-82018474» y «A82018474» del mismo proveedor), y el nombre se
unifica al que ya tenga guardado ese NIF. Importa: Aplifisa busca la cuenta por
NIF y luego por nombre EXACTO, así que dos formas de escribirlo pueden acabar en
dos cuentas distintas.

**Suplidos.** Se registran **como tú los contabilizas**: una segunda línea de
base imponible del mismo apunte, sin % ni cuota de IVA, repitiendo fecha, número
y concepto. Ejemplo real: base 100 + IVA 21 + línea de 109,08 = importe neto
230,08. En el resumen se ven aparte, para que no se confundan con la base.

**El resumen.** «Comprobación de totales por bloque» suma cada PDF por separado
y pone **una columna por cada tipo de IVA** («IVA 21%», «IVA 10%»…), con el
porcentaje en la cabecera y solo el importe en la celda.
Se puede ocultar (botón «Ocultar» o menú Ver). La miniatura del documento se
pulsa para verla grande.

**Los avisos de cada fila.** Pulsa el semáforo (la casilla verde/ámbar/roja) y
se abre al lado una ficha con lo que le pasa a esa factura: el estado con su
color, cada problema en su línea y qué significa. Se queda abierta hasta que
pulses fuera, y el texto se puede seleccionar y copiar. Al pasar el ratón sigue
saliendo el resumen rápido, ahora con mejor formato. La barra de desplazamiento
de la tabla también se ha rehecho.

**Lo que cuesta.** Abajo a la derecha: el modelo de Gemini, lo que ha costado el
lote y lo que llevas del mes. Un lote de 24 facturas costó 7 céntimos.

---

### Lo que me falta saber de ti

1. **¿Te falta alguna cuenta** de las que usas en el catálogo?

2. **Una factura que pone «Copia duplicada»**: ¿se registra igual o se descarta?
   Si se descarta, el programa puede detectar ese sello y avisarte, como ya hace
   con las sustituidas.

3. **Un proveedor que factura sin recargo** a un cliente que está en recargo de
   equivalencia: entiendo que también va por el total factura. ¿Correcto?

4. **Un proveedor con dos CIF en la cabecera** (dos sedes): ¿cuál es el bueno
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
