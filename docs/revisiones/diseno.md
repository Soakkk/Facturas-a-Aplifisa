<!-- Revisión del 04-05/10/2026, copiada del scratchpad de la sesión (las rutas /tmp/... ya no existen). Estado de cada punto: ver PLAN-MEJORAS.md, «Para seguir». -->

## Revisión de diseño de Facturas a Aplifisa 1.21.0: 21 propuestas

**Cómo lo he revisado.** He sacado capturas reales con QT_QPA_PLATFORM=offscreen y 14 facturas inventadas. Hay capturas de las 5 distribuciones a 1366×768 y a 1920×1080, y de la 4 a 1366×697, que es lo que queda útil en un portátil de 1366×768 con barra de tareas y título. También del estado vacío y del diálogo de cuadre. He probado el teclado con QTest.

Aquí no hay Segoe UI y la he sustituido por Liberation Sans, así que las medidas son aproximadas (±5 %). No he tocado nada del repo. Las modificaciones sin confirmar que aparecen (cuadre_anual.py, registro_facturas.py y dos tests) ya estaban al empezar.

**Capturas más ilustrativas** (carpeta `/tmp/claude-0/-home-user-Notas-Asesoria-app/80eee95a-129e-573c-8981-869185147349/scratchpad/revision/diseno/`):
- `principal_cuadre_1366x697_real.png`: en el portátil la tabla enseña una sola factura.
- `principal_tras_exportar_1366x697.png`: el aviso de exportación aplasta la tabla y monta los filtros unos encima de otros.
- `principal_cuadre_1920x1080.png`: el asa gris de 88 px y la columna Total fuera de la vista.
- `dialogo_cuadre_resultado.png`: el diálogo «Cuadre año» con el filtro y «Qué pasa» cortados.
- Extra: `simulacion_portatil_compacto.png` (simulación de la propuesta 1).

---

**1. En un portátil solo se ven 1 o 2 facturas.**
- **Hoy:** en la distribución 4 a 1366×697 la tabla mide 39 px de alto, es decir, una fila. Se lo comen el menú (40), la cinta (73), la alerta (62), la barra de filtros y acciones (104) y los totales (207). A 1366×768 se ven 3 filas.
- **Propuesta:** un modo compacto automático cuando el alto sea menor de 800:
  - la alerta en una sola línea;
  - filtros y acciones de la tabla en una sola fila (ver 9);
  - los totales plegados a una línea («Gastos 3T · base… · IVA… · total… ▸ Su suma») que se despliega al cuadrar.
- **Simulado en memoria:** se pasa de 2 a 9 filas visibles.
- **Por qué:** es la pantalla donde pasa horas.
- **Esfuerzo:** medio.

**2. Asa de 88 px entre la hoja y lo leído.**
- **Hoy:** en las distribuciones 3 y 4 el divisor `splitFactura` en horizontal mide 88 px y se ve como un bloque gris con ⋮. La causa es `margin: 40px 2px` en estilo.py, que suma 80 px al ancho del asa. Lo he reproducido aislado con el tema: en vertical mide 12 px.
- **Propuesta:** quitar ese margen y pintar la barra corta en `_Asa.paintEvent`.
- **Por qué:** son 80 px menos de hoja y parece un panel roto.
- **Esfuerzo:** pequeño.

**3. Los avisos empujan la tabla.**
- **Hoy:** `BandaAvisos` va dentro del layout.
  - Cada Ctrl+Intro saca «1 línea(s) revisada(s)…» durante 10 s; la tabla baja unos 40 px y luego vuelve a subir.
  - El resumen de exportación se queda fijo (`segundos=0`) y en el portátil deja la tabla a 0 px.
- **Propuesta:**
  - el aviso flotando encima del contenido, sin mover nada;
  - el resumen de exportación en una línea con «Ver detalle»;
  - Ctrl+Z (fuera de una celda en edición) para deshacer la última revisión.
- **Esfuerzo:** medio.

**4. No se puede revisar sin ratón.**
- **Hoy:**
  - Intro y Ctrl+Intro solo funcionan con el foco en la tabla (`TablaFacturas.keyPressEvent`). Tras pulsar «Revisada» o «Usar este», Ctrl+Intro ya no hace nada (comprobado).
  - Tab no sale de la tabla: tras 60 pulsaciones seguía en las celdas. Por eso «Es correcto» y «Usar este» no se alcanzan con el teclado.
  - No hay Ctrl+F para el buscador ni teclas para el zoom de la hoja.
- **Propuesta:**
  - atajos de ventana: Ctrl+Intro, Ctrl+F, Alt+1/Alt+2 (quedarse con la lectura 1 o la 2), Ctrl+más/menos/0 para la hoja, y F6 para pasar de tabla a factura y a totales;
  - `setTabKeyNavigation(False)` en la tabla;
  - que los botones de la tarjeta devuelvan el foco a la tabla.
- **Esfuerzo:** medio.

**5. Los importes no se ven en la tabla.**
- **Hoy:**
  - La tabla pide 939 px. A 1366 la distribución 4 le da 607 y se corta en «Nombre»; a 1920 tampoco se ve «Total».
  - En la 1 a 1366, al elegir una celda la tabla se desplaza y desaparece la columna Estado.
  - En la 5 el Total sale cortado («498,»), contra la regla de `MINIMO` de que un importe nunca se corta.
- **Propuesta:**
  - Cuenta y GXX en una sola columna («628 G16»);
  - Tipo como una chapa estrecha G/I;
  - Estado fija a la izquierda;
  - el ancho del Total reservado.
- **Ahorro:** unos 130 px.
- **Esfuerzo:** medio.

**6. El botón Exportar no dice si se puede exportar.**
- **Hoy:** está activo aunque haya 4 facturas en ámbar. Al pulsarlo sale la ventana «Revisión pendiente». Cuando sí se puede, aparece `DialogoOrden` en cada exportación, aunque recuerda la elección anterior.
- **Propuesta:**
  - el botón muestra «Faltan 4» y su clic lleva a la siguiente pendiente;
  - con todo listo, un botón partido «Exportar · por fecha ▾».
- **Por qué:** una ventana y dos clics menos por cliente y trimestre.
- **Esfuerzo:** pequeño.

**7. «Cuadre año» pierde el resultado.**
- **Hoy:**
  - `DialogoCuadre` es modal. «Ver en el lote» lo cierra y para ver la siguiente hay que volver a cargar el listado y pulsar «Cuadrar».
  - Mide 1180×760 fijo y no cabe en los ~728 px útiles de un portátil de 768.
  - El filtro sale como «Solo lo q…».
  - «Qué pasa», donde va la pista de cuál podría ser, se corta.
  - Los trimestres van en 9 columnas que alternan programa y Aplifisa, y el descuadre solo se marca en rojo.
- **Propuesta:**
  - ventana no modal que se conserva;
  - cuadrar en cuanto se carga el listado;
  - un panel con el detalle de la línea elegida;
  - por trimestre «Programa | Aplifisa | Diferencia» con ✓ o ≠;
  - tamaño ajustado a la pantalla.
- **Esfuerzo:** medio.

**8. Dos cuadres con cuatro nombres.**
- **Hoy:** «Cuadrar» (Ctrl+R) en la cinta es «Comprobar registro de Aplifisa…» en el menú. «Cuadre año» (Ctrl+Shift+R), que admite cualquier periodo, es «Cuadre con Aplifisa: lo guardado en PDF…». Los dos piden el mismo listado. «Cuadre año» usa el icono de «Registro», y «Registro» es otra cosa.
- **Propuesta:** un solo «Cuadrar con Aplifisa» que carga el listado una vez y enseña «este lote» y «todo lo guardado del cliente» en dos pestañas.
- **Esfuerzo:** medio.

**9. Barra de la tabla con duplicados y dos papeleras iguales.**
- **Hoy:**
  - «Siguiente incidencia», «Ver incidencias» y «Correcta · siguiente» llevan casi al mismo sitio. «Marcar revisada» y «Revisada» hacen lo mismo.
  - En el portátil, «Quitar bloque» y «Eliminar» son dos papeleras rojas idénticas, solo con icono.
  - No hay menú de clic derecho en las filas.
- **Propuesta:** quitar de la barra lo que ya está en la tarjeta de la factura, y llevar a un clic derecho y a un botón «⋯» lo ocasional (unir hojas, eliminar, quitar bloque, ¿De dónde sale?, abrir el PDF). Libera una fila entera.
- **Esfuerzo:** pequeño.

**10. La alerta cuenta otra cosa que el semáforo.**
- **Hoy:** pone «Atención: 1 aviso que revisar» con 4 filas en «! Revisar». `_pintar_alerta` solo cuenta duplicadas, fuera de periodo, huecos de numeración y sustituidas. Ocupa 62 px.
- **Propuesta:** una línea tipo «4 por revisar · 1 fuera del 3T · Siguiente (Intro)», con el mismo recuento que la barra de estado.
- **Esfuerzo:** pequeño.

**11. Menús donde no se encuentra nada.**
- **Hoy:**
  - Abrir PDF, Exportar y Vaciar no están en ningún menú.
  - Registro y Expedientes están dentro de «Escaneos».
  - «Examen de precisión» aparece dos veces (Configuración y Ayuda).
  - En Ayuda está «Pedir revisión del modelo Gemini», que prepara una orden para Codex.
  - No hay letras de acceso rápido (&), y los atajos solo se descubren en los globos.
- **Propuesta:**
  - menús Archivo y Revisar, cada orden con su atajo;
  - «&» en todos los menús;
  - quitar lo que es de desarrollo.
- **Esfuerzo:** pequeño.

**12. La ventana no recuerda su tamaño.**
- **Hoy:** abre siempre a 1420×820, más que un portátil, y no guarda ni la posición ni si estaba maximizada.
- **Propuesta:** guardar y restaurar la geometría; en pantallas pequeñas, abrir maximizada.
- **Esfuerzo:** pequeño.

**13. Estado vacío sin guía.**
- **Hoy:** sin nada cargado, la tabla está en blanco. «Correcta · siguiente» sale azul y activa, igual que Copiar, Listado PDF, Vaciar todo y las casillas de Su suma. El visor pide usar «Abrir PDF o imágenes», pero el botón se llama «Abrir PDF».
- **Propuesta:** en la tabla, botones grandes «Escanear (Ctrl+E)» y «Abrir PDF (Ctrl+O)» y el «arrastre aquí»; el resto desactivado, con el motivo en el globo.
- **Esfuerzo:** pequeño.

**14. Cerrar un cliente y empezar otro.**
- **Hoy:** «Vaciar todo» está pegado a «Escanear», no se puede deshacer y hace la misma pregunta aunque el lote ya esté exportado.
- **Propuesta:**
  - tras exportar, ofrecer «Empezar otro cliente» en el aviso;
  - llevar «Vaciar» al menú;
  - en la pregunta, distinguir entre «exportado» y «N revisadas sin exportar».
- **Esfuerzo:** pequeño.

**15. Textos que engañan.**
- **Hoy:**
  - La ficha del semáforo ámbar dice «Se puede exportar, pero conviene mirarla antes», y en realidad no se exporta hasta marcarla (`ficha_incidencias.EXPLICACION`).
  - El aviso «El total no cuadra: factura pone 45.2… = 42.59» va con punto decimal (validacion.py:370).
  - «Ventas» en la barra de estado frente a «Ingresos» en los filtros.
  - «mes: 0,00 € de 5,00 €» no dice que es el gasto de Gemini.
  - «Cuadre año» sirve para cualquier periodo.
  - Se le trata de usted en todo salvo en «Para mejorar el programa» («tus notas»).
  - La casilla de recargo está marcada y no se puede desmarcar: es un rótulo disfrazado de casilla.
- **Propuesta:** corregir cada uno, formato español con € en todos los avisos, y una chapa en vez de la casilla.
- **Esfuerzo:** pequeño.

**16. Daltonismo y contraste.**
- **Hoy:**
  - El semáforo lleva símbolo y texto, eso está bien.
  - Pero la celda culpable distingue error de aviso solo por el color (#ffcdd2 frente a #fff3cd), y los trimestres del cuadre igual.
  - Los ceros en #9AA9B8 tienen un contraste de 2,4:1.
  - Los bordes de las casillas (#DCE5F0) tienen 1,27:1 y las de «Su suma» casi no se ven.
- **Propuesta:**
  - ✕ o ! en la celda culpable y ≠ en el cuadre;
  - ceros en #8495A6 (3,07:1);
  - bordes de las casillas a 3:1 o más.
- **Esfuerzo:** pequeño.

**17. Colores fuera del sistema.**
- **Hoy:** hay 33 colores sueltos fuera de estilo.py. El ámbar del semáforo es #86500A y el de la ficha emergente #A16207; `dialogo_registro` usa otra paleta (#fee2e2/#dcfce7).
- **Propuesta:** colores de estado centralizados en estilo.py (texto, fondo y borde para correcto, revisar, error e información), usados en todas partes.
- **Esfuerzo:** pequeño a medio.

**18. Iconos de la cinta.**
- **Hoy:** cuatro carpetas (Abrir PDF, Escaneos, Recoger, Expedientes); Registro y Cuadre año comparten icono; Escanear lleva una impresora; los trazos van en dos tonos de azul.
- **Propuesta:** un icono distinto por función y un solo tono. Juntar los cuatro de archivo, que hoy ocupan 318 px, en un botón «Archivo ▾» libera unos 240 px para el cliente.
- **Esfuerzo:** pequeño.

**19. Letra pequeña para jornadas largas.**
- **Hoy:** la letra base es de 12 px, muchos rótulos van a 11 px y los títulos de la ficha a 10 px. No hay ajuste dentro del programa.
- **Propuesta:** Ver → Tamaño de letra (normal/grande), con la escala desde un único valor y un mínimo de 11 px.
- **Esfuerzo:** medio.

**20. «Lo leído» repite avisos.**
- **Hoy:** «La cuenta 623 necesita subclave…» sale dos veces: `repartir` en ventana_ficha.py lo apunta una vez por concepto y otra por subclave. La ficha del semáforo sale de solo 200 px de ancho y repite lo mismo.
- **Propuesta:** quitar duplicados, y que el clic en el semáforo lleve a «Por revisar» de la ficha en vez de abrir otra ventana.
- **Esfuerzo:** pequeño.

**21. Escanear el siguiente taco.**
- **Hoy:** cada Ctrl+E abre el diálogo y el Tipo vuelve siempre a «Gastos», porque `recordar()` no lo guarda.
- **Propuesta:** recordar el tipo y añadir «Escanear otro igual» (Ctrl+Mayús+E) sin diálogo.
- **Esfuerzo:** pequeño.

Los scripts (`capturas.py`, `capturas2.py`, `teclado.py`, `simulacion.py`) están en la misma carpeta que las capturas.