"""Notas de parche mostradas una vez tras instalar cada versión."""

from __future__ import annotations

from . import ajustes


NOTAS = {
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
