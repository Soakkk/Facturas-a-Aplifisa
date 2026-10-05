"""Notas de parche mostradas una vez tras instalar cada versión."""

from __future__ import annotations

from . import ajustes


NOTAS = {
    "1.22.1": """
<h2>Novedades de la versión 1.22.1</h2>
<p>A partir de ahora, en el programa manda la ley: el trato fiscal de cada
factura sale de la norma, no de lo que traiga impreso.</p>
<ul>
  <li><b>Cliente en recargo de equivalencia: todas sus compras por el
      total.</b> No presenta el 303, así que ni paga ni deduce IVA. Antes solo
      se registraban por el total si el lote traía alguna factura con recargo
      impreso; un lote solo con el teléfono o unas reparaciones salía con su
      IVA desglosado. Ahora basta con que el cliente esté en recargo, y arriba
      se ve «Cliente en recargo». Las facturas con retención (el alquiler del
      local) siguen con su desglose y su aviso: el IRPF hay que declararlo.</li>
  <li><b>Decir que un cliente está en recargo sin esperar a una factura con
      recargo:</b> Configuración → Recargo de equivalencia de este
      cliente.</li>
  <li><b>Una sociedad no puede estar en recargo</b> (art. 148 de la Ley del
      IVA: solo personas físicas y comunidades de bienes). Si a una S.L. o una
      S.A. le cobran recargo, sus compras van con el desglose normal y se
      avisa de que ese recargo no le corresponde.</li>
  <li><b>El tabaco lleva un recargo del 1,75 %</b> (y lo que en 2022-2024
      iba al 5 % de IVA, el 0,62 %): ya no se marca como un recargo
      equivocado.</li>
  <li>Un lote que dejó abierto con el criterio de antes se rehace solo al
      abrirlo, sin volver a leer las facturas.</li>
</ul>
""",
    "1.22.0": """
<h2>Novedades de la versión 1.22.0</h2>
<ul>
  <li><b>Facturas sin NIF que ya no se pisan.</b> El registro de facturas
      reconocía cada factura por el NIF de la otra parte, su número y su
      fecha. Sin NIF, el tique «1» de un bar y el «1» de una ferretería del
      mismo día eran la misma ficha: exportados juntos se sumaban, y en dos
      lotes el segundo borraba al primero (y el «Cuadre año» no podía
      reclamarlo). Ahora, sin NIF, cuenta el nombre de la otra parte. Las
      fichas que ya tenía se pasan solas al arrancar, y la misma factura
      escrita de otra forma («Bar La Esquina, S.L.» y «BAR ESQUINA SL»)
      sigue avisando de «ya exportada».</li>
  <li><b>Pruebas más seguras al publicar.</b> Una de las comprobaciones que
      se pasan antes de publicar se quedaba a veces parada en Windows: la
      ventana de «Novedades» se abría en mitad de ella y esperaba un clic.
      Ya no puede pasar, y si alguna vez algo se para, se corta a los pocos
      minutos diciendo dónde. No cambia nada de lo que usted ve.</li>
</ul>
""",
    "1.21.0": """
<h2>Novedades de la versión 1.21.0</h2>
<ul>
  <li><b>Cuadre con Aplifisa de lo guardado</b> (botón <b>«Cuadre año»</b>,
      Comprobar → Cuadre con Aplifisa, o Ctrl+Mayús+R). Saque de Aplifisa el
      listado de lo que quiere comprobar (del 1 de enero a hoy, 6 o 9 meses,
      el año entero; compras, ventas o los dos) y el programa le dice si es
      lo que tiene guardado en PDF de ese cliente, factura a factura:
      <ul>
        <li><b>Todo bien</b>: está en Aplifisa y su PDF está guardado.</li>
        <li><b>Falta en Aplifisa</b>: el programa la tiene y no está
            registrada.</li>
        <li><b>Falta en el programa</b>: está en Aplifisa pero no hay PDF
            guardado: hay que buscarla y escanearla.</li>
        <li><b>Falta el PDF</b>: registrada, pero su PDF no está en la
            carpeta del cliente.</li>
        <li><b>Duplicada</b>: la misma factura dos veces (mismo proveedor,
            número, fecha e importes).</li>
        <li><b>Dato distinto</b>: la misma factura con otra fecha, importe,
            retención, recargo o nombre.</li>
      </ul>
      Mira todo lo que el programa tiene de ese cliente (todos los lotes ya
      exportados, con su PDF) y el lote abierto. El cliente lo elige solo,
      por el NIF que Aplifisa imprime en el listado (y avisa si el elegido es
      otro). Cada listado lleva su periodo (sale del listado por trimestres;
      póngale las fechas que pidió a Aplifisa). Todas las líneas del listado
      se comprueban, y si el listado no se ha leído entero (o no trae sus
      totales) no dice «todo bien». Para dar dos facturas por la misma tiene
      que constar que son del mismo proveedor: su NIF, o su nombre entero
      (compartir un apellido o una palabra no basta, ni una C.B. es la
      persona que le da nombre); un NIF o un nombre vacío no cuentan. Dos facturas con distinto número o NIF
      nunca se dan por la misma: lo dudoso sale como «falta» con una pista
      de cuál podría ser. Para el cuadre más seguro de las compras, use el
      listado de <b>facturas recibidas</b> (trae el número de cada factura).
      Con totales por trimestre, filtro de «solo lo que falla», «Abrir su
      PDF», «Ver en el lote» e informe en PDF. Rápido aunque sean miles de
      facturas. Sin IA ni coste.</li>
</ul>
""",
    "1.20.1": """
<h2>Novedades de la versión 1.20.1</h2>
<ul>
  <li><b>Exportar las facturas que faltan en Aplifisa.</b> Una factura cuenta
      como exportada en cuanto se crea su Excel, aunque luego la importación
      en Aplifisa se cancele o se quede a medias. Antes, al volver a exportar,
      «Exportar sin ellas» las quitaba todas, no quedaba nada y el programa
      se paraba sin llegar a elegir el orden. Ahora:
      <ul>
        <li>Si todo el lote ya salió, el botón principal es <b>«Comprobar con
            el listado de Aplifisa…»</b>: elija el PDF del listado y el
            programa ve cuáles faltan.</li>
        <li>Con el listado comprobado (aquí o con Comprobar → Comprobar
            registro de Aplifisa), se ofrece <b>«Exportar las que faltan»</b>:
            el Excel lleva solo esas (y las nuevas), y se pasa a elegir el
            orden como siempre.</li>
        <li>Si según el listado ya está todo en Aplifisa, por defecto no se
            exporta nada (se puede forzar con «Exportarlas todas otra
            vez»).</li>
      </ul></li>
  <li>Si no queda nada que exportar, ahora lo dice una ventana (antes era un
      aviso discreto y parecía que «Exportar» no hacía nada).</li>
  <li><b>Comprobar con Aplifisa: gastos con gastos e ingresos con
      ingresos.</b> Un listado de compras se compara solo con los gastos del
      lote (y uno de ventas, con los ingresos), y solo con las fechas que
      cubre el listado (del primer mes al último). Antes se comparaba todo el
      lote y los ingresos y las facturas de otros meses salían como «no
      registradas». La ventana dice qué se ha comparado y cuántas quedan
      fuera.</li>
  <li><b>El listado de apuntes desglosados se lee entero.</b> Si una factura
      no lleva número en Aplifisa, antes se desfasaba la lectura (el total de
      la línea anterior pasaba a ser su número) y salía «el propio listado no
      cuadra». Ahora se lee línea a línea por columnas, y las facturas se
      cuentan bien aunque Aplifisa repita un número.</li>
</ul>
""",
    "1.20.0": """
<h2>Novedades de la versión 1.20.0</h2>
<ul>
  <li><b>Nueva pantalla.</b> Arriba, las facturas a la izquierda y la
      <b>factura</b> a la derecha: la hoja escaneada y, a su lado, lo que ha
      leído la IA (el botón «Lectura IA» lo quita para dar a la hoja todo el
      ancho). «Revisada» y «Correcta · siguiente» suben a la línea del
      título de la factura.</li>
  <li><b>Los totales, abajo y a lo ancho, como el listado de Aplifisa.</b>
      Una fila por gastos e ingresos (y por lo que se ve con un filtro, que
      va la primera) y una columna por importe: base, cada IVA, total IVA,
      recargo, retención, suplidos y total. El divisor entre arriba y abajo
      se puede arrastrar y el programa lo recuerda.</li>
  <li><b>Su suma, debajo de cada columna.</b> Una casilla bajo cada importe
      y, debajo, lo que da de más o de menos el programa (o «✓ cuadra»). La
      fila con la que se compara sale en negrita. «Su suma a mano» oculta o
      enseña esa fila.</li>
  <li><b>Más facturas a la vista en un portátil.</b> Si los botones de la
      tabla no caben en una fila, los de uso ocasional (unir hojas, limpiar
      filtros, quitar bloque, eliminar) se quedan con el icono; su nombre
      sale al pasar el ratón.</li>
  <li><b>Elija la distribución de la pantalla</b> en <b>Ver → Distribución
      de la pantalla</b> (o con Ctrl+1 … Ctrl+5): los cinco prototipos que
      vio dibujados.
      <ol>
        <li><b>Tres columnas</b> — todo a la vista en una pantalla grande:
            facturas | factura (la hoja arriba y lo leído debajo) | totales
            en columna.</li>
        <li><b>Lectura sobre la hoja</b> — para comprobar contra el papel:
            la hoja ocupa toda la factura, lo leído queda en una línea y los
            datos ya localizados se señalan sobre la hoja.</li>
        <li><b>Tabla arriba</b> — para repasar el lote entero: la tabla de
            facturas a lo ancho; debajo, la factura y los totales.</li>
        <li><b>Cuadre con su suma</b> (la de siempre) — para cuadrar con su
            suma y con Aplifisa: los totales abajo, a lo ancho, con «Su suma»
            bajo cada columna.</li>
        <li><b>Una a una</b> — para revisar las pendientes una detrás de
            otra: una lista con lo justo, la factura en grande, cuántas
            quedan y los totales en columna (para pantallas anchas).</li>
      </ol>
      Con los totales en columna, «Su suma» va al lado de cada importe. Cada
      distribución recuerda dónde dejó los divisores y el programa abre con
      la última elegida.</li>
  <li><b>Columnas a la medida de lo que ponen.</b> Cada columna de la tabla
      mide lo que su texto más largo, con aire para leerse bien; si sobra
      sitio se reparte entre todas (antes se lo quedaba entero el nombre) y
      si falta, se estrechan el nombre y el nº de factura, nunca los
      importes. Los títulos van alineados con su contenido.</li>
  <li><b>Anchos a su gusto.</b> Arrastre el borde de una columna para
      ensancharla: se queda así (doble clic en el borde la vuelve a ajustar).
      Entre la tabla, la factura y los totales hay un asa con puntos:
      arrástrela para dar más sitio a uno u otro (doble clic: como venía).
      En <b>Ver</b>: «Ajustar las columnas a lo que ponen» y «Volver al
      reparto de esta distribución». Cada distribución recuerda lo suyo.</li>
  <li><b>Un NIF, un nombre.</b> Las facturas de una misma empresa llegaban
      unas con el nombre fiscal («EMPRESA, S.A.») y otras con el comercial
      («Empresa»): ahora todas salen con uno solo, el que ya se usó para ese
      NIF o, la primera vez, el que lleva la forma jurídica. También al abrir
      un lote de antes y al corregir un NIF a mano. Si con el mismo NIF hay
      nombres que no se parecen en nada, la línea queda en «Revisar»: o el
      nombre o el NIF está mal leído.</li>
</ul>
""",
    "1.19.0": """
<h2>Novedades de la versión 1.19.0</h2>
<ul>
  <li><b>Su suma a mano.</b> Debajo de los totales, escriba lo que le da a
      usted (a mano o en el listado de Aplifisa): base, IVA, total… Al lado
      sale «✓ cuadra» o cuánto se separa el programa (+35,55 €). Compara con
      lo que se ve: si filtra un mes, con ese mes. Lo escrito se guarda con
      el lote.</li>
  <li><b>Filtro por mes</b>, junto al de estado: julio, agosto, septiembre…
      (y «Sin fecha» si alguna no la tiene). Los totales de «Lo que se ve»
      son los de ese mes, para cuadrar mes a mes con Aplifisa.</li>
  <li><b>Revisar sin ir a la tabla.</b> Debajo de la factura: «Revisada»
      (la marca y se queda) y «Correcta · siguiente» (la da por buena y salta
      a la siguiente pendiente). Atajos en la tabla: <b>Intro</b> pasa a la
      siguiente pendiente sin marcar nada; <b>Ctrl+Intro</b> la da por buena
      y pasa. Una en rojo no se puede dar por buena: se corrige antes.</li>
  <li><b>«Lo que ha leído la IA» se pliega</b> a una línea (estado y
      motivo) con un clic en su título, y la hoja gana todo el alto. El
      programa recuerda cómo lo dejó.</li>
</ul>
""",
    "1.18.0": """
<h2>Novedades de la versión 1.18.0</h2>
<ul>
  <li><b>Pantalla en tres columnas.</b> A la izquierda, las facturas leídas;
      en el centro, la <b>factura</b>: la hoja escaneada y, justo debajo, lo
      que ha leído la IA (el divisor entre las dos se puede arrastrar); a la
      derecha, a toda la altura, la <b>comprobación de totales</b>. La franja
      de totales de abajo y la columna «Bloques del lote» desaparecen: el
      bloque se sigue eligiendo en su desplegable.</li>
  <li><b>Totales completos para cuadrar a mano.</b> Gastos e ingresos por
      separado, con base imponible, cada tipo de IVA, total IVA, recargo de
      equivalencia, retención IRPF, suplidos y total. Lo que vale cero
      también sale (en gris), para que vea que está mirado. Con un filtro o
      con facturas fuera del trimestre, sale además el bloque de lo que se
      ve y el de dentro y fuera del trimestre.</li>
  <li><b>Arriba, solo lo que se usa.</b> Fuera el logo y el título: una fila
      de botones con el cliente y el periodo en el centro y «Exportar a
      Aplifisa» a la derecha. Modelos de lectura y API key siguen en el menú
      Configuración. En ventanas pequeñas, los botones de uso ocasional se
      quedan solo con el icono (su nombre sale al pasar el ratón).</li>
  <li><b>Filtros a la izquierda</b> y buscador de tamaño normal; Todos /
      Gastos / Ingresos, más pequeños, al lado.</li>
  <li><b>✎ Corregida.</b> Si corrige a mano un dato de una factura en ámbar
      (o elige «Usar este» en la ficha, o cambia gasto/ingreso), toda la
      factura pasa a «✎ Corregida»: cuenta como revisada y se exporta sin
      pulsar «Marcar revisada». Si después de su corrección el total no
      cuadra, sigue en ámbar para que no se escape un dígito mal tecleado.
      Las facturas a las que el programa copia ese dato (mismo proveedor)
      siguen pendientes: esas no las ha mirado nadie.</li>
  <li><b>Doble lectura más segura.</b> «Es correcto» y «Usar este» ya no
      tocan los importes de otras líneas de la factura: un suplido va solo a
      su línea, la retención solo a la suya y, en un abono, el importe
      elegido conserva el signo. Si no se puede poner sin riesgo, el botón
      le pide corregirlo en la tabla.</li>
  <li><b>Clientes en recargo «por el total».</b> Un importe corregido a mano
      en la línea resumida ya no se pierde al escanear otro taco o quitar
      un bloque. Y si una factura leída como gasto se pasa a ingreso, vuelve
      con su IVA (una venta no va por el total).</li>
</ul>
""",
    "1.17.2": """
<h2>Novedades de la versión 1.17.2</h2>
<ul>
  <li><b>Un Excel nuevo en cada exportación.</b> Antes el Excel se llamaba
      siempre igual (<i>GASTOS_CLIENTE.xlsx</i>) y, si el de la vez anterior
      seguía en el Escritorio o abierto en Excel o en Aplifisa, el nuevo no se
      generaba. Ahora, si ya existe, el nuevo sale como
      <i>GASTOS_CLIENTE_2.xlsx</i>, <i>_3</i>… El anterior no se toca, y el
      aviso final le dice el nombre exacto del que acaba de crear. Así puede
      trabajar con varios bloques de facturas y exportar cada uno.</li>
  <li>La comprobación de facturas ya exportadas sigue igual: lo que ya salió
      hacia Aplifisa no se vuelve a meter si pulsa «Exportar sin ellas».</li>
  <li><b>Ningún fallo pasa en silencio.</b> Si algo sale mal al exportar, o en
      cualquier otro momento, aparece un mensaje explicando qué ha pasado y
      queda apuntado en <i>errores.log</i>. Si el Excel no se puede guardar,
      no se deja ninguno a medias. Si al releerlo no coincide con la pantalla,
      se aparta como <i>«NO IMPORTAR - GASTOS_…»</i> para que no se pueda
      importar por error.</li>
</ul>
""",
    "1.17.1": """
<h2>Novedades de la versión 1.17.1</h2>
<ul>
  <li><b>Se acabó la «gestión manual».</b> Las facturas con suplido, los
      posibles bienes de inversión y las sustituidas ya no se apartan en
      gris («M Manual»): salen en <b>ámbar</b>, con el motivo en la ficha, y
      en cuanto pulsa <i>Marcar revisada</i> van al Excel como las demás.
      Antes se quedaban fuera de la exportación y no llegaban a Aplifisa,
      y eso descuadraba el registro.</li>
  <li>Las que tenía apartadas en el lote abierto pasan solas a ámbar: revíselas
      y expórtelas. Si alguna ya estaba exportada, el programa le avisa antes
      de repetirla.</li>
  <li><b>Marcar revisada</b> confirma la factura entera: en una factura con
      suplido o con varios tipos de IVA basta con pulsar una de sus líneas.</li>
  <li><b>El documento se ve nítido al acercarlo.</b> La hoja se saca del PDF
      original al tamaño de la pantalla, en vez de ampliar la imagen pequeña
      que se manda a Gemini.</li>
  <li><b>Sin ventanas que lo tapen todo.</b> Un clic en el documento ya no
      abre la vista grande. En su lugar: <i>arrastre</i> para moverse por la
      hoja, <i>Ctrl + rueda</i> o <i>doble clic</i> para acercar ese punto, y
      otro doble clic vuelve a la hoja entera. En el botón ⋮: «Ver la hoja
      entera» y «Ajustar al ancho». Los recuadros de «¿De dónde sale?» siguen
      igual.</li>
</ul>
""",
    "1.17.0": """
<h2>Novedades de la versión 1.17.0</h2>
<ul>
  <li><b>De dónde sale cada dato.</b> En las facturas en ámbar o en rojo, el
      documento de la derecha recuadra dónde está escrito el dato dudoso. Al
      pulsar una celda de la tabla (NIF, total, fecha…) se recuadra ese dato y
      la hoja se acerca sola. Si las dos lecturas no coinciden, salen los dos
      sitios y la ficha dice cuál de los dos valores <i>está en la hoja</i> y
      cuál <i>no aparece</i>. Para cualquier otra factura, botón
      <i>«¿De dónde sale?»</i> encima del documento. Es una consulta aparte a
      Gemini, más corta que la lectura, y solo para las dudosas; se puede
      quitar en Configuración → Modelos de lectura.</li>
  <li><b>Registro de facturas</b> (cinta → Archivo → «Registro»): cada
      factura que sale del programa queda apuntada con su recorrido (leída,
      revisada, exportada, archivada), el Excel en el que salió y su PDF. Se
      busca por proveedor, NIF, número o importe y se abre su PDF con doble
      clic. El resumen del expediente sale de aquí, con el PDF de cada
      factura y las archivadas que no se exportaron.</li>
  <li><b>Examen de precisión</b> (Ayuda → «Examen de precisión de la
      lectura…»): vuelve a leer facturas que usted ya revisó y dice, con
      números, cuánto acierta cada modelo en cada dato y si alguna habría
      salido verificada con un dato mal. Dice el coste antes de empezar y
      guarda cada examen para comparar versiones.</li>
  <li><b>Columnas según el cliente.</b> Recargo y retenciones solo ocupan
      sitio cuando tocan: recargo si el cliente está en ese régimen o alguna
      factura lo trae; retenciones si alguna factura las trae o el cliente
      ya las tuvo antes. Nunca se esconde una columna con datos. Para verlas
      todas: Ver → «Ver todas las columnas» (o clic derecho en la cabecera).</li>
  <li><b>Por dentro:</b> todo lo que el programa recuerda (clientes,
      proveedores, ajustes, gasto de Gemini, facturas exportadas) está ahora
      en una sola base de datos en su ordenador. Lo de antes se ha copiado
      solo; los archivos antiguos quedan como estaban. Además, la ventana
      principal se ha reorganizado para que corregir, ordenar y filtrar
      vaya más fino.</li>
  <li>Todos los importes de la tabla salen con dos decimales.</li>
</ul>
""",
    "1.16.0": """
<h2>Novedades de la versión 1.16.0</h2>
<ul>
  <li><b>Una factura, un PDF.</b> Al exportar a Aplifisa, el taco escaneado se
      parte: cada factura queda en su propio PDF, con la fecha y el proveedor
      (o cliente) en el nombre, por ejemplo
      <i>2026-02-12 GASOLINERA EJEMPLO SL G-118.pdf</i>. Así la carpeta se
      ordena sola por fecha y se encuentra cualquier factura de un vistazo.</li>
  <li>Cada factura va al ejercicio de <b>su</b> fecha y a Gastos o Ingresos
      según <b>su</b> tipo, aunque el taco mezclara años o tipos.</li>
  <li>El PDF original del escaneo no se borra: se aparta intacto en
      <i>Tacos escaneados</i>, dentro del mismo ejercicio.</li>
  <li>Las facturas apartadas para gestión manual (bienes de inversión,
      suplidos) también tienen su PDF; los duplicados y las sustituidas no.</li>
  <li>Lo archivado antes de esta versión se queda como estaba.</li>
</ul>
""",
    "1.15.0": """
<h2>Novedades de la versión 1.15.0</h2>
<ul>
  <li><b>Recoger facturas sueltas</b> (cinta → Archivo → «Recoger sueltos…»):
      busca en el Escritorio y en Descargas los PDF de facturas y los Excel
      de Aplifisa, averigua de qué cliente, ejercicio y tipo es cada uno por
      el NIF de su texto (gratis) y los lleva a su carpeta
      <i>Nombre — NIF / Ejercicio / Gastos | Ingresos</i>. Antes de mover
      nada enseña la propuesta; lo dudoso sale en ámbar y sin marcar. Las
      copias repetidas van a _Duplicados y todo se puede deshacer.</li>
  <li>Los escaneados sin texto se pueden identificar con Gemini leyendo solo
      su primera página, con el coste a la vista.</li>
  <li><b>Expediente por cliente y ejercicio</b> (cinta → Archivo →
      «Expedientes…»): un PDF con todos los gastos y otro con todos los
      ingresos, con índice y marcadores; los Excel exportados; y un resumen
      en PDF con base, IVA, recargo, retención y total de lo exportado. Al
      lado, un ZIP con todo para adjuntar en Aplifisa.</li>
  <li><b>Se mantiene solo:</b> cada exportación guarda una copia fechada del
      Excel en la carpeta del cliente (<i>Excel Aplifisa</i>) y actualiza su
      expediente. Al recoger sueltos, también.</li>
</ul>
""",
    "1.14.0": """
<h2>Novedades de la versión 1.14.0</h2>
<p>Esta versión está pensada para que ningún dato mal leído llegue a Aplifisa
sin que se vea, y para entender de un vistazo qué se ha leído.</p>
<ul>
  <li><b>Doble lectura:</b> cada hoja la leen dos modelos de Gemini
      (3.8-flash y 3.7-flash) y se comparan NIF, número, fecha, desglose de
      IVA, retención y total. Si no coinciden, la factura queda en ámbar con
      los dos valores y un botón para quedarse con el bueno. Se puede dejar
      solo para las dudosas en Configuración → Modelos de lectura.</li>
  <li><b>Nuevos estados:</b> <i>Verificada</i> (las dos lecturas coinciden y
      todo cuadra), <i>Sin verificar</i> (todo cuadra, pero la leyó un solo
      modelo), <i>Revisar</i> y <i>Error</i>. Abajo se ve el recuento.</li>
  <li><b>Ficha de la factura</b> junto al documento: identificación, importes
      y contabilidad, cada dato con ✓ o !, y el cuadre como una cuenta
      («480,00 + 100,80 = 580,80 ✓ total impreso 580,80»).</li>
  <li><b>No se inventan cuentas:</b> una factura sin concepto claro ya no
      entra como 600 Compras en verde; se propone 629 Otros servicios y queda
      en ámbar para elegir. Un servicio (705) con la subclave mal leída ya no se
      convierte en venta de género (700).</li>
  <li><b>Controles nuevos:</b> tipo de IVA que no existe (p. ej. 22 %) y fecha
      futura salen en rojo; los CIF se comprueban según el tipo de sociedad;
      los NIF intracomunitarios (ES…, FR…) se explican en vez de salir como
      «dudosos».</li>
  <li><b>Facturas ya exportadas:</b> el programa recuerda lo que ya salió
      hacia Aplifisa. Si una factura vuelve a aparecer en otro lote, se avisa
      y al exportar se propone dejarla fuera.</li>
  <li><b>Clientes de la suite:</b> reconoce al momento a los clientes del
      directorio común (el mismo que usa Generador de avisos) y apunta allí
      los que confirme aquí.</li>
  <li><b>Más rápido:</b> corregir una celda en un lote de 300 líneas pasa de
      6 segundos a menos de 0,2. Se leen 10 hojas a la vez.</li>
  <li><b>Avisos dentro de la ventana con «Deshacer»</b> (eliminar filas,
      quitar un bloque, marcar revisadas…), y nueva cinta de herramientas
      con el estilo de la suite.</li>
</ul>
""",
    "1.13.24": """
<h2>Novedades de la versión 1.13.24</h2>
<ul>
  <li><b>Listado PDF de comprobación:</b> el bloque de totales incorpora un
      botón visible para guardar un documento imprimible.</li>
  <li><b>Preparado para puntear:</b> el PDF incluye cliente, NIF, periodo,
      resumen del lote, resultado del filtro y el detalle de las facturas que
      se están mostrando.</li>
  <li><b>Respeta los campos fiscales:</b> cuenta, GXX, IVA, IRPF, total y, cuando
      exista, recargo de equivalencia aparecen en el listado.</li>
</ul>
""",
    "1.13.23": """
<h2>Novedades de la versión 1.13.23</h2>
<ul>
  <li><b>Mesa contable directa:</b> desaparece el titular decorativo y la tabla
      aprovecha ese espacio para la revisión de facturas.</li>
  <li><b>Acciones visibles y compactas:</b> Siguiente incidencia, Marcar
      revisada, Unir hojas, Limpiar filtros, Quitar bloque y Eliminar quedan a
      la vista, ajustadas a su texto y sin el menú «Más acciones».</li>
  <li><b>Orden contable recuperado:</b> Tipo, Cuenta y GXX vuelven al principio;
      NIF, IVA e IRPF permanecen visibles. El recargo de equivalencia aparece
      automáticamente solo cuando el lote lo contiene.</li>
  <li><b>Paneles ajustables:</b> se puede arrastrar la separación entre tabla y
      documento, y también entre la revisión y la comprobación de totales. El
      programa recuerda las posiciones elegidas.</li>
  <li><b>Gestión manual fuera del trabajo diario:</b> sigue disponible en el
      menú Comprobar para los casos excepcionales, sin ocupar la barra habitual.</li>
</ul>
""",
    "1.13.22": """
<h2>Novedades de la versión 1.13.22</h2>
<ul>
  <li><b>Excel sin protección:</b> se elimina por completo una marca vacía de
      protección que algunos importadores podían interpretar como un libro
      bloqueado, aunque no tuviera contraseña.</li>
  <li><b>Listo para Aplifisa:</b> el archivo se cierra y libera inmediatamente
      después de generarlo y comprobar sus importes, para que Aplifisa pueda
      abrirlo directamente con acceso de edición.</li>
</ul>
<p>Las comprobaciones fiscales se mantienen, pero no dejan el Excel abierto ni
añaden medidas de protección al archivo.</p>
""",
    "1.13.21": """
<h2>Novedades de la versión 1.13.21</h2>
<ul>
  <li><b>Mesa de revisión · Azul asesoría:</b> fondos claros, cabecera blanca,
      azul suave y texto contrastado, incluso con Windows en modo oscuro.</li>
  <li><b>Buscador a la vista:</b> búsqueda amplia por proveedor o cliente,
      botones Todos/Gastos/Ingresos y filtro de facturas fuera del trimestre.</li>
  <li><b>Tabla y original juntos:</b> importes y retenciones en la vista de
      revisión; «Más acciones → Mostrar todos los campos contables» permite
      editar también NIF, cuenta, concepto y porcentajes.</li>
  <li><b>Totales del lote completo:</b> el resumen parte de todo lo cargado.
      Los resultados del filtro se destacan en azul y el desglose por escaneo
      sigue disponible en el menú Ver.</li>
  <li><b>Adaptada a portátiles:</b> las acciones secundarias se agrupan cuando
      falta espacio. «Siguiente incidencia» limpia los filtros que podrían
      ocultar la factura afectada.</li>
</ul>
<p>Se conservan las sesiones, las comprobaciones, las correcciones y el formato
de exportación a Aplifisa.</p>
""",
    "1.13.20": """
<h2>Novedades de la versión 1.13.20</h2>
<ul>
  <li><b>Buscador fiscal del lote:</b> localiza proveedor o cliente aunque
      cambien mayúsculas, acentos o la forma jurídica; también admite NIF,
      número de factura e importes exactos.</li>
  <li><b>El filtro tiene sus propios totales:</b> la comprobación muestra por
      separado el lote completo y el resultado visible, contando facturas y
      líneas fiscales.</li>
  <li><b>Control de trimestre:</b> detecta el periodo del lote, señala una fecha
      que se sale del trimestre y separa los importes de dentro y fuera sin
      impedir registrarla después de revisarla.</li>
  <li><b>Cuadre completo con Aplifisa:</b> lee los listados fiscales actuales de
      gastos e ingresos y compara base, IVA, recargo, IRPF, total, facturas y
      líneas. Las diferencias quedan filtrables y se puede volver directamente
      a la factura afectada.</li>
</ul>
""",
    "1.13.19": """
<h2>Novedades de la versión 1.13.19</h2>
<ul>
  <li><b>Una carpeta por NIF:</b> los nuevos escaneos se guardan en
      Nombre — NIF / Ejercicio / Gastos o Ingresos. Otra escritura del nombre
      no crea otra carpeta para el mismo NIF.</li>
  <li><b>Sin copias repetidas al importar:</b> si el mismo PDF ya está archivado
      en su destino, se reutiliza. El original externo se conserva.</li>
  <li><b>Hojas invertidas:</b> se une automáticamente un resumen anterior a su
      cabecera cuando coinciden número, fecha e identidad y los importes cuadran.</li>
  <li><b>Escaneos más fáciles de localizar:</b> búsqueda por cliente, NIF o
      archivo y filtro de gastos e ingresos.</li>
</ul>
<p>Las carpetas antiguas se conservan. Su reorganización es opcional, con
vista previa y posibilidad de deshacer.</p>
""",
    "1.13.18": """
<h2>Novedades de la versión 1.13.18</h2>
<ul>
  <li><b>Facturas completas:</b> se recalcula el total al corregir las líneas;
      los duplicados contradictorios y las facturas incompletas no se exportan.</li>
  <li><b>Identidad y cuentas:</b> se avisa de NIF incompatibles y se impide
      exportar una cuenta que no corresponde a gasto o ingreso.</li>
  <li><b>Facturas de varias hojas:</b> se mantiene la unión de cabecera y resumen
      fiscal sin identificación, con aviso para comprobarla. También funciona
      entre partes internas de 25 páginas y respeta las correcciones.</li>
  <li><b>Ejemplos reales guardados:</b> se conservan localmente los originales,
      las lecturas y las revisiones. En Ayuda, «Preparar ZIP de ejemplos para
      revisión» permite guardar un ZIP para adjuntarlo a la conversación.</li>
  <li><b>Tus decisiones se conservan:</b> unir hojas no modifica las otras
      facturas del lote ni recupera automáticamente documentos apartados.</li>
</ul>
""",
    "1.13.17": """
<h2>Novedades de la versión 1.13.17</h2>
<ul>
  <li><b>IRPF visible y editable:</b> la tabla muestra base de retención,
      porcentaje y cuota; en transportistas avisa si falta el 1%.</li>
  <li><b>Ordenación por cabeceras:</b> pulse Fecha, IRPF, nombre, importe o
      cualquier otra columna para ordenar; un segundo clic invierte el orden.</li>
  <li><b>Retenciones primero:</b> al pulsar por primera vez una columna de IRPF
      aparecen arriba las facturas que sí tienen retención.</li>
  <li><b>Más espacio útil:</b> Bloque se oculta en la tabla —permanece en el
      filtro y el resumen— y Cuenta/GXX ocupan menos ancho.</li>
</ul>
""",
    "1.13.16": """
<h2>Novedades de la versión 1.13.16</h2>
<ul>
  <li><b>Tabla nuevamente legible:</b> se corrige el fondo negro que podía
      ocultar visualmente los datos después de revisar o corregir una fila.</li>
  <li><b>Colores del sistema:</b> al desaparecer una incidencia se recuperan
      correctamente el fondo normal, las filas alternas y el texto del tema.</li>
  <li><b>Los datos nunca faltaron:</b> era únicamente un defecto de pintura;
      importes, comprobaciones y exportación permanecían intactos.</li>
</ul>
""",
    "1.13.15": """
<h2>Novedades de la versión 1.13.15</h2>
<ul>
  <li><b>Rectificativas de ventas:</b> si el cliente emitió el abono, se
      mantiene como ingreso en la cuenta 700 con todos los importes negativos.</li>
  <li><b>Clasificación contable correcta:</b> el signo negativo reduce el
      importe, pero ya no cambia por sí solo una venta a gasto.</li>
  <li><b>Resumen neto por tipo:</b> los abonos restan dentro de Gastos o
      Ingresos según quién haya emitido la factura.</li>
</ul>
""",
    "1.13.14": """
<h2>Novedades de la versión 1.13.14</h2>
<ul>
  <li><b>Abonos de proveedor:</b> dentro de un lote de gastos se contabilizan
      como menor gasto en su cuenta, nunca como un ingreso en la 700.</li>
  <li><b>Signos coherentes:</b> base, cuota, recargo y total quedan en negativo
      aunque el menos solo se haya leído con claridad en el total.</li>
  <li><b>Resumen neto:</b> la comprobación de totales suma las facturas normales
      y resta automáticamente los abonos para mostrar el resultado final.</li>
  <li><b>Abonos de ventas protegidos:</b> una rectificativa emitida en un lote
      de ingresos continúa siendo un ingreso negativo.</li>
</ul>
""",
    "1.13.13": """
<h2>Novedades de la versión 1.13.13</h2>
<ul>
  <li><b>Año incorrecto localizado:</b> solo queda en rojo la factura cuya
      fecha pertenece a un ejercicio distinto del predominante en el lote.</li>
  <li><b>Aviso concreto:</b> la alerta superior indica línea, número, fecha
      leída y los dos años para encontrar y corregir el error enseguida.</li>
  <li><b>El campo problemático queda marcado:</b> fecha, número, NIF, base,
      IVA, cuota o total se resaltan directamente para localizar la corrección.</li>
  <li><b>Sin falsos amarillos:</b> se elimina también el antiguo aviso global
      guardado en sesiones anteriores, que coloreaba todas las facturas.</li>
</ul>
""",
    "1.13.12": """
<h2>Novedades de la versión 1.13.12</h2>
<ul>
  <li><b>Unión automática más resistente:</b> si dos hojas consecutivas repiten
      el mismo número de factura, una fecha mal leída en el pie ya no impide
      unirlas; se conserva la fecha clara de la cabecera.</li>
  <li><b>Nuevo botón «Unir hojas»:</b> permite seleccionar fragmentos, incluso
      de PDF distintos, y convertirlos expresamente en una sola factura.</li>
  <li><b>Sin duplicar subtotales:</b> la primera hoja aporta identificación y el
      resumen fiscal completo de la última aporta los importes definitivos.</li>
</ul>
""",
    "1.13.11": """
<h2>Novedades de la versión 1.13.11</h2>
<ul>
  <li><b>Facturas de dos o más hojas:</b> la cabecera de la primera página se
      une con el resumen fiscal definitivo de la última aunque esta no repita
      el número de factura ni el destinatario.</li>
  <li><b>Subtotales intermedios:</b> un subtotal de artículos al acabar una hoja
      ya no se toma como base imponible ni como total de una factura separada.</li>
  <li><b>Un único apunte:</b> se conservan número, fecha y cliente de la cabecera,
      junto con todas las bases, IVA, recargo y total del resumen final.</li>
</ul>
""",
    "1.13.10": """
<h2>Novedades de la versión 1.13.10</h2>
<ul>
  <li><b>Numeración correcta en ingresos:</b> la serie se comprueba para el
      cliente emisor completo, no por cada comprador de sus facturas.</li>
  <li><b>Sin falsos avisos por IVA:</b> una factura con varias bases o tipos de
      IVA cuenta una sola vez al buscar hojas ausentes.</li>
  <li><b>El Excel no cambia:</b> la corrección afecta únicamente al aviso de
      control; los apuntes y totales continúan como estaban.</li>
</ul>
""",
    "1.13.9": """
<h2>Novedades de la versión 1.13.9</h2>
<ul>
  <li><b>Revisar Gemini:</b> un nuevo botón visible prepara la orden para que
      Codex compruebe disponibilidad, retirada, precio y modelos estables.</li>
  <li><b>La calidad manda:</b> la solicitud prohíbe cambiar a un modelo más
      barato si eso puede empeorar la lectura de las facturas.</li>
  <li><b>Sin cambios a ciegas:</b> el programa conserva el modelo probado y
      solo pide una migración cuando la documentación y las pruebas la avalen.</li>
</ul>
""",
    "1.13.7": """
<h2>Novedades de la versión 1.13.7</h2>
<ul>
  <li><b>Aprendizaje con contraste:</b> una corrección guardada completa CIF o
      NIF ausentes e inválidos, pero no silencia una lectura válida distinta.</li>
  <li><b>Confirmación por mayoría:</b> si tres o más facturas del mismo
      proveedor coinciden en otro identificador, se pregunta una sola vez si
      mantener el anterior, recordar el nuevo o dejar el grupo pendiente.</li>
  <li><b>Sin decisiones ocultas:</b> la memoria nunca se sustituye únicamente
      porque la IA la contradiga; la decisión final siempre es del usuario.</li>
  <li><b>Preparada para lotes grandes:</b> mantiene el procesamiento por turnos
      y bloques de 25 páginas para acotar el trabajo simultáneo en memoria.</li>
</ul>
""",
    "1.13.6": """
<h2>Novedades de la versión 1.13.6</h2>
<ul>
  <li><b>Las correcciones humanas mandan:</b> un CIF, NIF o DNI corregido se
      recuerda y prevalece sobre futuras lecturas erróneas del OCR.</li>
  <li><b>Clientes reconocidos por su nombre:</b> si su identificador sale
      cortado o mal leído, se recupera el confirmado anteriormente.</li>
  <li><b>Contado sin falsas reglas:</b> los tickets sin identificador continúan
      en amarillo para revisarlos y confirmarlos en bloque.</li>
  <li><b>Excel listo en el Escritorio:</b> se llama GASTOS_CLIENTE.xlsx o
      INGRESOS_CLIENTE.xlsx; al consolidar se limpian los Excel temporales de
      partes del mismo cliente y tipo.</li>
</ul>
""",
    "1.13.5": """
<h2>Novedades de la versión 1.13.5</h2>
<ul>
  <li><b>Archivo documental automático:</b> los PDF quedan ordenados en el
      Escritorio por cliente, ejercicio y tipo, en Gastos o Ingresos.</li>
  <li><b>También para escaneos de HP:</b> al cargar un PDF externo se guarda
      una copia documental completa sin mover el archivo original elegido.</li>
  <li><b>Lotes grandes sin archivos sobrantes:</b> las divisiones internas de
      25 páginas se eliminan después de procesarlas y no llegan a la carpeta
      del cliente.</li>
  <li><b>Una sola salida para Aplifisa:</b> se crea únicamente el Excel
      consolidado, junto a los PDF del ejercicio; ya no se generan parciales.</li>
</ul>
""",
    "1.13.4": """
<h2>Novedades de la versión 1.13.4</h2>
<ul>
  <li><b>Diseño completamente unificado:</b> se elimina la mezcla con el estilo
      gris técnico y toda la interfaz utiliza la misma tipografía Segoe UI.</li>
  <li><b>Cliente como en la referencia:</b> estado y botón Cambiar aparecen
      juntos, en una franja limpia a todo el ancho.</li>
  <li><b>Visor renovado:</b> mantiene el PDF a la derecha e incorpora indicador
      de página, controles de zoom y acceso a la vista previa grande.</li>
  <li><b>Acabado visual fiel:</b> iconos lineales, bordes ligeros, cabeceras
      azules y proporciones ajustadas al diseño aprobado.</li>
</ul>
""",
    "1.13.3": """
<h2>Novedades de la versión 1.13.3</h2>
<ul>
  <li><b>Cabecera como en el nuevo diseño:</b> los menús quedan a la izquierda
      y Abrir PDF, Escanear, Vaciar todo y Exportar a Aplifisa a la derecha.</li>
  <li><b>Barra de título oscura:</b> la ventana se integra con la cabecera azul
      del programa en Windows.</li>
  <li><b>Sin botones recortados:</b> al reducir la ventana, los accesos rápidos
      y las acciones de revisión se reorganizan en filas legibles.</li>
  <li><b>Menú más limpio:</b> «Más acciones» muestra Quitar bloque y Eliminar
      selección; Deshacer aparece solo cuando existe algo que recuperar.</li>
</ul>
""",
    "1.13.2": """
<h2>Novedades de la versión 1.13.2</h2>
<ul>
  <li><b>Nueva barra de acceso rápido:</b> abrir PDF, escanear, vaciar el lote
      y exportar a Aplifisa quedan siempre visibles bajo los menús.</li>
  <li><b>Mejor en portátiles:</b> las acciones de revisión se reparten en filas
      cortas y ya no recortan sus textos a 1024 px o con escalado de Windows.</li>
  <li><b>Cliente más compacto:</b> el selector ocupa una sola línea y deja más
      espacio para las facturas y la vista previa del documento.</li>
  <li><b>Acciones ordenadas:</b> quitar bloque, eliminar selección y deshacer
      quedan agrupadas en «Más acciones»; «Vaciar todo» permanece accesible.</li>
</ul>
""",
    "1.13.0": """
<h2>Novedades de la versión 1.13.0</h2>
<ul>
  <li><b>Cola para lotes grandes:</b> puede añadir más PDF mientras Gemini
      trabaja; se procesan por turnos sin bloquear el lote completo.</li>
  <li><b>PDF largos por partes:</b> un documento de 100 páginas se divide
      automáticamente en 4 bloques de 25 mediante PyMuPDF.</li>
  <li><b>Excel consolidado y parciales:</b> se crea el archivo completo para
      importar en Aplifisa y un Excel de control por cada parte.</li>
  <li><b>Gemini con límite de espera:</b> una página atascada termina como
      incidencia y la cola continúa con las siguientes.</li>
  <li><b>Sesión, archivo y revisión:</b> se mantienen las mejoras de guardado
      por cliente/ejercicio, recuperación del trabajo y revisión manual.</li>
</ul>
<p><b>Importante:</b> en Aplifisa importe solo el Excel consolidado. Los
Excel por partes son para control o recuperación.</p>
""",
}


def contenido(version: str) -> str:
    return NOTAS.get(version, "<h2>Novedades</h2><p>Mejoras y correcciones.</p>")


def ya_vistas(version: str) -> bool:
    return ajustes.leer("notas_version_vistas", "") == version


def marcar_vistas(version: str) -> None:
    ajustes.guardar("notas_version_vistas", version)
