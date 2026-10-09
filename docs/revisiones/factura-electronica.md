<!-- Investigación del 09/10/2026 (consulta del usuario: el escáner es el cuello de botella). Copiada de la sesión; cada informe va seguido de su verificación adversarial, que corrige al informe donde discrepan. -->

# Factura electrónica, Verifactu y captura con el móvil

**Informe: cómo aliviar el escáner que frena la entrada de facturas (estado a 9 de octubre de 2026)**

**Limitación del método.** Desde este entorno no se pudo abrir boe.es, la sede de la AEAT ni otras webs: WebFetch daba error de DNS y el proxy respondía 403 a curl. Todo dato externo sale de los extractos que da el buscador de esas páginas. Las páginas oficiales se citan con su URL de boe.es, agenciatributaria o hacienda. Lo que solo aparece en despachos o blogs va marcado como «secundaria». Las URL están numeradas al final.

---

## 0. Lo que dice el código (repo `/home/user/facturas-a-aplifisa`, sin modificar)
- **Máquina actual.** Es una HP LaserJet Pro M148 (`facturas_excel/escaner.py:48`, `:262`).
- **Alimentador.** WIA solo devolvía la primera hoja del taco, así que el alimentador se maneja con NAPS2 (`escaner.py:70-79`). Se escanea a 200 ppp por defecto (`escaner.py:62`) y cada taco tiene un tope de 45 minutos (`escaner.py:79`).
- **Formatos que acepta la app.** `.pdf .png .jpg .jpeg .tif .tiff .bmp` (`facturas_excel/ventana_comun.py:61`; imágenes en `facturas_excel/pdf.py:19`). **No acepta HEIC.**
- **Sin lector de XML ni de QR.** Busqué `ubl|facturae|verifactu|qr|zxing|pyzbar|heic` en `facturas_excel/` y no hay resultados. Los `.xml` que existen son solo plantillas de exportación a Aplifisa (`ventana_aplifisa.py:453-454`).
- **Idea del QR ya apuntada.** El lector de QR Verifactu figura como idea en `PLAN-MEJORAS.md:290-296`, pero ahí pone «Verifactu 2026+», y esa fecha ya no vale.

## 1. Factura electrónica obligatoria entre empresas y autónomos (Ley 18/2022, art. 2 bis de la Ley 56/2007)

**Aprobado**
- **Real Decreto 238/2026, de 25 de marzo.** Publicado en el BOE núm. 79 el 31/03/2026 (BOE-A-2026-7295) y en vigor desde el 20/04/2026 [1][4].
- **Orden HAC/1028/2026, de 2 de octubre.** Regula la solución pública de facturación electrónica de la AEAT. Publicada en el BOE el 05/10/2026 (BOE-A-2026-20587) y en vigor desde el **06/10/2026**. Con ella empiezan a contar los plazos [2][3].
- **Calendario según la AEAT, contado desde el 06/10/2026** [3]:
  - **06/10/2027:** empresas y autónomos con volumen de operaciones superior a 8 M€ el año anterior. Deben emitir, remitir y recibir factura electrónica, e informar del estado y del pago de cada factura.
  - **06/10/2028:** el resto, es decir, pymes y autónomos (también los de módulos). Deben emitir, remitir y recibir. Las sociedades de 8 M€ o menos además informan de estados y pagos.
  - **06/10/2029:** las personas físicas y entidades en atribución de rentas empiezan a informar de estados y pagos.
  - La solución pública debe estar disponible al menos 2 meses antes de la primera fecha (disposición adicional 5.ª del Real Decreto) [1]. Eso da, como muy tarde, en torno al 06/08/2027. Es un cálculo mío.
- **Formatos.** Mensaje estructurado según la norma europea EN 16931, en sintaxis UBL, CII, EDIFACT o Facturae [1][38].
  - Peppol BIS vale entre plataformas privadas [1].
  - La solución pública trabaja en UBL. Quien emita por una plataforma privada debe enviar a la vez a la solución pública una copia fiel en UBL [1][37].
  - Las plataformas deben poder convertir a todos los formatos admitidos (secundaria [37]).
- **Exclusiones.**
  - Quedan fuera los tiques (facturas simplificadas, art. 4.1). No quedan fuera las simplificadas cualificadas, las del art. 7.2 del RD 1619/2012, que llevan el NIF del destinatario [1].
  - Por orden ministerial se pueden excluir sectores (art. 4.2) [7].
  - La obligación solo existe si emisor y destinatario son empresarios o profesionales establecidos en España [1].
  - No encontré ninguna exclusión por estar en módulos o en recargo de equivalencia, pero no pude comprobarlo en el texto completo.
- **Régimen transitorio (disposición transitoria 2.ª).** Durante 12 meses, quien supere 8 M€ debe acompañar cada factura con un PDF legible, salvo que el destinatario acepte recibir solo el original. Ese PDF no se envía a la solución pública (secundaria [37]).
- **Acceso a las facturas recibidas (Orden, arts. 9 a 11)** [5]:
  - El destinatario puede recuperar sus facturas recibidas «en cualquier momento», directamente o con acceso automatizado (servicios web), o mediante un formulario.
  - Un tercero puede hacerlo si está **apoderado**. Para la vía del formulario tiene que estar inscrito en el **Registro de apoderamientos de la AEAT** (art. 11.2).
  - Si el certificado de colaborador social sirve también para esto: no confirmado.

**Respuesta a la pregunta clave**
- Sí. Cuando el proveedor del cliente esté obligado, cada factura entre empresas (excepto los tiques) existirá en XML UBL en la solución pública. La asesoría, como apoderada, podría descargarla e importarla sin escanear ni usar IA.
- Para eso hace falta escribir un importador UBL, que la app hoy no tiene.
- **Inferencia mía, no lo dice ninguna fuente expresamente:** las facturas de proveedores de más de 8 M€ ya llegarían en XML desde el **06/10/2027**. Me baso en que la disposición transitoria 2.ª les obliga a adjuntar el PDF «para el resto de empresarios». Esto afectaría a mayoristas, distribuidoras y suministradoras, que es justo lo que compran los clientes en recargo de equivalencia.
- De forma general, todas las facturas entre empresas llegarían en XML desde el **06/10/2028**.
- Seguirán llegando en papel los tiques, las facturas de proveedores extranjeros y los gastos que no sean entre empresas.

**Borrador o superado**
- El proyecto de orden sometido a audiencia en abril de 2026 preveía empezar el 01/10/2026 [6]. Lo ha sustituido la orden publicada.
- El entorno de pruebas de la solución pública no tiene fecha confirmada.

## 2. Verifactu (RD 1007/2023)

**Vigente por ley**
- El RDL 15/2025, de 2 de diciembre, se publicó en el BOE el 03/12/2025 (BOE-A-2025-24446) [9][11]. El Congreso lo convalidó por resolución de 11/12/2025 (BOE-A-2025-25695) [10].
- Fechas que fija: **01/01/2027** para los sujetos al Impuesto sobre Sociedades y **01/07/2027** para el resto, autónomos incluidos.

**Solo anunciado, no es norma**
- La nota de prensa de Hacienda de 05/10/2026 habla de una «previsión» de aplazar las obligaciones pendientes hasta **octubre de 2028**, para que coincidan con la factura electrónica de quienes facturan 8 M€ o menos [12].
- No está publicada en el BOE ni tiene día exacto. El «6 de octubre de 2028» que dan algunos blogs es una suposición suya [13].

**¿Da acceso a las facturas recibidas?** Solo en parte.
- Desde el 23/04/2025 la sede de la AEAT tiene, para destinatarios, un servicio de cotejo por QR y una página para consultar y descargar los registros que envían los sistemas VERI*FACTU [14][16].
- Solo aparecen las facturas de emisores que trabajan en modalidad VERI*FACTU, que hoy es voluntaria. Los programas en modalidad «No VERI*FACTU» no envían nada.
- Verifactu regula solo los programas de facturación. Una factura hecha a mano no genera ningún registro [19].
- No confirmado: si la vista del destinatario muestra el desglose de base y cuota, y si un apoderado puede entrar a consultarla.
- El receptor también puede enviar voluntariamente a la AEAT los datos del QR [15].

**¿El QR permite leer los datos sin IA?** Sí, pero solo cuatro.
- El QR contiene una URL de la AEAT (`www2.agenciatributaria.gob.es/…/TIKE-CONT/ValidarQR`, o `ValidarQRNoVerifactu`) con estos parámetros: `nif` (del emisor), `numserie`, `fecha` (DD-MM-AAAA) e `importe` (total). La base es el art. 21 de la Orden HAC/1177/2024 (secundaria [18]). Una fuente añade un hash; no confirmado.
- Se lee con una librería de QR como zxing-cpp o pyzbar, sin IA.
- No incluye base imponible, tipos, cuotas, recargo, retención ni el NIF del receptor.
- **No evita escanear el papel.** Solo sirve para comprobar lo que lee Gemini, que es lo que ya prevé `PLAN-MEJORAS.md:290-296`.
- La app de la AEAT hace el cotejo y responde «encontrada», «no encontrada» o «no verificable» [17].

## 3. Otras vías para que entre menos papel
- **Facturas que ya llegan en PDF por correo.** No hace falta imprimirlas: se pueden reenviar solas a un buzón de la asesoría y cargarlas directamente, porque la app acepta PDF (`ventana_comun.py:61`).
  - Gmail: filtro con la acción «Reenviar a». La dirección tiene que estar verificada, solo afecta a correos nuevos y en Google Workspace debe permitirlo el administrador [22].
  - Outlook: regla de reenvío automático [23].
- **Suministradoras, telefonía, bancos y seguros.**
  - El art. 2 de la Ley 56/2007 obliga a las empresas de especial trascendencia económica (electricidad, agua, gas, telecomunicaciones, entidades financieras, seguros, transporte, etc.) a ofrecer un medio telemático con el historial de facturación de **al menos los últimos 3 años** [8][20].
  - El art. 2 bis.3 da derecho a pedir copia gratis durante **4 años** desde la emisión [8].
  - Los umbrales de plantilla y volumen no los confirmé.
  - No encontré ninguna figura legal que dé acceso directo al asesor. En la práctica sería con las credenciales del cliente o poniendo el correo de la asesoría como destino de la factura electrónica; no confirmado.
  - Que los bancos entreguen facturas de terceros: no confirmado.
- **FACe** es solo para facturas a Administraciones Públicas. **FACeB2B** es para subcontratistas de contratos públicos (art. 216 de la Ley de Contratos del Sector Público) y uso voluntario entre empresas [21]. Ninguna de las dos sirve para recoger las facturas de los clientes.

## 4. Captura con el móvil
- **iPhone, apps Notas y Archivos («Escanear documentos»).** Captura automática o manual, ajuste de las esquinas, varias páginas, sale **PDF**. Desde Archivos se elige dónde guardarlo [24].
- **Google Drive (Android e iOS), botón Escanear.** Marca el recorte con un contorno azul, captura automática o manual, filtros, varias páginas. Sale **PDF con texto buscable**; en Android se puede elegir .pdf o .jpg [25]. En Android, Files by Google también guarda en PDF [39].
- **Adobe Scan, gratis.** Captura automática con detección de bordes, varias páginas, sale **PDF** y permite exportar a JPEG. Exportar a Word o Excel, comprimir y poner contraseña son de pago [26].
- **Microsoft Lens: retirado.**
  - Empezó a retirarse el 09/01/2026.
  - Salió de las tiendas y se quedó sin soporte el 09/02/2026.
  - **Desde el 09/03/2026 no permite escanear.**
  - Microsoft recomienda el escáner de la app OneDrive, que no guarda copia en el teléfono [27]. Que saque PDF o JPG lo dicen respuestas de la comunidad, no Microsoft [28].
- **HEIC.** La cámara del iPhone guarda en HEIF por defecto. Con «Ajustes > Cámara > Formatos > Más compatible» guarda en JPEG [29]. Como la app no acepta HEIC, conviene que los clientes usen el escáner de Notas o Archivos, que da PDF, o que activen esa opción.
- **Velocidad.**
  - No encontré ninguna comparación medida en condiciones controladas.
  - Un caso de Engadget (2014): unos 45 s para 5 páginas con el móvil, unos 9 s por hoja [30].
  - Con un soporte para el móvil, la foto tarda alrededor de 1 s; lo que más tiempo lleva es colocar cada hoja [31].
  - Mi estimación, sin fuente: 5 a 10 s por hoja con el móvil.
- **Comparación con escáneres de alimentador automático.**
  - **HP M148** (la de la asesoría): unos 15 ppm según un minorista, para el modelo M148fdw; bandeja de 35 hojas. Su hermana M149fdw no escanea a doble cara por el alimentador [32]. Ninguno de estos datos está confirmado para la M148 exacta.
  - **ScanSnap iX1600:** 40 ppm, 80 caras por minuto a doble cara, bandeja de 50 hojas [33]. Según un listado de terceros no tiene driver TWAIN/ISIS [34], así que podría no funcionar con el flujo NAPS2/WIA de la app (`escaner.py:70-79`).
  - **Ricoh fi-8170:** 70 ppm, 140 caras por minuto, unas 100 hojas, compatible con TWAIN/ISIS según distribuidores [35].

## Conclusiones
1. **Ya hoy:** reenvío automático de los PDF que llegan por correo, y que el propio cliente capture con el móvil (en PDF, no HEIC). Así el papel no llega al escáner. Lo que siga llegando en papel se atasca en la HP M148, que parece lenta (a una cara, unos 15 ppm, 35 hojas; datos no oficiales). Un escáner de documentos a doble cara con TWAIN o WIA iría bastante más rápido.
2. **Verifactu:** no da acceso general a las facturas recibidas hasta que sea obligatorio. Por ley eso es el 01/01/2027 o el 01/07/2027; anunciado, octubre de 2028. El QR solo permite validar 4 datos; no ahorra escanear.
3. **Factura electrónica:** es la vía que de verdad elimina el papel y la IA. Habría que descargar el UBL de la solución pública como apoderado, a partir del 06/10/2027 para los proveedores de más de 8 M€ (inferencia) y del 06/10/2028 para todos. Requiere apoderamiento inscrito en el registro de la AEAT y un importador UBL en la app, que hoy no existe. Los tiques seguirán en papel.

**Fuentes**
[1] https://www.boe.es/buscar/act.php?id=BOE-A-2026-7295
[2] https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-20587
[3] https://sede.agenciatributaria.gob.es/Sede/todas-noticias/2026/octubre/7/solucion-publica-facturacion-electronica.html
[4] https://sede.agenciatributaria.gob.es/static_files/Sede/Actualidad/Novedades/2026/Nota_informativa_RD_Facturacion.pdf
[5] https://noticias.juridicas.com/base_datos/Fiscal/1013629-orden-hac-1028-2026-de-2-oct-regula-la-solucion-publica-de-facturacion-electronica.html
[6] https://www.hacienda.gob.es/sgt/normativadoctrina/proyectos/16042026-proyecto-pom-factura-electronica.pdf
[7] https://www.iustel.com/diario_del_derecho/noticia.asp?ref_iustel=1264482
[8] https://www.boe.es/buscar/act.php?id=BOE-A-2007-22440
[9] https://www.boe.es/buscar/doc.php?id=BOE-A-2025-24446
[10] https://www.boe.es/buscar/doc.php?id=BOE-A-2025-25695
[11] https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/nota-informativa-ampliacion-plazo-adaptacion-facturacion.html
[12] https://www.hacienda.gob.es/sgt/gabsehacienda/nota-informativa-verifactu.pdf
[13] https://www.afiris.es/verifactu-aplazamiento/
[14] https://sede.agenciatributaria.gob.es/Sede/todas-noticias/2025/abril/30/servicios-verifactu-disponibles.html
[15] https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/preguntas-frecuentes/posibilidad-remision-informacion-factura-parte-receptor.html
[16] https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/preguntas-frecuentes/sistemas-verifactu.html
[17] https://sede.agenciatributaria.gob.es/Sede/ayuda/consultas-informaticas/aplicaciones-moviles-aeat-ayuda-tecnica/gestiones-disponibles-app-agencia-tributaria/notificaciones-cotejo-documentos-electronicos.html
[18] https://www.codigonext.com/recursos/verifactu-codigo-qr/ ; https://quaderno.io/es/articulos/facturacion-electronica/codigo-qr-factura/
[19] https://sede.agenciatributaria.gob.es/Sede/normativa-criterios-interpretativos/analisis/El__Reglamento_Veri_factu_.html
[20] https://www.garrigues.com/es_ES/noticia/obligacion-de-facilitar-los-usuarios-un-medio-de-interlocucion-telematica-entrada-en-vigor
[21] https://administracionelectronica.gob.es/pae_Home/va/dam/jcr:b4f787dd-a794-49d4-9b7e-fbc2c7bb734f/2019-01_nota-tecnica-FACeB2B.pdf
[22] https://support.google.com/mail/answer/10957?hl=en
[23] https://support.microsoft.com/es-es/outlook/mail/use-rules-to-automatically-forward-messages
[24] https://support.apple.com/en-us/108963
[25] https://support.google.com/drive/answer/3145835?hl=en&co=GENIE.Platform%3DAndroid ; https://support.google.com/drive/answer/3145835?hl=en&co=GENIE.Platform%3DiOS
[26] https://www.adobe.com/devnet-docs/adobescan/android/en/scan.html ; https://www.adobe.com/acrobat/mobile/scanner-app.html
[27] https://support.microsoft.com/en-us/lens/retirement-of-microsoft-lens
[28] https://learn.microsoft.com/en-us/answers/questions/5805252/file-type-for-onedrive-capture-(former-lens)
[29] https://support.apple.com/en-us/116944
[30] https://www.engadget.com/2014-04-10-scanbot-the-only-scanner-youll-need.html
[31] https://terrywhite.com/tag/scandock/
[32] https://galaxus.be/en/s1/product/hp-m148fdw-laserjet-pro-laser-black-and-white-printer-10885759 ; https://hp.com/bd-en/products/printers/product-details/product-specifications/22954498
[33] https://www.pfu.ricoh.com/global/scanners/scansnap/ix1600/
[34] https://sabeswings.com/2023/09/fujitsu-scansnap-ix1600-scanner-driver.html
[35] https://scannerone.com/product/ricoh-fi-8170/
[37] https://marimon-abogados.com/aprobacion-del-rd-238-2026-que-desarrolla-el-sistema-espanol-de-facturacion-electronica-obligatoria-b2b/
[38] https://www.forvismazars.com/es/es/insights/alertas/alertas-fiscales/rd-238-2026-facturacion-electronica
[39] https://support.google.com/files/answer/15598575?hl=en-GB

## Verificación

**Verificación adversarial del informe «aliviar el escáner…» (9/10/2026)**

**Límites de esta pasada.**
- WebFetch también falla con DNS (`getaddrinfo ENOTFOUND www.boe.es`, y lo mismo con cuatrecasas.com).
- curl devuelve `CONNECT tunnel failed, response 403`.
- El límite de búsquedas web del turno, compartido con los demás agentes, se agotó tras 5 consultas. No lo he sorteado.
- Por eso casi todo lo legal y lo de las apps del móvil queda **no verificado**. Lo del escáner y el código sí está comprobado.
- Teniendo en cuenta lo que aclara el usuario (el cuello de botella es la máquina escáner), las correcciones más importantes son las de la sección de hardware.

---

## A. Código (/home/user/facturas-a-aplifisa, solo lectura)

| Afirmación | Veredicto |
|---|---|
| HP M148 en `escaner.py:48`, `:262` | **Confirmada.** El código dice «HP M148» y «HP LJ Pro M148», sin sufijo dw ni fdw. |
| WIA solo da la 1.ª hoja y por eso se usa NAPS2 (`escaner.py:70-79`) | **Confirmada** (comentario en `:71-75`). **Falta un dato:** NAPS2 se llama con `"--driver", "wia"` (`escaner.py:422`) y la lista de escáneres sale solo de `WIA.DeviceManager` (`escaner.py:155`, `escaneres()` en `:158-177`). Hoy la app solo ve y maneja escáneres con driver **WIA**. |
| 200 ppp por defecto (`escaner.py:62`) | **Confirmada.** En el diálogo, además, vienen por defecto «grises» (`dialogo_escaneo.py:80`), el alimentador (`:107`) y una sola cara (`:110`). |
| Tope de 45 min por taco (`escaner.py:79`) | **Corregida.** La constante existe, pero el tope no funciona. El bucle `for linea in proceso.stdout` (`escaner.py:437`) se queda bloqueado antes de llegar a `proceso.wait(timeout=…)` (`:442`), y nada mata el proceso. Está documentado en `docs/revisiones/aplicacion.md:103-105`, marcado como [VERIFICADO]. |
| Extensiones aceptadas (`ventana_comun.py:61`, `pdf.py:19`); no acepta HEIC | **Confirmada.** No hay ninguna referencia a heic ni heif en `facturas_excel/`. |
| No hay lector de XML ni de QR; la búsqueda no da resultados | **Confirmada con matices.** Buscando palabras completas (`grep -w`) no sale nada. Buscando subcadenas sin distinguir mayúsculas salen falsos positivos (`QRectF` en `visor.py:8`, `QRadioButton`…). Sí hay un lector de XML, pero de configuración, no de facturas (`config_columnas.py:1-10`, con `xml.etree`). Conviene decir «sin lector de facturas XML». |
| Los `.xml` son plantillas de exportación (`ventana_aplifisa.py:453-454`) | **Confirmada con matiz.** Son `config/gastos.xml` y `config/ingresos.xml`, la configuración de columnas del gestor fiscal que lee `config_columnas.py:1-5`. |
| Idea del QR en `PLAN-MEJORAS.md:290-296` con «Verifactu 2026+» | **Confirmada.** El título está en `:289` y «Verifactu 2026+» en `:296`. |
| Omisiones relevantes | - El alimentador de la M148 arrastra hojas pegadas: hay un aviso por recuento y por huecos en la numeración (`config/pendientes.md:263-266`) y un consejo de abanicar el taco (`:439-440`).<br>- Ya existe una vía para fotos del móvil: `--import` (`app.py:3098`), usada por la app «Escáner Fotos» (`docs/revisiones/aplicacion.md:69`; `PLAN-MEJORAS.md:298-300`).<br>- En `pendientes.md:441-443` está pendiente vigilar una carpeta para las fotos del móvil. |

## B. Escáneres (lo más relevante para el usuario)

| Afirmación | Veredicto |
|---|---|
| M148fdw: unos 15 ppm y bandeja de 35 hojas | **Confirmada, pero solo con minoristas.** - Galaxus: https://galaxus.be/en/s1/product/hp-m148fdw-laserjet-pro-laser-black-and-white-printer-10885759<br>- Paklap: https://www.paklap.pk/hp-laserjet-pro-m148fdw-printer-pakistan.html<br>- No hay ficha oficial de HP para la M148. No consta si los 15 ppm son en B/N o en color, ni el dato de la M148dw. Un listado da además «ADF 3», que es claramente un error. |
| La M149fdw no escanea a doble cara por el ADF | **Confirmada.** La ficha de HP dice «Duplex ADF scanning: No» y bandeja de 35 hojas: https://hp.com/bd-en/products/printers/product-details/product-specifications/22954498. Para la M148 es una inferencia. **Consecuencia que el informe no menciona:** la casilla «Escanear las dos caras» (`dialogo_escaneo.py:109`, que pasa `--source duplex` en `escaner.py:423`) probablemente no sirve con esta máquina. |
| ScanSnap iX1600: 40 ppm, 80 caras/min, 50 hojas | **Confirmada:** https://www.pfu.ricoh.com/global/scanners/scansnap/ix1600/. Matiz: es a 300 ppp en color, en los modos Auto, Normal, Better y Best. En «Excellent» baja a 10 ppm: https://www.pfu-apac.ricoh.com/kr/scanners/scansnap/ix1600/ |
| iX1600 sin TWAIN ni ISIS | **No verificable con el fabricante.** Solo lo dice un revendedor, que además marca descatalogada la versión blanca: https://scannerone.com/product/fujitsu-scansnap-ix1600-white/. Tampoco he confirmado si sigue a la venta o si tiene sucesor. |
| Ricoh fi-8170: 70 ppm, 140 caras/min, unas 100 hojas, TWAIN/ISIS | **Confirmada.** 100 hojas de 80 g/m², unas 10.000 hojas al día.<br>- https://www.uk.shi.com/product/46058818/Ricoh-fi-8170-Document-scanner<br>- https://eshop.comfeel.cz/fujitsu-skener-fi-8170-a4-pruchodovy-70ppm-600dpi-lan-rj45-1000-usb-3-2-adf-100listu-10000-listu-za-den<br>- https://sourceit.com.sg/products/fujitsu-fi-8170-a4-adf-scanner-pa03810-b051<br>**Lo que falta:** ninguna fuente menciona driver WIA, y la app hoy exige WIA. Que funcione con la app no está confirmado. |
| «Un escáner a doble cara con TWAIN o WIA iría más rápido» | **Corregida.** Con el código actual tiene que ser **WIA** (`escaner.py:155`, `:422`). Uno que solo tenga TWAIN obligaría a cambiar `--driver wia` y la forma de listar los dispositivos. |

## C. Factura electrónica

**Confirmadas**
- **RD 238/2026, de 25 de marzo**, publicado en el BOE el 31/03/2026. Modifica el RD 1619/2012 y su aplicación es escalonada: primero quienes facturan más de 8 M€ y después el resto. Todo depende de la entrada en vigor de la orden.
  - https://www.cuatrecasas.com/es/spain/fiscalidad/art/reglamento-facturacion-electronica-obligatorio-operaciones
  - https://sede.agenciatributaria.gob.es/Sede/eu_es/todas-noticias/2026/marzo/31/facturacion-electronica-obligatoria.html
- **El art. 9 del RD 1619/2012, en la redacción del RD 238/2026, está en vigor desde el 20/04/2026** (Iberley, solo ese artículo): https://www.iberley.es/legislacion/articulo-9-reglamento-regulan-obligaciones-facturacion
- **Orden HAC/1028/2026, de 2 de octubre.** BOE núm. 247 del 05/10/2026, BOE-A-2026-20587: https://www.boe.es/boe/dias/2026/10/05/pdfs/BOE-A-2026-20587.pdf
  - Su preámbulo exige enviar a la solución pública una copia fiel a la vez que se emite.
  - El destinatario debe comunicar el pago completo o el rechazo.
- **La referencia [7] existe:** https://laadministracionaldia.inap.es/noticia.asp?id=1264482

**No verificadas**
- BOE núm. 79 y BOE-A-2026-7295.
- Entrada en vigor de la orden el 06/10/2026.
- **Calendario 06/10/2027, 06/10/2028 y 06/10/2029.** La búsqueda dice expresamente que no encontró fechas concretas.
- Disposición adicional 5.ª (disponibilidad 2 meses antes), formatos y Peppol, exclusiones del art. 4, disposición transitoria 2.ª del PDF y arts. 9 a 11 de la orden con el registro de apoderamientos.
- Proyecto de orden de abril con inicio el 01/10/2026.
- El cálculo 06/10/2027 menos 2 meses = 06/08/2027 es aritméticamente correcto.

## D. Verifactu, Ley 56/2007, FACeB2B, apps del móvil y HEIC

**No verificado nada externo:**
- RDL 15/2025 y su convalidación, con las fechas 01/01/2027 y 01/07/2027. Coinciden con lo que yo sabía, pero sin fuente en esta pasada.
- Nota de Hacienda del 05/10/2026.
- Parámetros del QR y art. 21 de la Orden HAC/1177/2024.
- Art. 2 de la Ley 56/2007 (3 años) y art. 2 bis.3 (4 años).
- FACeB2B y el art. 216 de la LCSP.
- Gmail, Outlook, Notas, Drive y Adobe Scan.
- HEIC con «Más compatible».
- Engadget 2014 y Terry White.

**Incoherencia interna:** el informe dice «desde el 23/04/2025», pero la URL que cita [14] es una noticia del 30/04/2025. Hay que revisarlo.

**Fechas de Microsoft Lens (09/01, 09/02 y 09/03/2026):** no verificadas. Yo recordaba un calendario de retirada a finales de 2025. No está confirmado; hay que comprobarlas contra [27].

---

## Correcciones que hay que aplicar al informe
1. **§0, «tope de 45 minutos».** Sustituir por: «Hay una constante de 45 min (`escaner.py:79`), pero el tope no funciona. El bucle de salida (`:437`) bloquea antes de `wait` (`:442`) y no se mata el proceso (`docs/revisiones/aplicacion.md:103-105`)».
2. **§0, alimentador.** Añadir que NAPS2 se ejecuta con `--driver wia` (`escaner.py:422`) y que los escáneres se listan solo por WIA (`escaner.py:155-177`).
3. **§0, lectores.** Cambiar «sin lector de XML» por «sin lector de facturas XML» (existe `config_columnas.py`, que lee XML de configuración). Aclarar que la búsqueda vacía es por palabra completa.
4. **§4 y conclusión 1.** Cambiar «con TWAIN o WIA» por «con driver WIA, o TWAIN cambiando el código».
   - fi-8170: WIA no confirmado.
   - iX1600: sin TWAIN según un revendedor y sin WIA confirmado. Con la app actual, probablemente no funciona.
5. **§4, M148.** Añadir que la casilla «dos caras» (`dialogo_escaneo.py:109`, que pasa `--source duplex` en `escaner.py:423`) probablemente no funciona en esta máquina (inferido de la M149fdw). Añadir también los atascos de hojas pegadas documentados (`config/pendientes.md:263-266`, `:439-440`). Los 15 ppm siguen siendo de un minorista y no se sabe si son en B/N o en color.
6. **§4, iX1600.** Matizar que 40 ppm es en los modos normales a 300 ppp, y 10 ppm en «Excellent». No está confirmado si sigue a la venta.
7. **§3 y §4, captura con el móvil.** Mencionar que ya existe la vía «Escáner Fotos» con `--import` (`app.py:3098`, `PLAN-MEJORAS.md:298-300`) y la idea pendiente de vigilar una carpeta (`config/pendientes.md:441-443`).
8. **§2, fecha de [14].** Revisar «23/04/2025» frente a la URL de [14], que es del 30/04/2025.
9. **§4, Microsoft Lens.** Volver a comprobar las fechas de retirada contra [27], porque no están confirmadas.
10. **§1.** Indicar que el calendario 2027, 2028 y 2029 y la entrada en vigor de la orden el 06/10/2026 siguen sin confirmar con una fuente leída. Está confirmado que la orden existe, que se publicó el 05/10/2026 y que los plazos cuentan desde su entrada en vigor.
11. **Enfoque.** Dado que el usuario aclara que el cuello de botella es la máquina, conviene poner primero la sección de escáneres, con el requisito WIA como criterio de compra. Verifactu y la factura electrónica deberían ir después, como vías a medio plazo.

