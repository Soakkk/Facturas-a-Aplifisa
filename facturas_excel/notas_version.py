"""Notas de parche mostradas una vez tras instalar cada versión."""

from __future__ import annotations

from . import ajustes


NOTAS = {
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
