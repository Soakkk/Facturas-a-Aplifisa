<!-- Revisión del 04-05/10/2026, copiada del scratchpad de la sesión (las rutas /tmp/... ya no existen). Estado de cada punto: ver PLAN-MEJORAS.md, «Para seguir». -->

## Revisión de organización: 21 propuestas, de más a menos importante

No he tocado el repo. Las pruebas, con datos inventados, están en `scratchpad/revision/organizacion/`. En la copia de trabajo hay cambios sin commit (registro_facturas.py, cuadre_anual.py y tests). Son de otra sesión y no los he tocado.

**1. El lote solo se guarda al cerrar el programa, y si no se puede recuperar se borra** [VERIFICADO]
- **Hoy:** `sesion.guardar` solo se llama desde `closeEvent` (app.py:1809) y al unir hojas (ventana_lectura.py:588). Si se va la luz, el programa se cuelga o Windows se reinicia, se pierden la revisión y la lectura ya pagada. Cuando la sesión no se puede restaurar (por ejemplo, tras una actualización), el lote se vacía en silencio (app.py:1745-1750). Al cerrar, `_guardar_sesion` ve el lote vacío y borra el fichero (1664-1666).
- **Propuesta:** guardar el lote con el mismo temporizador de 800 ms que ya guarda las muestras (app.py:146). Si no se puede restaurar, renombrar el fichero a `sesion_lote.no-recuperada-FECHA` y avisar.
- **Por qué:** horas de trabajo y dinero.
- **Esfuerzo:** pequeño.

**2. No hay copia de seguridad de nada** [VERIFICADO]
- **Hoy:** buscar «backup» o «copia de seguridad» en el código no da nada. `facturas_aplifisa.db` (registro, clientes, proveedores) funciona en modo WAL (almacen.py:106): si el asesor copia el .db a mano sin su -wal, puede perder lo último. Tampoco se copian `.clientes.json` ni las notas.
- **Propuesta:** copia diaria rotativa con `Connection.backup()`, más el índice y las notas, en `Documentación Facturas/_Copias` o en una carpeta externa. También una copia antes de cada migración o actualización, y un menú «Copia de seguridad / Restaurar».
- **Por qué:** un disco roto o un cambio de PC hoy lo pierde todo.
- **Esfuerzo:** medio.

**3. Facturas sin número: no tienen ficha y comparten PDF** [VERIFICADO, probado]
- **Hoy:** `registro_facturas.clave` devuelve None si no hay número, así que no hay aviso de «ya exportada», no salen en el expediente y el Cuadre año las da como «Falta en el programa». Además, `separar.py:99-103` da por «ya estaba» un nombre repetido sin comparar el contenido. Con dos tiques inventados de la misma gasolinera y el mismo día se creó un solo PDF, y las dos fichas apuntan a él.
- **Propuesta:** para estas facturas, identificarlas por NIF + fecha + total + huella de la hoja (`original_id`/página). En separar, comparar el contenido o numerar `_2`.
- **Por qué:** se rompe la trazabilidad justo en los tiques.
- **Esfuerzo:** medio.

**4. El registro guarda rutas absolutas y casi nadie las actualiza al mover archivos** [VERIFICADO]
- **Hoy:** solo `_cambiar_origen` llama a `cambiar_ruta` (ventana_archivo.py:321). No lo hacen «Cambiar de cliente» (dialogo_escaneos.py:200, que además renombra la factura suelta a `CLIENTE_gastos_fecha`), «Quitar» (va a una `_Papelera` plana y sin forma de restaurar, l. 307), Organizar/Deshacer ni Recoger.
- Configuración → Carpeta de documentación (app.py:1969-1976) solo cambia el ajuste: el archivo queda partido en dos, y el aviso dice que los Excel irán allí cuando siguen yendo al Escritorio. El Cuadre año marca entonces «Falta el PDF» (cuadre_anual.py:95).
- **Propuesta:** rutas relativas a la raíz del archivo más la huella; una única función de «mover» que actualice el registro; y cambiar de carpeta como mudanza guiada.
- **Esfuerzo:** medio.

**5. La cuenta recordada de un proveedor vale para todos los clientes** [VERIFICADO]
- **Hoy:** `recordar_cuenta_proveedor` (procesar.py:1197) guarda la cuenta sin cliente. `aplicar_recordado` (1216-1234) la pone en cualquier cliente y quita el aviso. Makro puede ser 600 para un bar y 629 para otro.
- **Propuesta:** guardarla por cliente y proveedor; la de otro cliente, solo como propuesta en ámbar.
- **Por qué:** un error contable sin ningún aviso.
- **Esfuerzo:** pequeño-medio.

**6. No se sabe en qué Excel salió cada factura** [VERIFICADO]
- **Hoy:** el registro guarda el nombre del Excel del Escritorio («GASTOS_CLIENTE_2.xlsx», registro_facturas.exportar), que es temporal y se repite cada trimestre. La copia archivada se llama «GASTOS 2026 2026-10-04 101500.xlsx» (expediente.py:323) y su ruta se descarta (ventana_archivo.py:284). En la base no hay ni periodo, ni orden, ni totales de cada exportación.
- **Propuesta:** tabla `exportaciones` (cliente, periodo, fecha, orden, nº de facturas, totales, ruta de la copia) y `facturas.exportacion_id`; la copia, con el periodo en el nombre («GASTOS 3T-2026…»).
- **Esfuerzo:** medio.

**7. Cambiar las columnas de la base dejaría el registro sin apuntar, sin avisar** [VERIFICADO]
- **Hoy:** almacen.py:101-104 usa `CREATE TABLE IF NOT EXISTS` y fija `user_version=1` sin migrar nada. El INSERT usa una lista fija de columnas, y `exportar()` se traga el `sqlite3.Error` y devuelve 0. Si se añade una columna, en las bases existentes no aparecería y cada exportación fallaría sin decirlo.
- **Propuesta:** migraciones numeradas por `user_version`, con copia previa, y un aviso visible cuando falle una escritura del registro.
- **Esfuerzo:** pequeño-medio.

**8. Escritorio fijo en `~/Desktop` (falla con OneDrive)** [VERIFICADO]
- **Hoy:** escaner.py:136-138, archivo.py:134/164 y ventana_comun.py:23 usan `~/Desktop`, mientras que recoger.py:55-57 sí contempla `OneDrive\Escritorio`. Con el Escritorio en OneDrive se crea una carpeta que no se ve, y el Excel y el archivo «desaparecen».
- **Propuesta:** una sola función `rutas.escritorio()` que pregunte a Windows dónde está el Escritorio (SHGetKnownFolderPath), usada en todos esos sitios.
- **Esfuerzo:** pequeño.

**9. «Deshacer organización» falla después de cualquier recogida** [VERIFICADO, probado]
- **Hoy:** `identidad_archivo.deshacer_ultimo` (l. 231) coge el último JSON de `_Organizacion`, incluidos los de las recogidas, y da el error «La ruta sale de la carpeta de escaneos». Además, no se puede deshacer una organización anterior.
- **Propuesta:** filtrar por tipo de operación, y un historial de movimientos con «deshacer» en cada uno.
- **Esfuerzo:** pequeño.

**10. Lo que el programa recuerda no se puede ver ni corregir** [VERIFICADO]
- **Hoy:** un cliente confirmado por error (clientes.py:83-98) se queda así para siempre y además se escribe en la suite. «Cambiar cliente» no desmarca al equivocado (ventana_lectura.py:431). El nombre de la carpeta lo fija el primer nombre visto (identidad_archivo.py:67-70). Un conflicto de nombres en la suite deja el nombre vacío (suite.py:86). Hay cuatro listas de clientes: la base, la suite, `.clientes.json` y el registro.
- **Propuesta:** Configuración → «Clientes y proveedores»: una ficha por NIF para editar, renombrar la carpeta (con mudanza), desmarcar y olvidar la cuenta recordada.
- **Esfuerzo:** medio-grande.

**11. El trimestre no está guiado** [VERIFICADO]
- **Hoy:** el Registro solo filtra por texto y ejercicio, y corta en 2000 filas sin decirlo (`consultar`). El informe del cuadre va al Escritorio (dialogo_cuadre.py:537) y no queda constancia de que se hizo. No se avisa de los escaneos «Sin identificar» ni de los tacos leídos sin exportar.
- **Propuesta:** «Panel del trimestre» por cliente: exportado del trimestre, último cuadre (con su informe guardado en `Nombre — NIF/2026/Cuadres`), pendientes y PDF que faltan.
- **Esfuerzo:** medio-grande.

**12. El cierre de año no existe y hay dos ZIP para lo mismo** [VERIFICADO]
- **Hoy:** «Crear ZIP del ejercicio» crea `Documentacion_2026.zip`, `_2`, `_3`… cada vez (archivo.py:354-359). Expedientes crea `Expediente 2026.zip` (expediente.py:288-296).
- **Propuesta:** un «Cerrar ejercicio» que revise lo pendiente, genere un expediente definitivo y un solo ZIP, y avise si luego entra una factura de un año ya cerrado.
- **Esfuerzo:** medio.

**13. Copia oculta y creciente de todo en %APPDATA%** [VERIFICADO]
- **Hoy:** `muestras_revision` copia cada PDF completo (l. 66-83) y cada hoja, y guarda un JSON del lote entero tras cada cambio (cada 800 ms tras editar). Nunca se borra nada. «Preparar ZIP de ejemplos» mete todos los clientes.
- **Propuesta:** un plazo de conservación, el tamaño visible en Ayuda y el ZIP solo de lo que se elija.
- **Esfuerzo:** medio.

**14. Solo cabe un lote abierto** [VERIFICADO]
- **Hoy:** hay un único `sesion_lote.pkl.gz` (sesion.py:12). Para atender a otro cliente hay que exportar o «Vaciar todo».
- **Propuesta:** «Aparcar lote» con el nombre del cliente y el periodo, y una lista de lotes aparcados.
- **Esfuerzo:** medio.

**15. El índice del archivo es frágil** [VERIFICADO]
- **Hoy:** si `.clientes.json` se daña, `leer` lanza un error (identidad_archivo.py:26-33) y ya no se archiva ni se separa nada. No hay forma de repararlo.
- **Propuesta:** guardar un `.bak` en cada escritura y un botón «Reconstruir desde las carpetas», que se llaman «Nombre — NIF».
- **Esfuerzo:** pequeño.

**16. El directorio de la suite se escribe sin bloqueo** [VERIFICADO]
- **Hoy:** `registrar_cliente` lee, modifica y reemplaza el fichero (suite.py:107-147). Si otro programa de la suite escribe entre medias, su cambio se pierde.
- **Propuesta:** un fichero de bloqueo, o volver a comprobar la fecha del fichero justo antes de reemplazarlo.
- **Esfuerzo:** pequeño.

**17. Notas de versión** [VERIFICADO]
- **Hoy:** solo se enseñan las de la versión instalada (notas_version.py:692, app.py:1518). Quien salte de la 1.19 a la 1.21 no ve las de la 1.20, que traía la pantalla nueva. Las versiones 1.13.1 y 1.13.8 se publicaron sin notas.
- **Propuesta:** enseñar todas las intermedias desde la última vista, y un test que exija notas para la versión actual.
- **Esfuerzo:** pequeño.

**18. El canal con el usuario no cierra el círculo** [VERIFICADO]
- **Hoy:** pendientes.md sigue arrastrando preguntas de la 1.13 y la 1.14 (por ejemplo, la tarifa de 3.8-flash). Las respuestas se quedan en el PC del usuario (pendientes.py:5-7), que una sesión en la nube no puede leer, y nada marca qué está contestado.
- **Propuesta:** preguntas numeradas con su estado; un botón «Enviar notas al mantenedor» que prepare un ZIP sin datos de clientes; y podar lo resuelto en cada versión.
- **Esfuerzo:** pequeño-medio.

**19. `publicar.py` hace `git add -A` en un repo público** [VERIFICADO]
- **Hoy:** la línea 112 añade todo. El .gitignore no cubre `*.zip`, `*.db`, `*.jpg/png/tif`, `*.pkl.gz` ni notas. La firma «Claude Opus 5» está fija (l. 114).
- **Propuesta:** añadir solo lo que ya está en seguimiento más una lista explícita; negarse si hay archivos sueltos sin seguimiento; ampliar el .gitignore; comprobar que hay notas y que pendientes.md está al día.
- **Esfuerzo:** pequeño.

**20. Un solo procedimiento de desarrollo escrito** [VERIFICADO]
- **Hoy:** CLAUDE.md dice una sola rama y push directo, pero el historial usa ramas y PR (#7–#13) con commits «Une la rama ya fusionada». El README manda usar `release.py`, que compila desde `C:\Users\ASESORIA`. La versión se nombra antes de que la elija publicar.py («v1.20.0: …»; el código sin commit ya habla de «antes de la 1.22»).
- **Propuesta:**
  - Escribir un solo flujo: rama, PR y publicar desde master.
  - Dejar `release.py` solo para emergencias.
  - Escribir las notas bajo «próxima» y que publicar.py les ponga el número.
  - Abrir un PR en borrador al empezar, que diga qué ficheros se tocan.
- **Esfuerzo:** pequeño.

**21. Dependencias sin fijar** [VERIFICADO]
- **Hoy:** requirements.txt usa «>=», el CI trabaja con Python 3.12 (build.yml) y en local se usa 3.11 (CLAUDE.md). El instalador se compila con lo último que haya ese día; PyMuPDF ya avisa de que `fitz` está obsoleto.
- **Propuesta:** fijar las versiones con un fichero de restricciones y usar el mismo Python en local y en el CI.
- **Esfuerzo:** pequeño.