## Cómo va el programa y qué necesito de ti

Actualizado el 5 de octubre de 2026 (versión 1.25.0). Apunta abajo lo que
veas y lo leo en la siguiente sesión de trabajo.

---

### Lo nuevo de la 1.25: memoria y lectura

**Arreglos de lo que salió en tu errores.log:** exportar ya no se para por un
nombre con un carácter invisible en lugar de una tilde (sale en ámbar para
escribirlo bien), y leer un paquete ya no se come la memoria cuando una
factura trae un número muy largo («Algo ha fallado» con MemoryError).

La cuenta que pones a un proveedor se recuerda **por cliente** (en otro
cliente se propone en ámbar). El NIF puesto de memoria solo va en silencio si
ese proveedor ya le factura a ese cliente o lo leído es su NIF mal impreso.
Un homónimo de tu cliente ya no se lleva el lote. Además: «posiblemente ya
exportada» por número y total, fechas siempre dd/mm/aaaa, bienes de inversión
a la 200, la doble lectura compara la cuenta, y los céntimos de redondeo de
una factura grande ya no la dejan en rojo.

### Lo nuevo de la 1.24: manda la ley

Avisos con su artículo de la Ley del IVA: lo que no es una factura (proforma,
albarán), las copias, otra moneda, inversión del sujeto pasivo e
intracomunitarias, IVA no deducible (tiques sin tu cliente, restaurantes,
regalos), rectificativas cuya original no está en el lote y ventas que faltan
contando las ya exportadas. Botón **«Por el total»** para una factura cuyo IVA
no se deduce, y régimen de cliente **sin derecho a deducir** (actividad
exenta) en Configuración → Régimen de IVA de este cliente. Por el total, la
retención se conserva.

### Lo nuevo de la 1.23: no perder nada

- **El lote se guarda solo** unos segundos después de cada cambio: un apagón
  ya no se lleva la revisión ni lo leído. Si un lote guardado no se puede
  abrir, se guarda aparte en vez de borrarse.
- **Copia de seguridad diaria** de lo que el programa recuerda (registro de
  facturas, clientes, proveedores, cuentas y notas) en «_Copias de seguridad»,
  dentro de tu carpeta de documentación. Configuración → Copias de seguridad
  para hacer una o volver a una anterior.
- **Gemini con prisas ya no tira lo leído**, y si se acaba el crédito se queda
  con lo que ya había leído.
- **Aviso en rojo** si no se puede apuntar lo exportado.
- **Cada factura, su PDF**, aunque dos se llamen igual.
- **Escritorio en OneDrive** y **«Deshacer organización»** tras una recogida.

### Lo nuevo de la 1.22.1: manda la ley

Lo que me pediste: en el programa manda la ley, siempre. Lo primero, el
recargo de equivalencia:

- **Un cliente en recargo lleva TODAS sus compras por el total factura**, también las
  que no traen recargo impreso (teléfono, reparaciones…): no presenta el 303,
  ni paga ni deduce IVA. Antes solo pasaba si el lote traía alguna factura con
  recargo. Las que llevan retención (el alquiler del local) siguen
  desglosadas y avisadas, porque el IRPF hay que declararlo.
- Se puede decir que un cliente está en recargo sin esperar a una factura con
  recargo: **Configuración → Recargo de equivalencia de este cliente**.
- **Una sociedad no puede estar en recargo** (art. 148 de la Ley del IVA): si
  a una S.L. le cobran recargo, va con desglose y se avisa.
- **El tabaco lleva el 1,75 %** de recargo: ya no sale como equivocado.

### Lo nuevo de la 1.22: facturas sin NIF

Dos tiques sin NIF con el mismo número y el mismo día, de dos sitios
distintos, ya son dos facturas en el registro (antes una pisaba a la otra).
Lo que ya tenías guardado se pasa solo.

### Lo nuevo de la 1.21: cuadre con Aplifisa de lo guardado

Botón **«Cuadre año»** (o Comprobar → Cuadre con Aplifisa, Ctrl+Mayús+R).
Sacas de Aplifisa el listado de lo que quieres comprobar (de enero a hoy,
6 o 9 meses, el año entero; compras, ventas o los dos) y el programa te dice
si es lo que tienes guardado en PDF de ese cliente: todo bien, falta en
Aplifisa, falta en el programa (búscala y escanéala), falta el PDF, duplicada
o dato distinto. Con totales por trimestre e informe en PDF. Mira todos los
lotes ya exportados de ese cliente y el que tengas abierto. El cliente lo
coge solo del NIF que trae el listado, y para dar dos facturas por la misma
tiene que ser el mismo proveedor (por su NIF o su nombre): nunca dice «todo
bien» por casualidad.

Pruébalo con el listado de enero a septiembre de un cliente y dime si algo
de lo que marca no es cierto.

### Lo nuevo de la 1.20 (el prototipo 4 que elegiste)

**Arriba, facturas y factura.** Las facturas a la izquierda; a la derecha la
hoja y, a su lado, lo que ha leído la IA («Lectura IA» lo quita y la hoja
gana el ancho). «Revisada» y «Correcta · siguiente», en la línea del título.

**Abajo, los totales como el listado de Aplifisa**: una fila por gastos e
ingresos (con un filtro, lo que se ve va primero) y una columna por importe.
Debajo, **Su suma** con una casilla bajo cada columna y lo que da de más o
de menos el programa.

**Los cinco prototipos, para elegir.** En Ver → Distribución de la pantalla
(o Ctrl+1 … Ctrl+5) puedes cambiar entre las cinco que viste dibujadas.
Cada una va mejor para un momento del trabajo:
1 tres columnas (todo a la vista en una pantalla grande), 2 lectura sobre la
hoja (comprobar contra el papel), 3 tabla arriba (repasar el lote entero),
4 cuadre con su suma (cuadrar con tu suma y con Aplifisa; la de siempre) y
5 una a una (revisar las pendientes una detrás de otra, con cuántas
quedan). Cambia solo dónde va cada pieza;
lo cargado y lo que hayas escrito en «Su suma» se quedan. Cada una recuerda
sus divisores y el programa abre con la última que elegiste.

**Columnas y anchos a tu gusto.** Cada columna mide lo que pone (el nombre
ya no se queda con media tabla) y lo que sobra se reparte entre todas.
Arrastra el borde de una columna para ensancharla (doble clic: se ajusta
sola) y el asa con puntos entre tabla, factura y totales para dar más sitio
a uno u otro (doble clic: como venía). En Ver: «Ajustar las columnas a lo
que ponen» y «Volver al reparto de esta distribución».

**Un NIF, un nombre.** Si las facturas de una empresa llegan unas con
«EMPRESA, S.A.» y otras con «Empresa», ahora salen todas con uno solo (el
que lleva la forma jurídica, o el que ya se usó para ese NIF). Si con el
mismo NIF hay dos nombres que no se parecen en nada, la línea queda en
«Revisar»: o el nombre o el NIF está mal leído.

Dime con cuál te quedas (o qué cambiarías de la que más te guste) y la dejo
como la de siempre.

### Lo nuevo de la 1.19 (lo que pediste)

**Su suma a mano.** Debajo de los totales escribes lo que te da a ti (o el
listado de Aplifisa) y al lado sale si cuadra o cuánto se separa. Compara con
lo que se ve: filtra un mes y compara con ese mes.

**Filtro por mes**, junto al de estado.

**Revisar desde la factura.** «Revisada» y «Correcta · siguiente» debajo de
la hoja. En la tabla, Intro pasa a la siguiente pendiente (sin marcar nada) y
Ctrl+Intro la da por buena y pasa. No puse Intro solo para marcar porque
quien viene de Excel pulsa Intro sin pensar y se daría por buena una factura
sin mirarla.

**Lo leído se pliega** a una línea con un clic en «Lo que ha leído la IA».

Dime si te sirve así o si prefieres otras cifras en «Su suma».

### Lo nuevo de la 1.18 (lo que pediste)

**Tres columnas.** Facturas a la izquierda; en el centro la factura (la
hoja y, debajo, lo que ha leído la IA, todo junto); a la derecha los totales
a toda la altura, con base, cada IVA, total IVA, recargo, retención,
suplidos y total, para cuadrar con tu suma a mano. Sin logo ni título
arriba: botones, cliente, periodo y «Exportar a Aplifisa». Los filtros, a la
izquierda.

**✎ Corregida.** Si corriges a mano un dato de una factura en ámbar, ya
cuenta como revisada: no hace falta pulsar «Marcar revisada». Si tras tu
corrección el total no cuadra, sigue en ámbar.

Dime si el reparto de anchos te va bien en tu pantalla (se puede arrastrar
cada separador y el programa lo recuerda).

### Lo nuevo de la 1.17.1 (lo que pediste)

**Ya no hay «M Manual».** Suplidos, bienes de inversión y sustituidas salen
en ámbar con su motivo; los miras, pulsas «Marcar revisada» y van al Excel.
Las que tenías apartadas en el lote abierto ya están en ámbar: revísalas y
expórtalas para que cuadre el registro.

**El documento, nítido y sin taparte nada.** Al acercar se ve fino (se saca
del PDF original). Arrastra para moverte, Ctrl + rueda o doble clic para
acercar, otro doble clic para ver la hoja entera. El clic ya no abre la
ventana grande.

Dime si las hojas con grapas rotas o mal escaneadas se leen bien ahora al
acercarlas.

### Lo nuevo de la 1.17 (pruébalo)

**De dónde sale cada dato.** En las facturas en ámbar o rojo, el documento de
la derecha recuadra el dato dudoso. Pulsa una celda (NIF, total, fecha…) y se
recuadra ese dato; la hoja se acerca sola. Si las dos lecturas no coinciden,
la ficha te dice cuál de los dos valores está en la hoja y cuál no aparece.
Para cualquier otra factura, botón «¿De dónde sale?» encima del documento.

**Registro de facturas.** Botón «Registro» de la barra de arriba. Todas las facturas
que salen del programa, con su recorrido, su Excel y su PDF. Busca por
proveedor, NIF, número o importe.

**Examen de precisión.** Ayuda → «Examen de precisión de la lectura…». Vuelve
a leer facturas que ya revisaste y te dice cuánto acierta cada modelo. Te
dice lo que cuesta antes de empezar; pásalo cuando quieras comparar.

**Columnas.** Recargo y retenciones solo salen cuando tocan a ese cliente.
Para verlas siempre: Ver → «Ver todas las columnas».

Dime:
- Si los recuadros caen en su sitio en tus facturas reales (con las de
  prueba sí, pero lo que manda es tu papel escaneado).
- Si prefieres que los recuadros se pidan también para las verdes (cuesta
  algo más por factura).

### Lo nuevo de la 1.16

**Una factura, un PDF.** Al exportar, el taco escaneado se parte y cada
factura queda en su propio PDF dentro de Gastos o Ingresos, con la fecha y el
proveedor en el nombre («2026-02-12 GASOLINERA EJEMPLO SL G-118.pdf»). Cada
una va al año de su fecha. El taco original se guarda en «Tacos escaneados».
Lo que ya tenías archivado no se ha tocado.

### Lo nuevo de la 1.15

**Recoger lo suelto.** Botón «Recoger» de la barra de arriba. Mira
el Escritorio y Descargas, reconoce de qué cliente es cada factura por su NIF
y te enseña la propuesta antes de mover nada. Lo dudoso sale en ámbar y sin
marcar. Si algo no te cuadra, «Deshacer la última recogida» (menú Escaneos).

**Expedientes.** Botón «Expedientes» de la barra de arriba: por cliente y ejercicio, un
PDF con todos los gastos, otro con los ingresos, los Excel y un resumen con
los totales, y un ZIP con todo. Se actualiza solo cada vez que exportas.

Dime si te encaja el formato del resumen o si quieres ver algo más en él
(por ejemplo, las facturas del ejercicio que NO se exportaron desde aquí).

### Lo nuevo de la 1.14

**Doble lectura.** Cada hoja la leen ahora dos modelos (3.8-flash y
3.7-flash). Si no coinciden en el NIF, el número, la fecha, el desglose o el
total, la factura sale en ámbar y en la ficha de al lado ves los dos valores
con un botón para quedarte con el bueno. Si coinciden y todo cuadra, sale
**Verificada**. Cuesta más o menos el doble; si prefieres, en Configuración →
Modelos de lectura puedes dejarla solo para las dudosas.

**Ya no se inventan cuentas.** Si no se sabe el concepto, se propone 629
Otros servicios en ámbar (antes entraba como 600 Compras en verde).

**Facturas ya exportadas.** Si una factura que ya mandaste a Aplifisa vuelve a
aparecer en otro lote, se avisa y al exportar se propone dejarla fuera.

**Más controles:** IVA del 22 % o fecha futura en rojo; CIF comprobados según
el tipo de sociedad; NIF intracomunitarios explicados.

### Lo que me falta saber de ti (1.14)

1. **La tarifa de gemini-3.8-flash.** No la he querido inventar. Mientras no
   la escribas en Configuración → Modelos de lectura, el gasto de ese modelo
   se estima y abajo pone «(tarifa estimada)».
2. **¿Doble lectura siempre o solo en las dudosas?** He dejado «siempre».

---

### Lo que se resolvió en la 1.13

**Escanear.** El botón «Escanear facturas» (Ctrl+E) maneja el alimentador de tu
HP, guarda el PDF completo en
`Escritorio\Documentación Facturas\<CLIENTE>\<EJERCICIO>\Gastos|Ingresos` y lo
mete solo en el lote. Los PDF creados con el programa de HP también se copian a
esa estructura al cargarlos, sin mover el original elegido. No hace falta ni
decirle de quién es: lo detecta por el NIF y coloca el PDF él solo. Eliges color
(b/n, grises, color) y calidad (75-300 ppp) en la misma ventana. En «Escaneos»
(Ctrl+L) tienes todos los PDF generados, para reabrirlos, recolocarlos o
quitarlos de en medio.

**Varios PDF en un Excel.** Cada carga o escaneo es un «bloque» que se suma al
lote. Un requerimiento de 60 facturas se escanea en tres tandas y sale un solo
Excel consolidado en el Escritorio, llamado `GASTOS_CLIENTE.xlsx` o
`INGRESOS_CLIENTE.xlsx`. Cada bloque se puede quitar por separado, y «Vaciar
todo» empieza de cero. Los PDF largos se procesan en partes internas de 25
páginas; al comprobarse el consolidado se borran también los Excel temporales
`parte_N_de_M` de ese cliente y tipo.

**Facturas que se pierden o se repiten.** Si el alimentador arrastra dos hojas
pegadas, esa factura no daba ningún aviso. Ahora salta por dos vías: el recuento
de hojas (si le dices cuántas pones) y el salto en la numeración («falta la
09/25»). Las repetidas siguen saliendo en rojo.

**Quién es tu cliente.** Con un taco de facturas del mismo proveedor las dos
partes salen las mismas veces y antes se elegía al azar. Ahora pregunta, se
acuerda de tu respuesta para siempre, y el botón «Cambiar cliente…» rehace el
lote sin volver a pagar la lectura.

**CIF/NIF corregidos.** Lo que escribes a mano completa automáticamente futuras
lecturas ausentes o inválidas. Si el OCR trae otro identificador válido, no se
cambia nada a escondidas: queda amarillo y, cuando tres o más facturas coinciden
en el nuevo, se pregunta una vez si mantener el guardado, sustituirlo o dejar el
grupo pendiente. Se recuerda también el cliente confirmado. Los tickets de
contado sin DNI permanecen en amarillo para que los veas y los marques como
revisados, sin inventarles ninguna regla.

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
momento sin volver a leer nada. Al minorista se le llevan así **todas** las
compras, traigan o no recargo, y el desplegable sale aunque el lote no lo
traiga. Para el resto de clientes, si el lote no tiene recargo, ni aparece.
Además se comprueban los pares 21→5,2 (1,75 el tabaco) / 10→1,4 / 4→0,5.

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

Vale cualquiera de los dos listados: el «Listado de apuntes desglosados» y el
**«IVA/IGIC - Facturas recibidas»**, que es el que sacas para un requerimiento.
Este segundo se leía mal (las columnas se pisan y una línea de suplido trae
menos importes que las demás, así que los porcentajes se colaban como base y el
listado descuadraba). Ahora se lee por la posición de cada columna y cuadra con
sus propios totales antes de compararlo con nada.

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

**Los avisos de cada fila.** Pulsa la casilla ámbar o roja del semáforo y se
abre al lado una ficha con banda de color, **de qué factura se trata** (línea,
número y proveedor) y cada problema en su línea, con el mismo texto de siempre.
Se queda abierta hasta que pulses fuera y el texto se puede copiar. En las filas
verdes no sale nada: no hay nada que contar. Al pasar el ratón sigue apareciendo
el aviso rápido, ahora con título en color. La barra de desplazamiento de la
tabla también se ha rehecho.

**Cola de documentos.** Ya no hace falta que partas el trabajo en tandas: suelta
los PDF que quieras y el programa los lee **de uno en uno**, por turnos. Cada
documento entra en la tabla en cuanto está —no hay que esperar al último— y
abajo se ve cuál se está leyendo y cuántos quedan en la cola. Si mientras lee
sueltas otro PDF o escaneas otro taco, **se pone en la cola** en vez de decirte
«espera a que termine». Si uno da error, se avisa y sigue con los demás. Lo de
quién es el cliente se pregunta una sola vez, al final, con todo el lote
delante. «Vaciar todo» tira también lo que estuviera esperando turno.
Cuando un PDF largo necesita lotes de 25 páginas, estos se crean únicamente en
la carpeta interna de trabajo y se eliminan después de procesarse. En el archivo
del cliente permanece el PDF completo y, al exportar, un único Excel consolidado.

**Un lote grande ya no se queda colgado.** Con 70 hojas el lote se quedaba en
«69/70» y de ahí no pasaba: si una petición a Gemini se quedaba sin contestar,
ese hilo esperaba indefinidamente y nunca llegaba el final. Ahora cada página
tiene **90 segundos**; si no contesta se reintenta una vez y, si tampoco, esa
página se marca y el lote **sigue y termina**. Al acabar, el programa te dice
**qué páginas no se han podido leer y por qué**, con su archivo y su número de
hoja, para que vuelvas a pasar solo esas.

**Lo que cuesta.** Abajo a la derecha: el modelo de Gemini, lo que ha costado el
lote y lo que llevas del mes. Un lote de 24 facturas costó 7 céntimos.

---

### Lo que me falta saber de ti

1. **¿Te falta alguna cuenta** de las que usas en el catálogo?

2. **Una factura que pone «Copia duplicada»**: ¿se registra igual o se descarta?
   Si se descarta, el programa puede detectar ese sello y avisarte, como ya hace
   con las sustituidas.

3. **Un proveedor con dos CIF en la cabecera** (dos sedes): ¿cuál es el bueno
   para la cuenta?

4. **Cómo espera Aplifisa la inversión del sujeto pasivo y las
   intracomunitarias** al importar el Excel. Su configuración tiene casillas
   para «ISP», «Tipo de factura» y «Clave de régimen especial»: ¿qué hay que
   poner en cada una (S/N, códigos del SII…)? Con eso el programa las marca
   solas.

5. **Una factura del año anterior que llega ahora** (la del 28/12 en enero):
   ¿la registras en el periodo actual con fecha de deducción (art. 99)? ¿Usa
   Aplifisa la casilla «Fecha de deducción» para eso? Hoy queda en rojo.

6. **Cliente en recargo con otra actividad que no está en recargo** (sectores
   diferenciados): ¿tienes alguno? Las compras de esa otra actividad sí
   deducen el IVA.

7. **Las ventas de un cliente en recargo**: ¿las llevas con el IVA
   desglosado (como ahora) o por el total?

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
- Pendiente de valorar: ordenar además por periodo; vigilar una carpeta para
  procesar solo lo que llegue (útil para las fotos del móvil); y que la app de
  Escáner Fotos mande aquí el PDF mejorado.
