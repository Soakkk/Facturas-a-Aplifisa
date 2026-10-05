<!-- Revisión del 04-05/10/2026, copiada del scratchpad de la sesión (las rutas /tmp/... ya no existen). Estado de cada punto: ver PLAN-MEJORAS.md, «Para seguir». -->

**Revisión de estructura de «Facturas a Aplifisa»: 20 propuestas, de más a menos importante**

Lo he medido en la rama `claude/serene-franklin-7smpxl`. Ahí hay cambios sin commit de otra sesión en `registro_facturas.py`, `cuadre_anual.py` y en las pruebas; no los he tocado. No he cambiado nada del repo. Mis scripts están en `.../scratchpad/revision/estructura/`.

- **Pruebas:** pasan las 668 en 70,7 s en Linux; la más lenta tarda 1,5 s. El problema no es la lentitud, son los cuelgues.
- **Cobertura:** sin medir, porque coverage no está instalado.
- **Corrección al encargo:** el CI sí tiene caché (`cache: pip` en build.yml:28 y :49).

**1. Los fallos de la base de datos se callan, también el registro de lo exportado [VERIFICADO]**
- **Hoy:** `almacen.py:179`, `:195` y `:217` y `registro_facturas.py:265` (HEAD) capturan `sqlite3.Error` y devuelven {}, None, 0 o False. Además, `ventana_aplifisa.py:519` no mira lo que devuelve `historial.registrar`. Lo probé con la base inaccesible: `registrar` da 0, `buscar` da None y `ajustes.leer` da el valor por defecto, sin aviso y sin línea en errores.log.
- **Propuesta:** que la escritura falle de forma visible y la exportación avise «no quedó apuntada». Que la lectura deje constancia en errores.log.
- **Por qué:** si la exportación no queda apuntada, el aviso «YA EXPORTADA» no sale la próxima vez y la factura se registra dos veces en Aplifisa.
- **Esfuerzo:** pequeño.

**2. El lote en curso se pierde sin avisar [VERIFICADO]**
- **Hoy:** `sesion.py` guarda con pickle los objetos internos (Factura, bloques). Si falla al cargar, `cargar()` devuelve None (`sesion.py:46`) y, al cerrar, `_guardar_sesion` borra el fichero (`app.py:1665`). Lo probé con una clase que ya no existe: se restauraron 0 filas y el fichero acabó borrado.
- **Propuesta:** guardar en JSON con versión (`dataclasses.asdict`). Si no carga, renombrarlo a `.roto`, apuntarlo en errores.log y avisar.
- **Por qué:** renombrar o mover un campo en `modelo.py` borra el trabajo a medio revisar.
- **Esfuerzo:** medio.

**3. Los dos «deshacer» comparten carpeta y se estorban [VERIFICADO]**
- **Hoy:** «Organizar carpetas» y «Recoger sueltos» escriben en `_Organizacion`. `deshacer_ultimo` (`identidad_archivo.py:230`) lee también los registros de recogida. Lo reproduje: tras una recogida, «Deshacer organización» da «La ruta sale de la carpeta de escaneos» y ya no deja deshacer la organización real. Con una recogida vacía salta un `KeyError 'indice_despues'` que nadie captura. Además hay dos `_trasladar` casi iguales con comprobaciones distintas (`identidad_archivo.py:176` y `recoger.py:401`).
- **Propuesta:** filtrar por `"tipo"` o usar subcarpetas, y dejar un solo `_trasladar`.
- **Esfuerzo:** pequeño.

**4. `VentanaPrincipal` lo hace todo [VERIFICADO]**
- **Hoy:**
  - `app.py` tiene 2.872 líneas; la clase sola, 2.708 líneas y 111 métodos.
  - Con los 5 mixins suma 233 métodos, unas 5.900 líneas y 160 atributos distintos.
  - `_crear_interfaz` mide 712 líneas (`app.py:163`).
  - Los mixins usan 65 atributos que solo se crean en `app.py` (29 de ellos en `ventana_validacion`).
  - El cliente del lote (`_cliente_nif`/`_cliente_nombre`) no se crea en `__init__`; se lee con 29 `getattr(..., "")`.
- **Propuesta:** un `EstadoLote` sin Qt y con tipos (filas, bloques, cliente, periodo, duplicados), y partir `_crear_interfaz` por tarjetas.
- **Por qué:** dos asistentes editan a la vez un fichero de 2.900 líneas, con conflictos y efectos cruzados.
- **Esfuerzo:** grande, por pasos.

**5. Reglas fiscales metidas en la parte de Qt**
- **Hoy:** viven en `_revalidar_fila` (`ventana_validacion.py:96`) o en métodos del mismo mixin:
  - IRPF del 1 % de transportistas, detectado por «TRANSPORT» en el nombre (`:343-358`);
  - avisos de periodo y ejercicio;
  - duplicados y catálogo de cuentas.
  También hay tolerancias de cuadre en `ventana_ficha.py:382` y `dialogo_cuadre.py:393`. Por eso 401 de 633 pruebas (29 de 55 ficheros) montan la ventana entera, con 97 instanciaciones.
- **Propuesta:** una función pura `revalidar(estado) -> resultados`; la ventana solo pinta.
- **Esfuerzo:** medio.

**6. Cinco criterios distintos de «mismo proveedor» [VERIFICADO]**
- **Hoy:** son `procesar._mismo_nombre` (:50), `procesar.nombres_compatibles` (:1112), `cuadre_anual.nombres_parecidos` (:239), `clientes._clave_nombre` (:119) y `registro_facturas._nombre_clave` (nuevo, sin commit). Dan respuestas distintas para el mismo par:
  - «GARCIA LOPEZ JOSE» y «GARCIA LOPEZ MARIA»: compatibles sí, parecidos no, `_mismo` sí.
  - «BAR ESQUINA» y «BAR CENTRAL»: compatibles sí.
  - «Bar La Esquina, S.L.» y «BAR ESQUINA SL»: la clave de clientes es distinta y la del registro es igual.
- **Propuesta:** un `nombres.py` con una sola forma de trocear el nombre y 2 o 3 funciones públicas con el nombre de su uso, más una tabla de casos parametrizada común.
- **Esfuerzo:** medio.

**7. La clave guardada del registro depende de reglas que cambian**
- **Hoy:** la clave es `cliente#lado|NIF|número|fecha` (`registro_facturas.py:71-86`). El cambio en curso mete el nombre usando listas privadas de `procesar` (`_FORMAS_JURIDICAS`, `_PALABRAS_VACIAS`). Si alguien afina esas listas, cambian en silencio las claves ya guardadas. Y una fecha corregida después de exportar da otra clave, así que no sale «ya exportada».
- **Propuesta:** un normalizador de clave propio y congelado, con su versión, pruebas de claves fijas y una búsqueda de respaldo por NIF + número.
- **Esfuerzo:** medio.

**8. Cuatro maneras de limpiar un NIF [VERIFICADO]**
- **Hoy:** `procesar.py:32`, `clientes.py:37`, `suite.py:35` y `registro_facturas.py:40`. «B/12345674» queda con la barra en tres de ellas y sin barra en `clientes`. Con un espacio duro, «B 12345674» solo sale en `procesar`.
- **Propuesta:** una única `normaliza_nif` pública junto a `validar_nif`.
- **Esfuerzo:** pequeño.

**9. Cinco lectores de importes [VERIFICADO]**
- **Hoy:** `extraccion._num`, `registro._num`, `doble_lectura._numero`, `tabla_facturas.parse_numero` y `consulta._importe_buscado`.
  - «1.234» da 1,234 en extracción y 1234 en la tabla.
  - «28,20-» da None en la tabla.
  - «1,234.56» da 1,23456 en tres de ellos.
  - Como `procesar` importa `extraccion._num`, arrastra google.genai: 0,53 de los 0,57 s que tarda en cargar.
- **Propuesta:** un `numeros.py` con una sola función de lectura.
- **Esfuerzo:** pequeño.

**10. Tolerancias repartidas [VERIFICADO]**
- **Hoy:** hay 0,02 en 4 constantes y 0,011 en `doble_lectura.py:26`, más 18 cifras sueltas (por ejemplo `dialogo_registro.py:119` y `su_suma.py:535`). `_cerca` está repetida en `registro.py:694` y `cuadre_anual.py:407`.
- **Propuesta:** un `importes.py` con `TOLERANCIA` y `cerca()`.
- **Esfuerzo:** pequeño.

**11. La base SQLite no tiene migraciones de esquema**
- **Hoy:** `almacen.py:104` escribe `user_version = 1` en cada arranque y nunca lo lee. Como solo hay `CREATE TABLE IF NOT EXISTS`, una columna nueva no llegaría a las bases que ya existen. El cambio en curso reutiliza la tabla `migraciones` como bandera (`_migrar_claves_sin_nif`, que se llama en cada `_con()`).
- **Propuesta:** migraciones numeradas por `user_version`, cada una en su transacción, con una prueba que parta de una base v1.
- **Esfuerzo:** medio.

**12. Las pruebas pueden colgarse sin que nadie se entere**
- **Hoy:**
  - El código tiene 83 ventanas que esperan respuesta (QMessageBox y `.exec()`).
  - Las pruebas solo las anulan una a una (23 parches).
  - `conftest.py` no tiene una red de seguridad general.
  - No hay pytest.ini ni pytest-timeout.
  - El job de CI no tiene `timeout-minutes`, así que puede esperar hasta 360 min.
- **Propuesta:**
  - una fixture común que haga fallar con un mensaje claro cualquier QMessageBox, `QDialog.exec` o QInputDialog que no esté previsto;
  - `faulthandler_timeout=60` en pytest.ini (viene con pytest, no hay que instalar nada);
  - pytest-timeout en el CI;
  - `timeout-minutes: 20` en el job.
- **Esfuerzo:** pequeño.

**13. Las líneas de IVA son facturas sueltas**
- **Hoy:** `Factura` tiene 46 campos. Una factura con dos tipos de IVA son dos objetos que repiten la cabecera, unidos por `documento_id`/`lineas_factura` (38 usos en 10 ficheros). Los cambios de cabecera se copian a mano (`CAMPOS_CABECERA`, `app.py:79` y `:2304`).
- **Propuesta:** un `Documento(cabecera, lineas, revision)` en el núcleo, y desplegarlo en filas solo para la tabla y el Excel.
- **Por qué:** desaparecen los fallos de «una línea con otra fecha o NIF».
- **Esfuerzo:** grande.

**14. Funciones privadas usadas desde otros módulos [VERIFICADO]**
- **Hoy:** hay 25 importaciones de nombres con «_» entre módulos (por ejemplo `cuadre_anual.py:46-50` y `localizar.py:142`) y 37 accesos del tipo `modulo._x`. Las pruebas tocan 130 atributos privados de la ventana en 401 sitios.
- **Propuesta:** hacer públicas las que se comparten y dar a la ventana unos pocos métodos públicos para las pruebas.
- **Esfuerzo:** medio.

**15. Errores de los hilos sin traza [VERIFICADO]**
- **Hoy:** hay 54 `except Exception`.
  - `hilos.py:93`, `:128` y `:157` solo pasan el texto del error: no hay traza ni línea en errores.log.
  - `hilos.py:65` convierte cualquier fallo, incluido un error de programación, en «hoja ilegible».
  - `app.py:1806-1811` se calla si falla guardar la sesión.
- **Propuesta:** apuntar la traza con `errores.apuntar` en cada uno y capturar solo errores de API o de red.
- **Esfuerzo:** pequeño.

**16. `Fila` a medio pasar de diccionario a clase**
- **Hoy:** `lote.py:118-135` mantiene el acceso como diccionario. Quedan 49 accesos `fila["…"]` frente a 64 por atributo, y una errata al escribir crea un atributo nuevo sin fallar. Los bloques siguen siendo diccionarios (25 accesos).
- **Propuesta:** terminar el cambio, con `slots=True` y un `Bloque` como clase.
- **Esfuerzo:** pequeño.

**17. El CI prueba con otra versión de Python y sin lint [VERIFICADO]**
- **Hoy:** el CI usa Python 3.12 (`build.yml:27` y `:48`) y el desarrollo, 3.11. pyflakes no se pasa; da 36 avisos:
  - 23 reexportaciones de `app.py`;
  - 2 variables muertas (`archivo.py:63` y `identidad_archivo.py:237`);
  - 7 en las pruebas.
- **Propuesta:** igualar la versión, declarar las reexportaciones en `__all__` y añadir un paso de pyflakes o ruff.
- **Esfuerzo:** pequeño.

**18. Dependencias sin fijar [VERIFICADO]**
- **Hoy:** `requirements.txt` solo pone «>=». El venv tiene google-genai 2.26.0 frente a «>=1.0». PyMuPDF 1.28.2 avisa de que `import fitz` desaparecerá, y hay 19 usos en 16 ficheros. pyinstaller y pytest también van sin versión.
- **Propuesta:** versiones exactas para el build y pasar a `import pymupdf`.
- **Esfuerzo:** pequeño.

**19. `publicar.py` es frágil**
- **Hoy:**
  - `git add -A` (`:112`) en un repo público cuyo .gitignore no excluye jpg, png, json, csv ni zip.
  - pytest se lanza sin timeout y con la salida capturada (`:99`), así que si algo falla no se ve qué.
  - master y la etiqueta se suben por separado (`:118-119`); si el otro sube entre medias, quedan commit y etiqueta locales y el siguiente rebase choca en `__init__.py`.
  - El README manda usar `release.py`, que tiene una ruta fija `C:\Users\ASESORIA` (`release.py:16`).
- **Propuesta:**
  - `git add -u` más una lista explícita;
  - timeout en pytest y enseñar su salida;
  - `git push --atomic origin master vX`;
  - marcar `release.py` como obsoleto.
- **Esfuerzo:** pequeño.

**20. El actualizador no tiene pruebas**
- **Hoy:** ninguna prueba importa `updater.py`, y si la release no trae `.sha256` instala sin verificar (`:85`, `:104`).
- **Propuesta:** pruebas con respuestas falsas de la API y exigir el hash.
- **Esfuerzo:** pequeño.
