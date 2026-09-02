## Lo que necesito de ti para seguir afinando el programa

Esto se actualiza con cada versión. Apunta abajo lo que veas y lo leeré
en la próxima sesión.

### Lo más útil de todo

**El total factura de cada lote.** Compara el que da el programa (abajo, en
«Comprobación de totales por bloque», que ahora suma cada PDF por separado)
con el tuyo. Si no cuadran, dímelo aunque no sepas por
qué: así salió el abono de Coca-Cola, que se estaba registrando en positivo, y no
lo habría encontrado de otra forma.

### Novedades de esta versión que quiero que pruebes

- **Botón «Escanear facturas»** (o Ctrl+E): el programa maneja el alimentador,
  guarda el PDF en `Documentos\Facturas escaneadas\<CLIENTE>` con el nombre
  puesto y lo mete solo en el lote. **Ni hace falta decirle de quién son**: si
  dejas el cliente vacío, lo detecta por el NIF y coloca el PDF él solo.
  **Dime si el escáner responde bien** (tu HP M148dw) y si el taco entero entra
  de una pasada.
- **Menú «Escaneos» (Ctrl+L)**: la lista de todos los PDF escaneados, para
  volver a meter uno en el lote, abrirlo, cambiarlo de cliente o quitarlo de en
  medio (no se borra, va a la carpeta `_Papelera`).
- **Varios PDF en un mismo Excel**: cada carga o escaneo es un «bloque» que se
  suma; se pueden juntar 3 o 4 escaneos de un requerimiento y exportar una vez.
- **Abajo a la derecha sale lo que cuesta**: el modelo de Gemini que ha
  contestado, el coste del lote y lo que llevas gastado del mes. **Dime qué
  modelo te sale**: si es un Gemini 3.x, cada factura cuesta 2,5 veces más que
  con el 2.5 Flash y a lo mejor conviene cambiarlo (aun así hablamos de
  céntimos: unas 30 facturas salen por unos 7 céntimos).
- Ya **no hay trimestre**: nada se pone en ámbar por ser de otra fecha.

### Novedades de la 1.6.0

- **El alimentador ya saca el taco entero.** El escaneo de Windows pasaba las
  13 hojas pero solo entregaba la primera imagen (de ahi que 13 facturas
  salieran en un PDF de una pagina). Ahora esa parte la hace **NAPS2**, que ya
  esta instalado en tu equipo. Tu no notas nada: el mismo boton.
- **Al escanear puedes elegir color y calidad**: blanco y negro / grises /
  color, y de 75 a 300 ppp. Grises a 200 ppp es lo recomendado. Esto cambia lo
  que TARDA el escaner y lo que pesa el PDF.
- **Configuracion -> Calidad de lectura y coste**: aqui si se cambia lo que
  cuesta Gemini, y el propio dialogo te dice cuanto sale cada factura.
- **El panel de totales se puede ocultar** (boton «Ocultar», o menu Ver).

### Lo nuevo de la 1.6.1: hojas que se pierden

Con 13 hojas salieron 11 paginas: el alimentador arrastro dos hojas pegadas y
faltaba la factura 09/25. **Eso no daba ningun aviso**, y una venta sin
registrar es un problema serio. Ahora:

- **El programa mira la numeracion**: si un emisor lleva 01/25, 02/25... y falta
  la 09/25, sale un aviso rojo arriba diciendo cual falta.
- **Al escanear puede decir cuantas hojas pone** (casilla «Hojas que pone»). Si
  salen menos paginas, avisa en el momento.
- Truco: **abanica el taco** antes de meterlo y no lo cargues muy alto; asi el
  alimentador arrastra menos hojas pegadas.

### Lo nuevo de la 1.7.0: quien es TU cliente

Con un taco de facturas de la misma gasolinera, las dos partes salen las mismas
veces y el programa elegia al azar: salio la gasolinera como cliente y todas las
facturas del reves. Ahora:

- Si hay empate, **te pregunta** de quien son las facturas, con las dos partes
  delante (cuantas veces sale cada una y si emite o recibe).
- **Lo que contestes se recuerda**: ese NIF queda marcado como cliente tuyo y la
  otra parte como proveedor. La proxima vez ya no pregunta.
- Boton **«Cambiar cliente...»** junto al nombre: si se detecto mal, lo cambias
  y **el lote se rehace al momento sin volver a pagar a Gemini**.

### Lo nuevo de la 1.10.0: ingresos y gasto/ingreso mas seguro

- **Las cuentas de ingresos ya estan** (700 ventas, 705 prestacion de
  servicios, 710 autoconsumo, 740/741/746 subvenciones, 750, 760, 770) con sus
  subclaves I01, I02... El 700 lleva **I01**, que antes iba sin subclave.
- Gemini elige tambien la cuenta de ingreso: una factura de trabajos o reparto
  deberia ir a **705 (I01) PRESTACION DE SERVICIOS**, no al 700 generico.
  **Dime si prefieres que todo vaya al 700.**
- **Dos redes para el gasto/ingreso**: si dices al escanear que el taco es de
  gastos y una factura sale como ingreso (o al reves), se marca en ambar; y si
  una factura es la unica de su bloque que va al reves, tambien.

### Corrección de la 1.10.1: conceptos completos devueltos por Gemini

Gemini devolvía unas veces solo la cuenta (`628`) y otras copiaba la línea
entera del catálogo (`628 (G16) SUMINISTROS GAS`). Aunque ambas significaban lo
mismo, el programa trataba el segundo texto como una cuenta inexistente y dejaba
la fila en ámbar. Ahora separa siempre la cuenta y la subclave antes de validar,
tanto en gastos como en ingresos.

- En **Comprobación de totales por bloque**, si hay varios tipos de IVA se
  detallan dentro de la misma celda (por ejemplo,
  `10%: 12,34 € · 21%: 56,78 €`) sin añadir columnas ni saturar la tabla.

### Lo nuevo de la 1.10.2: suplidos y documento ampliado

- Gemini lee los **suplidos expresamente identificados** en la factura. Se
  muestran en una columna editable, se suman al total sin mezclarlos con la
  base ni el IVA y se exportan en el campo `Suplidos` de Aplifisa.
- La comprobación del total tiene en cuenta base, IVA, recargo, suplidos e IRPF.
- El resumen muestra siempre el porcentaje de IVA, aunque solo haya un tipo
  (`21%: 123,45 €`).
- La miniatura de **Documento original** se puede pulsar para verla grande y
  desplazarse por ella.

### Lo nuevo de la 1.9.0: el catalogo entero de Aplifisa

Me pasaste la lista completa de conceptos (200, 600...682) con sus subclaves.
Ahora esta dentro del programa (`config/conceptos_aplifisa.csv`) y sirve para:

- **Gemini elige de esa lista exacta**, no de una idea general del PGC: no puede
  proponer una cuenta que Aplifisa no tenga.
- **Se comprueba la pareja cuenta+subclave**: si no existe (p.ej. 628 con una
  GXX que no es), sale en ambar diciendo cuales son las buenas.
- Si una cuenta solo tiene una subclave posible (la 622 solo tiene G13), **se
  rellena sola**.
- Los textos para parametrizar son ya **los nombres del propio Aplifisa**
  ("SUMINISTROS GAS"), asi que se reconocen de un vistazo en su pantalla.

Si ves que alguna cuenta que usas no esta en la lista, dimelo y la añado.

### Lo nuevo de la 1.8.0: la subclave, automatica

Descubriste la pantalla de Aplifisa «Importacion de Excel -> Parametrizar los
textos de los Conceptos». Con eso se acaba el problema de la 628:

1. Abre **Configuracion -> Textos de conceptos para Aplifisa**. Ahi tienes la
   lista: concepto y el texto que escribe el programa (GASOLEO, AGUA, LUZ,
   TELEFONO...). Boton para copiarla.
2. En Aplifisa, en esa pantalla, para cada linea: elige el concepto, deja
   «IGUAL QUE» y escribe el texto. Es cosa de una vez.
3. Vuelve al programa y marca la casilla **«Ya lo tengo configurado»**.

A partir de ahi el Excel lleva el texto y **cada apunte entra con su cuenta Y su
subclave**, tambien con proveedores nuevos. Si no marcas la casilla, todo sigue
como hasta ahora (el codigo de la cuenta).

Ademas: el **gasoleo ya va a G16** (gas), como lo tienes tu configurado.

### Dudas concretas pendientes

1. **La factura de BIMBO pone «Copia duplicada».** ¿Se registra igual que un
   original, o hay que descartarla? Si hay que descartarla, el programa puede
   detectar ese sello y avisarte, como ya hace con las sustituidas.

2. **Los pares de tipo y recargo.** ¿Son siempre IVA 21 % → 5,2 %, IVA 10 % →
   1,4 % e IVA 4 % → 0,5 %? Si me lo confirmas, el programa puede cazar solo los
   errores de lectura del recargo.

3. **Bolsera Murciana factura sin recargo** (solo IVA 21 %, son las bolsas). En
   recargo de equivalencia no se deduce IVA de nada, así que entiendo que también
   va por el total factura. ¿Correcto?

4. **Facturas simplificadas y tickets.** Si alguna se lee mal, guárdala y dímelo.
   Las tres que mandaste llevan tu cliente identificado, así que no eran
   simplificadas de verdad; me falta ver una que dé problemas.

### Si algo sale en ámbar o en rojo y no debería

Dímelo con la factura delante. Es más fácil afinar el criterio con un caso real
que adivinarlo.

### Cosas que ya sé y estoy mirando

- Al escanear se cuela a veces la banda de otra factura en la misma hoja (pasó
  con la de BIMBO): hay dos «TOTAL FACTURA» y podría coger el que no es.
- Fotografiar con el móvil **no gasta más créditos**: encuadra llenando la foto
  con la factura y se leerá mejor sin pagar más.

