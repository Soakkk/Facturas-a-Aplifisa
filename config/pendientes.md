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

- **Botón «Escanear facturas»** (o Ctrl+E): elige cliente y si son gastos o
  ingresos, y el programa maneja el alimentador, guarda el PDF en
  `Documentos\Facturas escaneadas\<CLIENTE>` con el nombre puesto y lo mete
  solo en el lote. **Dime si el escáner responde bien** (tu HP M148dw) y si el
  taco entero entra de una pasada.
- **Varios PDF en un mismo Excel**: cada carga o escaneo es un «bloque» que se
  suma; se pueden juntar 3 o 4 escaneos de un requerimiento y exportar una vez.
- **Abajo a la derecha sale lo que cuesta**: el modelo de Gemini que ha
  contestado, el coste del lote y lo que llevas gastado del mes. **Dime qué
  modelo te sale**: si es un Gemini 3.x, cada factura cuesta 2,5 veces más que
  con el 2.5 Flash y a lo mejor conviene cambiarlo (aun así hablamos de
  céntimos: unas 30 facturas salen por unos 7 céntimos).
- Ya **no hay trimestre**: nada se pone en ámbar por ser de otra fecha.

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
