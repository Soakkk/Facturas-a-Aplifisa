<!-- Revisión del 04-05/10/2026, copiada del scratchpad de la sesión (las rutas /tmp/... ya no existen). Estado de cada punto: ver PLAN-MEJORAS.md, «Para seguir». -->

## Revisión del funcionamiento: 20 propuestas, ordenadas de más a menos importante

No he cambiado nada en el repositorio. Las pruebas son `prueba1.py` a `prueba7.py`, con datos inventados, en `/tmp/claude-0/-home-user-Notas-Asesoria-app/80eee95a-129e-573c-8981-869185147349/scratchpad/revision/funcionamiento/`. «[VERIFICADO]» quiere decir que lo he comprobado leyendo el código o ejecutando una de esas pruebas.

**1. Inversión del sujeto pasivo, intracomunitarias e importación de servicios** [VERIFICADO] · Esfuerzo: medio
- **Hoy:** a Gemini no se le pide la mención de IVA (`extraccion.py:258-285`). Los campos `isp`, `tipo_factura`, `clave_reg_esp` y `no_sujeta` existen en `Factura`, pero nada los rellena y `gastos.xml`/`ingresos.xml` no los mapean.
  - Una compra nacional al 0 % (obra, chatarra) sale en verde: `prueba1` da B12345674 al 0 % → `ok`, sin avisos.
  - Con un NIF de la UE solo hay un ámbar genérico que se puede confirmar.
  - Una venta intracomunitaria o con inversión del sujeto pasivo al 0 % sale en verde.
- **Propuesta:** un campo cerrado `regimen_iva` (normal, ISP, intracomunitaria, servicio extranjero, exenta, no sujeta). Con IVA 0 y régimen ISP o intracomunitario, ámbar con un texto concreto, y rellenar las columnas ISP y clave de régimen especial de Aplifisa (mapeándolas en los XML).
- **Por qué:** se registra como compra al 0 % y se pierde la autorrepercusión del 303 y el 349.

**2. El régimen de recargo «por el total» depende de que el lote traiga recargo** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** `_por_el_total()` solo se cumple si hay alguna línea con recargo (`app.py:2135` y `2208-2222`). En `prueba4`, un cliente guardado como «minorista por el total» con un lote solo de luz sale con `por_el_total=False` y la fila 100/21/21 con el IVA desglosado.
- **Propuesta:** decidir por el régimen guardado del cliente (`regimen_recargo(nif)`). Añadir además un régimen «sin derecho a deducir» para actividades exentas (médico, academia) que use la misma `a_total_factura`.
- **Por qué:** Aplifisa deduce un IVA que el cliente no puede deducir.

**3. La memoria de cuentas es la misma para todos los clientes** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** `aplicar_recordado` (`procesar.py:1216`) impone la cuenta que se puso a mano en otro cliente y borra el aviso (l.1232). En `prueba2`, la cuenta 600 G01 fijada en el cliente A se aplica en el cliente C aunque Gemini proponía 622 G13, y sale en verde.
- **Propuesta:** guardar la cuenta por cliente y NIF del proveedor; la de otro cliente, solo como sugerencia en ámbar.
- **Por qué:** la cuenta depende de la actividad de cada cliente, y lo que sale en verde no se revisa.

**4. NIF «de memoria» puesto en silencio a un proveedor homónimo** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** `completar_desde_memoria` (`procesar.py:576`) busca por nombre y, si la ficha guardada es manual, no avisa (l.615). En `prueba2`, un «Talleres García S.L.» de otro cliente con el NIF vacío o ilegible recibe el NIF del homónimo y queda en verde (o «Verificada» si las dos lecturas coincidían en el NIF malo).
- **Propuesta:** siempre ámbar, salvo que lo leído sea compatible o ese proveedor ya haya facturado a ese cliente.
- **Por qué:** el gasto se imputa a otra empresa sin que nadie lo vea.

**5. Rectificativa cuya factura original no está en el lote** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** `sustituye_a` solo se usa si la original está en el mismo lote (`procesar.py:485-508`). En `prueba3`, un «abono por devolución» que sustituye a F-100, con importes en positivo, sale en verde.
- **Propuesta:** ámbar «Rectificativa de F-100: compruebe el signo y que la original esté registrada», buscándola en el registro de facturas, y tipo de factura R1-R5 si Aplifisa lo admite.
- **Por qué:** un abono en positivo suma el gasto en vez de restarlo.

**6. Documentos que no son facturas** [VERIFICADO] · Esfuerzo: medio
- **Hoy:** el esquema no tiene clase de documento (no aparece nada de proforma, albarán, presupuesto, recibo o copia). Una proforma con desglose entra como factura, y la factura real, con otro número, no salta como duplicada. La pregunta «Copia duplicada» de `pendientes.md` sigue abierta.
- **Propuesta:** un campo `tipo_documento`; lo que no sea factura, en rojo.
- **Por qué:** gasto e IVA duplicados.

**7. Facturas en otra moneda** [VERIFICADO] · Esfuerzo: medio
- **Hoy:** ni el esquema ni `Factura` tienen moneda. Una factura en USD o GBP se exporta como si fueran euros. Como mucho sale «NIF/CIF dudoso» (`validacion.py:261`).
- **Propuesta:** campo `moneda`; si no es EUR, rojo hasta poner el contravalor en euros.
- **Por qué:** base e IVA erróneos en el 303 y el 347.

**8. Tiques sin NIF del cliente e IVA no deducible** [VERIFICADO] · Esfuerzo: medio
- **Hoy:** un tique sin destinatario solo avisa de «rol dudoso» (`prueba3`) y su cuota se exporta como deducible. No hay ningún control de deducibilidad.
- **Propuesta:** ámbar «IVA no deducible: ¿registrar por el total?», con botón que aplique `a_total_factura`. Que Gemini marque además restauración, atenciones y regalos (art. 96 LIVA).
- **Por qué:** es un ajuste típico en las comprobaciones de la AEAT.

**9. El aviso de «ya exportada» se pierde si cambia el NIF o la fecha leída** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** la identidad es lado | NIF (o nombre) | número | fecha (`registro_facturas.py:61-80`). En `prueba6`, una factura exportada sin NIF y releída con NIF no se reconoce como exportada.
- **Propuesta:** una segunda búsqueda por número y total, ignorando NIF y fecha, con ámbar «posiblemente ya exportada».
- **Por qué:** en los requerimientos se vuelve a escanear lo ya registrado.

**10. Fechas sin normalizar en el Excel** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** `fecha_de` acepta cinco formatos (`validacion.py:72`), pero `_valor_celda` escribe el texto tal cual (`exportar.py:77`) y `verificar_excel` lo da por bueno. En `prueba1`, «2026-03-05» y «05/03/26» salen en verde y llegan así al Excel.
- **Propuesta:** normalizar a dd/mm/aaaa al construir la factura, al editar la celda y al exportar (también la fecha de operación).
- **Por qué:** Aplifisa puede rechazarlas o leer el año como 1926.

**11. El bien de inversión nunca va a la 200** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** la cuenta «200 BIENES DE INVERSION» se quita de la lista que se da a Gemini (`extraccion.py:110`) y `es_bien_inversion` solo pone un aviso (`procesar.py:366`). Con «Marcar revisada» sale con la cuenta de gasto.
- **Propuesta:** proponer la 200 (200) en ámbar y exigir que se confirme la cuenta.
- **Por qué:** el IVA de bienes de inversión va en casillas propias del 303 y hay que amortizar.

**12. Una factura de otro año queda en rojo sin salida** [VERIFICADO] · Esfuerzo: medio
- **Hoy:** `_aviso_ejercicio` es un error (`ventana_validacion.py:160` y `279`) y no se puede exportar ni marcándola revisada (lo fija `test_app_core.py:140`). Una factura del 28/12 recibida en enero obliga a cambiar la fecha o a sacarla del lote. `fecha_deduccion` existe en el modelo y en Aplifisa, pero no está mapeada. Además contradice `validacion.py:229`, que dice que una fecha antigua no se marca.
- **Propuesta:** ámbar confirmable con «Registrar en el periodo de deducción», rellenando `fecha_deduccion` y mapeándola en el XML.
- **Por qué:** deducir en un periodo posterior (art. 99 LIVA) es habitual.

**13. La doble lectura no compara lo contable** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** `CAMPOS_COMPARADOS` (`doble_lectura.py:16`) no incluye cuenta, subclave, bien de inversión, `sustituye_a`, fecha de operación ni tipo o base de IRPF. Dos lecturas con 622 frente a 200 y bien de inversión sí/no dan `comparar() == []` y la factura sale «Verificada».
- **Propuesta:** compararlos; si la cuenta difiere, ámbar con las dos propuestas.
- **Por qué:** la segunda lectura ya se paga.

**14. Cliente homónimo de uno ya confirmado** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** `analizar_cliente` (`procesar.py:115`) cambia el NIF leído por el del cliente confirmado cuando coincide el nombre. En `prueba7`, un fontanero homónimo con NIF válido (X1234567L) pasa a ser el cliente 12345678Z con 1001 puntos y se propone como cliente del lote sin preguntar.
- **Propuesta:** sustituir el NIF solo si el leído está vacío o no es válido.
- **Por qué:** el lote entero se iría a otro cliente (Excel y archivo).

**15. Tolerancia fija de 0,02 € en la cuota** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** con base 12.345,67 y cuota impresa 2.592,62 (redondeo por línea) sale en rojo (`validacion.py:310`). Como el rojo no se puede confirmar, hay que teclear una cuota distinta de la impresa.
- **Propuesta:** tolerancia proporcional a la base y a las líneas, y las diferencias pequeñas en ámbar.
- **Por qué:** se acaba registrando una cuota que no es la de la factura.

**16. IRPF sin control de tipo ni de base** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** solo se comprueba base × % (`validacion.py:345`). Un 1,5 % pasa en verde, y una base de IRPF distinta de la de IVA también. En ventas solo se vigila el 1 % de los transportistas.
- **Propuesta:** tipos admitidos {1, 2, 7, 15, 19, 24} y ámbar si la base de IRPF no coincide con la de IVA.
- **Por qué:** modelos 111, 115 y 130.

**17. Huecos de numeración de ventas solo dentro del lote** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** `huecos_de_numeracion` recibe solo las filas del lote abierto (`ventana_validacion.py:477`). Si falta la primera venta de un trimestre, no se ve.
- **Propuesta:** continuar la serie con la última venta exportada que consta en el registro.
- **Por qué:** una venta que falta es un ingreso sin declarar.

**18. Tipos de IVA y de recargo que no dependen de la fecha** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** el 5 %, 2 % y 7,5 % se aceptan en cualquier año (`validacion.py:32`). A la tabla de recargos (l.25) le faltan el 1,75 % del tabaco (todas las facturas de un estanco saldrían en ámbar) y el 0,62/0,26/1 % de 2023-24.
- **Propuesta:** tabla de tipos según la fecha de la factura y tabla de recargos completa.
- **Por qué:** menos falsos ámbar y más lecturas malas detectadas.

**19. Al separar PDF, un nombre repetido se da por «ya guardado»** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** `separar.py:100` decide solo por el nombre del archivo. En `prueba5`, las facturas «A/1» y «A:1» del mismo día generan un solo PDF, y la ficha de la segunda apunta al PDF de la primera.
- **Propuesta:** comparar el contenido del PDF con la huella que ya calcula `identidad_archivo` y, si es otro documento, guardar con «_2».
- **Por qué:** el cuadre anual dice «todo bien» con un PDF que no es.

**20. Palabras clave con raíz que nunca coinciden** [VERIFICADO] · Esfuerzo: pequeño
- **Hoy:** `_contiene` busca la palabra entera (`conceptos.py:81`), así que «notari», «registr», «abogad» y «telefon» no encuentran notaría, registro, abogado ni Telefónica. En `prueba1` todas caen en 629 por descarte y la subclave de la 628 no se detecta.
- **Propuesta:** tratar esas claves como prefijo (`\bclave\w*`).
- **Por qué:** cuando Gemini no da una cuenta válida, la cuenta de respaldo sale peor y hay más ámbar.

Mirados sin encontrar huecos de peso: varias páginas, varios tipos de IVA, abonos con el signo detrás, suplidos, duplicados dentro del lote y el cuadre anual. El contraste de `registro.contrastar` empareja por orden de filas, pero el cuadre anual ya lo resuelve mejor.
