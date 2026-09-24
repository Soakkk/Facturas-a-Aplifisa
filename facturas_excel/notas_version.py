"""Notas de parche mostradas una vez tras instalar cada versión."""

from __future__ import annotations

from . import ajustes


NOTAS = {
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
