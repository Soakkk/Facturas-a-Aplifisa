<!-- Investigación del 09/10/2026 (consulta del usuario: el escáner es el cuello de botella). Copiada de la sesión; cada informe va seguido de su verificación adversarial, que corrige al informe donde discrepan. -->

# La HP M148 frente a escáneres de documentos

**Resumen:** la M148 es lenta por diseño. Escanea a una sola cara, a 15 ppm como máximo, con un alimentador de 35 hojas. No admite papel más pequeño que A5 ni más fino de 70 g/m², así que los tiques tienen que ir por el cristal uno a uno. Recomiendo el **Brother ADS-4300N (unos 349 €)**, con el **Epson ES-580W (unos 428 €)** como alternativa. En hojas A4 a una cara se gana unas 2,5 veces de velocidad nominal, a doble cara unas 5 veces, y los tiques pasan a ir en el mismo taco. Los ScanSnap quedan descartados porque NAPS2 no puede manejarlos (no tienen driver TWAIN ni WIA).

**Límites de la consulta:** WebFetch no resolvía casi ningún dominio (naps2.com, hp.com, pccomponentes, ricoh). Por eso los datos externos vienen de resúmenes de WebSearch y, en el caso de NAPS2, del código fuente leído en raw.githubusercontent.com. Los precios son capturas de buscador de fecha desconocida; hay que comprobarlos antes de comprar.

## 1. HP LaserJet Pro MFP M148dw / M148fdw (ficha oficial de HP)

| Dato | Valor | Fuente |
|---|---|---|
| Capacidad del alimentador | 35 hojas | https://support.hp.com/gb-en/document/c06165582 |
| Velocidad de escaneo | «Scan speed (normal): Up to 15 ppm». La ficha no dice a qué resolución ni en qué modo de color (no confirmado). Una copia de la hoja de datos de la M148dw da 16 ppm, posiblemente en tamaño carta (no confirmado) | c06165582 · https://www8.hp.com/h20195/V2/GetPDF.aspx/c07874033 · https://www.printerbase.co.uk/media/pdf/hp-m148dw.pdf |
| Doble cara por el alimentador | **No** («Duplex ADF scanning: No»). La doble cara solo se puede hacer a mano: escanear, dar la vuelta al taco y volver a escanear | c06165582 · https://h30434.www3.hp.com/t5/Scanning-Faxing-Copying/Does-the-LaserJet-Pro-MFP-M148dw-support-double-sided/td-p/7508967 |
| Resolución por el alimentador | Hasta 300×300 ppp | c06165582 |
| Tamaño mínimo / máximo en el alimentador | **148,5×210 mm** (A5) / 215,9×355,6 mm. Los tiques no caben | c06165582 |
| Gramaje en el alimentador | 70–90 g/m². No he confirmado cuánto pesa el papel térmico habitual | c06165582 |
| Detección de doble alimentación | No aparece en la ficha de HP (no confirmado) | c06165582 |
| Estado | «Discontinued» en HP EE. UU. | https://www.hp.com/us-en/shop/pdp/hp-laserjet-pro-mfp-m148dw |

## 2. Alternativas

| Modelo | ppm a una cara / ipm a doble cara | Bandeja | Doble cara en una pasada | Doble alimentación por ultrasonidos | Tiques / papel largo | Red o botón | TWAIN / WIA | Precio en España (orientativo) | Estado |
|---|---|---|---|---|---|---|---|---|---|
| **Brother ADS-4300N** | 40 / 80, carta a 300 ppp ([brother-usa](https://www.brother-usa.com/p/desktop-scanners/ADS4300N)) | 80 | Sí | **Sí** ([store.brother.co.uk](https://store.brother.co.uk/devices/scanners/ads/ads4300n)) | Mínimo 50,8×50,8 mm ([hoja de datos UE](https://www.brother.eu/-/media/product-downloads/devices/scanners/ads/ads4300n/ads-4300n-datasheet.pdf)); hoja portadora para papel más pequeño o de menos de 0,08 mm ([manual](https://www.manualslib.com/manual/2968699/Brother-Ads-4300n.html?page=39)); papel largo 5000 mm a 200 ppp | Escaneo a red SMB/FTP/SFTP sin PC ([store.brother.es](https://store.brother.es/devices/scanners/ads/ads4300n), [soporte](https://support.brother.com/g/s/id/htmldoc/ads/cv_ads4300n/spa/html/GUID-E163C9DB-B686-4406-8D09-D106AC35D5E5_55.html)). Solo cable, sin Wi-Fi | TWAIN, WIA, SANE (store UK) | 349 € ([PcComponentes](https://www.pccomponentes.com/brother-ads-4300n-escaner-profesional-de-sobremesa-con-conexion-a-red-cableada)) | SHI lo marca como fin de vida ([shidirect](https://www.shidirect.com/Product/44600511/Brother-ADS-4300N-Document-scanner)); sigue a la venta en España |
| Brother ADS-4700W | 40 / 80 | 80 | Sí | **Sí** ([store UK](https://store.brother.co.uk/devices/scanners/ads/ads4700w)) | Papel largo 5000 mm a 200 ppp | Igual que el 4300N, más Wi-Fi y pantalla táctil | TWAIN, ISIS, WIA ([CDW](https://www.cdw.com/product/brother-ads-4700w-document-scanner-desktop-usb-3.0-lan-wi-fin/7030197)) | Unos 526 € ([PcComponentes](https://www.pccomponentes.com/brother-ads-4700w-escaner-profesional-de-sobremesa-con-red-cableada-y-wifi)) | Brother EE. UU. aún lo vende |
| Brother ADS-1800W | 30 / 60, A4 a 300 ppp ([hoja de datos](https://www.brother.eu/-/media/product-downloads/devices/scanners/ads/ads-1800w-datasheet/ads-1800w.pdf)) | **20** | Sí | **No** ([B&H](https://www.bhphotovideo.com/c/product/1837721-REG/brother_compact_desktop_scanner_with.html)) | Mínimo unos 51×70 mm, según tiendas (sin confirmar en fuente oficial) | Wi-Fi | TWAIN, WIA | Unos 328 € ([PcComponentes](https://www.pccomponentes.com/brother-ads-1800w-escaner-documental-compacto-con-alimentador-de-documentos-adf-wifi-duplex)) | Actual |
| Epson ES-580W | 35 / 70, carta a 300 ppp ([ficha Epson](https://mediaserver.goepson.com/ImConvServlet/imconv/c87169a20c75647a66d95f808c6e71daabc18bb2/original?assetDescr=WorkForce_ES-580W_Scanner_Specification_Sheet_CPD-59548.pdf)) | 100 | Sí | **Sí** ([epson.eu](https://www.epson.eu/en_EU/products/scanners/consumer/workforce-es-580w-a4-auto-duplex-scanner-with-wi-fi-and-easy-to-use-touchscreen/p/30514)) | Mínimo 50,8×50,8 mm; papel largo 6096 mm a 200 ppp | Wi-Fi. Escaneo a carpeta de red no confirmado | TWAIN oficial. WIA solo según una tienda (no confirmado) | 428 € ([PcComponentes](https://www.pccomponentes.com/epson-workforce-es-580w-adf-escaner-de-documentos)) / 467 € ([epson.es](https://epson.es/es_ES/productos/esc%C3%A1neres/consumer/workforce-es-580w/p/30514)) | Actual |
| Epson DS-C490 | 40 / 80 (resolución no confirmada) | **20** | Sí | Sí, según tiendas ([imaging-superstore](https://imaging-superstore.co.uk/products/epson-workforce-ds-c490-document-scanner)) | Mínimo 50,8 mm | Sin red | TWAIN, ISIS, WIA ([B&H](https://www.bhphotovideo.com/c/product/1780307-REG/epson_b11b271201_ds_c490_compact_desktop_document.html)) | 567,90 € ([epson.es](https://epson.es/es_ES/productos/esc%C3%A1neres/business/ds-c490/p/40564)) | Actual |
| Epson RR-600W | 35 / 70 ([ficha Epson](https://mediaserver.goepson.com/ImConvServlet/imconv/13642db9a052feadac83b21b37fe70b263a4d953/original?assetDescr=RapidReceipt_RR-600W_Scanner_Specification_Sheet_CPD-59359.pdf)) | 100 | Sí | Tiene detección de doble alimentación ([B&H](https://www.bhphotovideo.com/c/product/1604008-REG/epson_b11b258202_workforce_rr_600w_mobile_receipt.html)); no confirmado si es por ultrasonidos | 27–413 g/m²; papel largo 6096 mm | Wi-Fi | TWAIN no confirmado | Sin precio en euros (parece modelo de EE. UU.) | No confirmado que se venda en España |
| ScanSnap iX2500 | 45 / 90 a 200/300 ppp ([scansnapit es](https://www.scansnapit.com/es-es/products/scansnap-ix2500)) | 100 (50 con la guía de recibos) | Sí | Sí ([appinformatica](https://www.appinformatica.com/pa03860-b101-scansnap-ix2500/p)) | Mínimo 50,8×50,8 mm; papel largo 3000 mm | Wi-Fi | **No tiene TWAIN** ([pfu-us](https://www.pfu-us.ricoh.com/scanners/scansnap/ix2500)) | 483–533 € ([PcComponentes](https://www.pccomponentes.com/escaner-ricoh-scansnap-ix2500-wi-fi-duplex-pantalla-tactil-45-ppm-negro)) | Actual |
| ScanSnap iX1600 | 40 / 80 | 50 | Sí | Sí ([pfuemea](https://www.pfuemea.com/es-es/dr_product/scansnap-ix1600-white)) | Papel largo 3000 mm | Wi-Fi | **No tiene TWAIN** ([FAQ Ricoh](https://scansnap-faq.pfu.ricoh.com/hc/en-us/articles/27610858674713-Does-the-ScanSnap-Series-support-TWAIN-or-ISIS)) | 435–465 € | **Descatalogado** ([scansnapit](https://www.scansnapit.com/en-eu/products/scansnap-ix1600)) |
| Canon DR-C240 | 45 ppm en blanco y negro, **30 ppm en color**, a 200/300 ppp ([Canon Asia](https://asia.canon/en/consumer/dr-c240-c230/specification?category=scanning&subCategory=document-scanners)) | 60 | Sí | Sí ([Canon EE. UU.](https://www.usa.canon.com/support/p/imageformula-dr-c240-office-document-scanner)) | Mínimo 50,8×54 mm ([Canon India](https://in.canon/en/business/dr-c240/main/specification)); papel largo 3000 mm | Sin red | ISIS, TWAIN, WIA ([Canon Asia](https://asia.canon/en/support/DR-C240/model)) | 395–491 € ([Amazon.es](https://www.amazon.es/Canon-imageFORMULA-DR-C240-600-dpi/dp/B00WQJLXSG)) | «No longer available» en Canon EE. UU. |
| Canon DR-C230 | 30 / 60 ([Canon Europa](https://www.canon-europe.com/business/products/scanners/document-scanners/imageformula-dr-c230/specifications/)) | 60 | Sí | Solo según una web de reseñas ([scannernote](https://scannernote.com/canon-dr-c230/)) | — | Sin red | TWAIN/ISIS. WIA no confirmado | No buscado | Fin de vida según SHI |
| Canon DR-M260 | 60 / 120 ([Canon ME](https://en.canon-me.com/business/products/scanners/document-scanners/imageformula-dr-m260/specifications/)) | 80 | Sí | Sí | Papel largo 5588 mm | Sin red | ISIS/TWAIN | 818–1019 € ([PcComponentes](https://www.pccomponentes.com/canon-imageformula-dr-m260-escaner-documental-a4)) | Descatalogado en Canon EE. UU. |
| Canon DR-S150 | 45 / 90. Una prueba real mantuvo los 45 ppm a 200 ppp ([ITPro](https://www.itpro.com/hardware/peripherals/356466/canon-imageformula-dr-s150-review-just-walk-up-and-scan)) | 60 | Sí | Sí ([Canon EE. UU.](https://www.usa.canon.com/support/p/imageformula-dr-s150-office-document-scanner)) | — | Envía a la red sin PC (Network PUSH) | ISIS/TWAIN | No encontrado | Actual |

## 3. NAPS2 (versión 8.4.1 según el CHANGELOG del repositorio)

- **Línea de comandos y doble cara:** sí se puede. La ayuda dice «--source: The paper source (glass/feeder/duplex)» y «--driver: wia/twain/escl/sane/apple». También tiene `--listdevices`, `--deskew` y `--splitpatcht`, que separa archivos por hojas separadoras Patch-T. Fuente: https://raw.githubusercontent.com/cyanfish/naps2/master/NAPS2.Lib/Automation/AutomatedScanningOptions.cs
- **Doble alimentación:** NAPS2 no tiene ninguna opción para ella.
  - Buscar «DoubleFeed» en el código de cyanfish/naps2 da 0 resultados.
  - `ScanOptions` no tiene ninguna opción para ello (https://raw.githubusercontent.com/cyanfish/naps2/master/NAPS2.Sdk/Scan/ScanOptions.cs).
  - Las opciones genéricas («KeyValueOptions») solo funcionan con SANE, no en Windows (https://raw.githubusercontent.com/cyanfish/naps2/master/CHANGELOG.md, versión 8.4.0).
  - Desde la línea de comandos no se muestra la ventana del driver TWAIN (CHANGELOG, versión 7.0b1).
  - Por tanto, que se detecte la doble alimentación depende de cómo venga configurado el driver de cada escáner. No está confirmado para ningún modelo: hay que probarlo.
- **Problemas conocidos:**
  - ADS-4300N: error «Twain error: NoDS» con Windows 11 conectado por Ethernet ([SourceForge](https://sourceforge.net/p/naps2/discussion/general/thread/f3df4852b1/)).
  - Epson WorkForce 4595: la doble cara falla por WIA ([ticket 520](https://sourceforge.net/p/naps2/tickets/520/)).
  - Un Canon por TWAIN daba dos imágenes por hoja ([issue 599](https://github.com/cyanfish/naps2/issues/599)).
  - ScanSnap: no se puede usar con NAPS2 salvo con SnapTwain, un driver de pago de otra empresa ([jse.de](https://www.jse.de/products.html)), sin pruebas publicadas con NAPS2.

## 4. Lo que afecta en el código (facturas-a-aplifisa)

- `facturas_excel/escaner.py:422` llama a NAPS2 siempre con `--driver wia`. Con un Epson o un Canon que no tengan WIA fiable habría que cambiarlo a `twain`. El Brother tiene WIA y TWAIN.
- `facturas_excel/escaner.py:423` usa `--source duplex|feeder`, así que la doble cara ya está prevista; la casilla está en `facturas_excel/dialogo_escaneo.py:109`.
- `facturas_excel/escaner.py:425` usa `--pagesize a4 --deskew`. Con tiques mezclados, la página fija en A4 y el enderezado por software (que gasta tiempo de PC) son cosas a medir; no está confirmado cómo se comporta cada driver.
- `facturas_excel/escaner.py:62` tiene 200 ppp por defecto. Está por debajo de la resolución a la que se miden las velocidades nominales, así que no penaliza.
- `facturas_excel/escaner.py:70-75`: WIA solo devuelve la primera hoja con la HP; por eso el alimentador va por NAPS2.
- Los escáneres de alimentador no tienen cristal. La ruta del cristal (WIA) dejaría de usarse y los tiques irían por el alimentador.

## 5. Recomendación y cuánto más rápido sería

1. **Brother ADS-4300N (unos 349 €).** Es la mejor relación entre velocidad, precio y compatibilidad: 40/80, bandeja de 80 hojas, ultrasonidos, tiques de 50,8 mm en adelante, TWAIN y WIA, y escaneo a carpeta de red. Conviene conectarlo por **USB** para evitar el error «NoDS» y probar primero sin tocar el código (`--driver wia`). Si se quiere Wi-Fi y pantalla, el ADS-4700W (unos 526 €) es la misma máquina.
2. **Epson ES-580W (unos 428 €).** Bandeja de 100 hojas, ultrasonidos, papel largo de 6 m y Wi-Fi. Probablemente obligaría a cambiar la línea 422 a TWAIN.

Descartados: los ScanSnap (sin TWAIN ni WIA), el ADS-1800W y el DS-C490 (bandeja de 20 hojas; el ADS-1800W además sin detección de doble alimentación), los DR-C230/C240 (antiguos y a 30 ppm en color) y el DR-M260 (por precio).

Ganancia estimada a partir de las velocidades oficiales, **no medida**:

| Caso | M148 | ADS-4300N | Ganancia |
|---|---|---|---|
| A4 a una cara | ≤15 hojas/min | 40 hojas/min | ≈2,7 veces (ES-580W ≈2,3 veces) |
| A4 a doble cara | ≤7,5 hojas/min teóricas (dos pasadas, sin contar el volteo a mano) | 40 hojas/min | ≈5 veces o más |
| Tiques | Cristal, uno a uno | Mismo taco, por el alimentador | La mayor ganancia, pero no cuantificable sin medir |
| Recargas | Cada 35 hojas | Cada 80 hojas | — |

En la práctica, NAPS2 por WIA o TWAIN, el enderezado por software y el PC pueden bajar estas cifras. Conviene cronometrar un taco real con la M148 y con el escáner elegido antes de comprar más de uno.

## Verificación

## Verificación del informe «HP M148 frente a escáneres de documentos»

**Límites de esta verificación:** WebFetch no resolvía ningún dominio y el proxy cortaba con 403 casi todas las webs (HP, Brother, Epson, Canon, PcComponentes, Amazon, jse.de, las páginas de issues de GitHub). Solo pude abrir sourceforge.net y hacer `git clone` de cyanfish/naps2 (commit 9314194, del 3 de octubre de 2026). Los datos externos vienen de resúmenes de WebSearch, y el cupo de búsquedas del turno (200, compartido con otros agentes) se agotó antes de poder comprobar los precios. No modifiqué el repositorio.

### 1. HP M148dw / M148fdw
- **Alimentador de 35 hojas: confirmada.** https://h10032.www1.hp.com/ctg/Manual/c06985097.pdf y https://www8.hp.com/h20195/V2/GetPDF.aspx/c07874033
- **Hasta 15 ppm escaneando en normal, A4: confirmada** (c07874033). La copia de printerbase da 16 ppm. No he encontrado a qué velocidad escanea en color o en grises.
- **Sin doble cara por el alimentador: confirmada.** c07874033 y https://www.officedepot.com/a/products/6988931/HP-LaserJet-Pro-M148dw-All-in/. El hilo de h30434 concreto no lo pude abrir; los hilos genéricos de HP describen la doble cara a mano en dos pasadas.
- **Alimentador a 300 ppp: confirmada** (c07874033).
- **Tamaño mínimo en el alimentador 148,5×210 mm (A5): confirmada** según un fragmento de una hoja de datos de HP, así que es verdad que los tiques no caben.
- **Tamaño máximo 215,9×355,6 mm: hay discrepancia.** Otro resumen de c07874033 da 215,9×297 mm. No cambia nada del informe.
- **Gramaje 70–90 g/m² en el alimentador: no verificable.** Solo encontré 60–163 g/m², sin indicar si es del alimentador o de la bandeja (https://eu.shi.com/product/36038906/HP-LaserJet-Pro-MFP-M148fdw). La frase del resumen «ni más fino de 70 g/m²» no tiene respaldo.
- **Descatalogada: confirmada.** https://www.hp.com/us-en/shop/pdp/hp-laserjet-pro-mfp-m148dw; LDLC y Coolblue también la dan como fuera de venta.

### 2. Alternativas

**Brother ADS-4300N**
- **40/80, bandeja de 80 hojas: confirmada.** https://brother-usa.com/-/media/brother/product-catalog-media/documents/ads-4300n-2-page-brochure.pdf y https://support.brother.com/g/s/id/htmldoc/ads/cv_ads4300n/uke/html/GUID-98CBC8A6-17EA-4203-BC29-12271BCB0811_1.html
- **Mínimo 50,8×50,8 mm: confirmada** (misma página de soporte de Brother).
- **Detección de doble alimentación por ultrasonidos:** solo la confirma una ficha de tienda. No pude abrir la tienda oficial del Reino Unido.
- **Papel largo de 5000 mm: no verificable.** La ficha oficial solo llega a 355,6 mm de largo.
- **Drivers: corregida.** El folleto de Brother lista TWAIN, WIA, **ISIS** y SANE. El informe omite ISIS.
- **Grosor y gramaje: corregida, y es lo más importante del informe.** https://support.brother.com/g/s/id/htmldoc/ads/cv_ads4300n/uke/html/GUID-05D53893-EC8C-46BC-8FD0-FDF53603587F_1.html dice:
  - el grosor admitido es de 0,08 a 0,28 mm y el gramaje de 40 a 200 g/m²;
  - el papel más fino tiene que ir con hoja portadora;
  - no se deben cargar a la vez documentos de distinto grosor o calidad.
  
  El papel térmico de los tiques se vende en 48–55 g/m² (tritonstore.com.au, neotech.ae). Por mi cuenta calculo que eso son unos 0,05–0,06 mm; es una estimación, no un dato publicado. Por tanto, la afirmación «los tiques pasan a ir en el mismo taco» **no es cierta** para este modelo: irían aparte o en hoja portadora.
- **Ethernet + USB 3.0, sin Wi-Fi: confirmada** (folleto). **Escaneo a SMB/FTP/SFTP:** no lo he verificado.
- **349 € y fin de vida según SHI: no verificables.** Sigue anunciado en ldlc.com/es-es y mediamarkt.pl.

**Brother ADS-4700W**
- **80 hojas: confirmada** (misma ficha de soporte).
- **Drivers y 526 €: no verificables.**

**Brother ADS-1800W**
- **20 hojas, mínimo 51×70 mm y papel largo de 5000 mm: confirmada en fuente oficial** (https://store.brother.is/devices/scanners/ads/ads1800w). El informe decía «sin confirmar en fuente oficial».
- **Sin ultrasonidos:** coherente con la ficha, que solo menciona un selector de separación y una ranura para tarjetas.
- **30/60 y precio:** no los he vuelto a comprobar.

**Epson ES-580W**
- **35/70 a 300 ppp, 100 hojas y ultrasonidos (sensor de ultrasonidos más control de longitud): confirmada.** https://www.epson.com.sg/p/B11B258502
- **Mínimo 50,8×50,8 mm, 6096 mm a 200 ppp y 27–413 g/m²: confirmada**, pero solo en fichas de tienda (Adorama, Galaxus).
- **«WIA solo según una tienda»: corregida.** La ficha oficial de Epson dice TWAIN, SANE, WIA e ICA (epson.com.sg).
- **«Escaneo a carpeta de red no confirmado»: corregida.** Las tiendas indican Network (SMB) (https://shop.inception.co.uk/epson-workforce-es-580w-b11b258401by.html) o «Folder/FTP».
- **Mezclar tamaños en el mismo taco:**
  - La FAQ de Epson lo permite hasta tamaño carta (https://epson.com/faq/SPT_B11B258201~faq-0000600-es580w_rr600w).
  - Las guías de Epson para modelos hermanos lo desaconsejan si se mezcla papel fino con grueso, A4 con tamaño tarjeta, o tiques largos (https://download4.epson.biz/sec_pubs/ds-c490/useg/en/GUID-BDE1BF55-5A51-4785-A978-AFA879A80D34.htm).
- **Precio: no verificable.**

**Epson DS-C490**
- **40/80, 20 hojas, solo USB: confirmada.**
- **Ultrasonidos: confirmada por Epson**, no solo por tiendas (https://www.epson.co.in/Scanners/Document-Scanners/Epson-DS-C490-Compact-Desktop-Document-Scanner-with-Auto-Document-Feeder/p/B11B271501).
- **Drivers y precio: no verificables.**

**Epson RR-600W**
- **35/70, 100 hojas, 27–413 g/m²: confirmada.** https://epson.com.au/products/scanner/RR-600W_Specs.asp
- **TWAIN, ultrasonidos y venta en España: no verificables.** Solo aparecen referencias de Australia y EE. UU.

**ScanSnap iX2500 e iX1600**
- **iX2500 a 45 ppm, 100 hojas y ultrasonidos: confirmada** (https://www.shidirect.com/product/50346326/Ricoh-ScanSnap-iX2500 y la FAQ de Ricoh).
- **Sin TWAIN ni ISIS: confirmada.** https://scansnap-faq.pfu.ricoh.com/hc/en-us/articles/27610858674713-Does-the-ScanSnap-Series-support-TWAIN-or-ISIS
- **Sin WIA:** solo lo dice una FAQ de terceros (https://www.officemanager.de/en/support/scansnap-faq.html).
- **iX1600 descatalogado: confirmada.** https://www.scansnapit.com/uk/scansnap-ix1600-offer
- **SnapTwain:** su existencia solo aparece en textos de tienda (oztoner.au). No consta que funcione con el iX2500.
- **50 hojas con la guía de recibos, papel largo de 3000 mm y 483–533 €: no verificables.** Druckerchannel da unos 600 € para el iX2500 (https://www.druckerchannel.de/artikel_druckansicht.php?ID=5253).

**Canon DR-C240 y DR-C230**
- **DR-C240 a 45/90 en blanco y negro y 30/60 en color, 60 hojas: confirmada.** https://asia.canon/en/consumer/dr-c240-c230/specification
- **Ultrasonidos del DR-C240:** solo lo menciona el folleto de Canon Europa.
- **WIA del DR-C240 y mínimo de 50,8×54 mm: no verificables.**
- **DR-C230 a 30/60: confirmada.** Sus ultrasonidos siguen sin confirmar.

**Canon DR-M260**
- **60/120 y 5588 mm: confirmada.**
- **Bandeja: corregida. Son 90 hojas, no 80.** https://www.canon-europe.com/business/products/scanners/document-scanners/imageformula-dr-m260/specifications/
- **Descatalogado: no verificable.**

**Canon DR-S150**
- **45/90 a 200 ppp, 60 hojas, red cableada, Wi-Fi o USB y Network PUSH: confirmada.** https://sg.canon/en/business/dr-s150/specification
- **Ultrasonidos y drivers: no verificables.**

**Lo que falta en la tabla: corregida.**
- **Canon DR-C340:** es actual. 40/80, bandeja de 100 hojas, ultrasonidos, drivers ISIS, TWAIN y **WIA**, USB-C. https://www.canon-europe.com/business/products/scanners/document-scanners/imageformula-dr-c340/specifications/ y https://www.canon.de/business/products/scanners/document-scanners/imageformula-dr-c340/specifications/
- **Canon DR-C350:** 50/100 y 100 hojas.
- No encontré precio en euros; un distribuidor de EE. UU. lo da a 440 $.

### 3. NAPS2
- **Versión 8.4.1 en el CHANGELOG: confirmada** (CHANGELOG.md:1).
- **Opciones de línea de comandos: confirmadas.** En NAPS2.Lib/Automation/AutomatedScanningOptions.cs: `--driver` en 69–70, `--listdevices` en 75, `--source` en 82–83, `--deskew` en 99 y `--splitpatcht` en 134.
- **Ninguna opción de doble alimentación: confirmada.** Buscando en el código clonado (no con el buscador de GitHub), sin distinguir mayúsculas, «double feed», «multifeed» y «ultrason» en .cs y .md dan 0 resultados. Tampoco hay nada en ScanOptions.cs, WiaOptions.cs ni TwainOptions.cs.
- **KeyValueOptions solo con SANE: la conclusión es cierta, pero la fuente está mal.** La prueba es el código: solo se usan en NAPS2.Sdk/Scan/Internal/Sane/SaneScanDriver.cs:435. La línea del CHANGELOG 8.4.0 (CHANGELOG.md:23) no dice que solo valgan para SANE.
- **Sin ventana del driver TWAIN desde la línea de comandos: confirmada** (CHANGELOG.md:365, versión 7.0b1). Además, TwainScanRunner.cs:92 abre el driver sin ventana salvo que se pida la nativa.
- **Error «NoDS»: confirmado, pero con matices** (https://sourceforge.net/p/naps2/discussion/general/thread/f3df4852b1/, 7 de marzo de 2025, Windows 11, sin solución publicada).
  - Fue con el driver **TWAIN** por red («TW-Brother ADS-4300N LAN»). La app usa WIA (escaner.py:422), así que el error no le afecta directamente.
  - El consejo de conectarlo por USB para evitar el error no está probado.
- **Ticket 520: confirmado, pero no sirve como prueba** (https://sourceforge.net/p/naps2/tickets/520/). Es de 2018, con NAPS2 6.0.3, Windows Server 2012 R2 y una multifunción WorkForce 4595, no un escáner de documentos.
- **Issue 599 de GitHub: no verificable** (GitHub bloqueado y no aparece en las búsquedas).

### 4. Código de facturas-a-aplifisa
- **escaner.py:422 usa `--driver wia`: confirmada.** Cambiar a TWAIN no se arregla solo en esa línea: el nombre de escáner que se pasa a NAPS2 sale de la lista de WIA (escaner.py:158–177 → ventana_archivo.py:44 → hilos.py:145 → escaner.py:427–428). `--device` acepta nombres aproximados (AutomatedScanningOptions.cs:72), así que puede funcionar, pero hay que probarlo.
- **escaner.py:423 y la casilla de doble cara en dialogo_escaneo.py:109: confirmada.**
- **escaner.py:425 con `--pagesize a4 --deskew`: confirmada** (también lleva `--force --verbose`).
- **escaner.py:62, 200 ppp por defecto: confirmada, con un matiz.** Se usa el último valor elegido (dialogo_escaneo.py:89–90 y 158) y se ofrecen 300 ppp (dialogo_escaneo.py:39).
- **escaner.py:70–75: confirmada.**
- **Ruta del cristal:** la app sigue dejando elegirla (dialogo_escaneo.py:106–108). Con un escáner que solo tiene alimentador pediría el cristal a WIA (escaner.py:268 y 469–478) y lo más probable es que falle; no lo he probado.
- **Falta en el informe:** la única protección de la app contra la doble alimentación es comparar hojas puestas con páginas escaneadas (dialogo_escaneo.py:96–104 y ventana_archivo.py:177–195). A doble cara compara páginas con hojas (ventana_archivo.py:189), así que casi nunca avisará.

### 5. Ganancia estimada
- **A una cara:** 40/15 ≈ 2,7, y con el ES-580W 35/15 ≈ 2,3. El resumen dice «unas 2,5 veces» y la tabla dice 2,7: son incoherentes entre sí.
- **A doble cara:** 40/7,5 ≈ 5,3, así que «≈5 veces» es correcto.
- La cifra de 15 ppm de la M148 no dice en qué modo de color se mide.

## Correcciones a aplicar al informe
1. **Resumen y apartado 5:** quitar «los tiques pasan a ir en el mismo taco». Con el ADS-4300N, el papel de menos de 0,08 mm va en hoja portadora y Brother desaconseja mezclar grosores (página «Acceptable Documents» de Brother). Con Epson se pueden mezclar tamaños hasta carta, pero Epson desaconseja mezclar papel fino con grueso y tiques largos. Los tiques irían en tacos aparte por el alimentador, que sigue siendo más rápido que el cristal.
2. **Resumen:** cambiar «2,5 veces» por «≈2,7 veces» (o «2,3–2,7»).
3. **Resumen y ficha de la HP:** marcar como no confirmado «ni más fino de 70 g/m²» y el rango de 70–90 g/m²; solo hay 60–163 g/m², sin decir si es del alimentador.
4. **ES-580W:** cambiar «WIA solo según una tienda» por «TWAIN, WIA, SANE e ICA según Epson». Quitar «probablemente obligaría a cambiar la línea 422 a TWAIN». Cambiar «escaneo a carpeta de red no confirmado» por «SMB/FTP según tiendas; comprobar en el firmware».
5. **ES-580W:** reconsiderar el orden de la recomendación para los tiques. Admite 27 g/m² según las fichas de tienda, frente a los 40 g/m² y 0,08 mm del ADS-4300N.
6. **ADS-4300N:** añadir ISIS a los drivers. Marcar los 5000 mm de papel largo como no confirmados.
7. **ADS-1800W:** el mínimo de 51×70 mm y los 5000 mm sí están en fuente oficial (store.brother.is).
8. **DS-C490:** los ultrasonidos los confirma Epson (epson.co.in), no solo las tiendas.
9. **DR-M260:** la bandeja es de 90 hojas, no 80.
10. **Añadir el Canon DR-C340** (40/80, 100 hojas, ultrasonidos, ISIS, TWAIN y WIA, USB) y **el DR-C350** (50/100) como sucesores actuales del DR-C230/C240. Precio en España sin confirmar.
11. **Error «NoDS»:** aclarar que fue con TWAIN por red y que la app usa WIA. El consejo de conectarlo por USB es una hipótesis.
12. **Ticket 520:** aclarar que es de 2018, con NAPS2 6.0.3 y una multifunción, y que no aplica a los modelos propuestos.
13. **KeyValueOptions:** citar como fuente SaneScanDriver.cs:435 y no el CHANGELOG 8.4.0.
14. **Apartado 4, añadir:**
    - pasar a TWAIN obliga a revisar también el nombre de escáner que sale de WIA (escaner.py:158–177 y 427–428);
    - hay que ocultar o forzar la casilla «Usar el alimentador» con escáneres sin cristal (dialogo_escaneo.py:106–108);
    - el aviso de «faltan hojas» no sirve a doble cara (ventana_archivo.py:189).
15. **Marcar como no verificados:** todos los precios, el fin de vida del ADS-4300N según SHI, la detección de ultrasonidos de los DR-C230 y DR-S150, el WIA del DR-C240, el issue 599, el funcionamiento de SnapTwain con el iX2500 y la ausencia de WIA en los ScanSnap (solo la afirma una fuente de terceros).

Fuentes de NAPS2 consultadas en local: /tmp/claude-0/-home-user-Notas-Asesoria-app/80eee95a-129e-573c-8981-869185147349/scratchpad/naps2-src (clon) y /tmp/claude-0/-home-user-Notas-Asesoria-app/80eee95a-129e-573c-8981-869185147349/scratchpad/sf_thread.html y sf_520.html (páginas de SourceForge).

# Escáneres de unos 200 € (brother-canon)

**Escáner para la asesoría (Brother/Canon, España, consulta del 9-oct-2026)**

**Antes de nada: de dónde salen los datos.** No he podido abrir ninguna web directamente: la red de este entorno bloquea Amazon.es, PcComponentes, Canon, Brother y naps2.com. Todo sale de los extractos que da el buscador de esas páginas. Los precios de Amazon.es son de lo que el buscador tiene guardado de amazon.es y no traen fecha de captura. Los de comprasmartphone.com sí la traen (21-jul-2026). Hay que comprobar el precio el día de la compra.

### Conclusión
1. **Por unos 200–230 € no hay ningún Brother o Canon nuevo en España que tenga detección ultrasónica de doble arrastre y además funcione con NAPS2.** Los más baratos con ultrasonidos y TWAIN/WIA cuestan unos 280–305 €:
   - Canon DR-C225W II
   - Canon DR-C225 II
   - Canon DR-C230
2. **Dentro del presupuesto: Brother ADS-1300**, unos 212 € en Amazon.es. Funciona con NAPS2 (TWAIN y WIA), pero tiene cuatro pegas para tacos de tiques:
   - no tiene detección ultrasónica;
   - el alimentador solo admite 20 hojas;
   - Brother recomienda hoja portadora para los tiques;
   - la almohadilla de separación dura unos 10.000 escaneos.
3. **Algo mejor por poco más: Canon DR-C230**, unos 295–305 €. Es el que mejor cumple:
   - alimentador de 60 hojas, 30 ppm / 60 ipm;
   - detección ultrasónica, con botón para seguir escaneando tras un doble arrastre;
   - admite papel muy fino (desde 27 g/m², útil para tiques);
   - controladores ISIS, TWAIN y WIA;
   - rodillos para unos 200.000 escaneos.

   Si no se llega a 300 €, la opción intermedia es el **DR-C225 II / DR-C225W II** (unos 278–299 €): también ultrasónico y compatible, pero más lento (25 ppm) y con alimentador más pequeño.

### Modelos que encajan (o casi)

**1) Brother ADS-1300 — encaja casi (cabe en el presupuesto, sin ultrasonidos)**
- **A la venta en 2026:** sí, con la referencia ADS1300UN1. Ficha en Amazon.es: https://www.amazon.es/Brother-ADS1300-documental-sobremesa-Compacto/dp/B0CYTFGW98
- **Precio:**
  - Amazon.es: 212,00 € y "43 ofertas desde 247,11 €" (extracto del buscador, sin fecha).
  - PcComponentes: 270,73 € (precio recomendado 279 €; captura con entrega el 27 de julio) — https://www.pccomponentes.com/marcas/brother/escaners
  - PCBox: 271,61 € — https://www.pcbox.com/ads1300un1-brother-escaner-documentos-ads1300/p
  - LDLC.es: 287,95 € — https://www.ldlc.com/es-es/ficha/PB00609814.html
  - Referencia europea: 185,50 € en 123inkt.be (Bélgica) — https://www.123inkt.be/Brother-ADS-1300-A4-documentscanner-ADS1300UN1-i102108-t7580153.html
- **Velocidad:** 30 ppm / 60 ipm a 300 ppp; 7 ppm a 600 ppp.
  - https://papyrus-gmbh.de/en/pdf/Brother_ADS-1300_Datenblatt.pdf
  - https://brother-usa.com/-/media/brother/product-catalog-media/documents/ads-1300-2-page-brochure.pdf
- **Alimentador:** 20 hojas, 51,8–128 g/m². Resolución óptica 600 × 600. Uso diario recomendado: 1.000 escaneos.
  - https://www.brother.eu/-/media/product-downloads/devices/scanners/ads/ads1300/ads-1300.pdf
  - https://support.brother.com/g/s/id/htmldoc/ads/cv_ads1800w/uke/html/GUID-2FFC02DD-6069-4E30-A738-DD727B78A689_1.html
- **Doble arrastre:** no tiene detección ultrasónica. La ficha de Brother solo indica "Separation Switch, Resume Scan" — https://www.brother.eu/-/media/product-downloads/devices/scanners/ads/ads1300/ads-1300.pdf
- **Controladores:** TWAIN y WIA para Windows 10/11, además de ICA y SANE.
  - https://brother.ca/en/p/ADS1300
  - Tabla de especificaciones de Brother (enlace de arriba).
- **NAPS2:** no he encontrado informes concretos con este modelo. Sí hay un caso con un ADS-4300N que daba error TWAIN "NoDS" en Windows 11 dentro de NAPS2 (https://sourceforge.net/p/naps2/discussion/general/thread/f3df4852b1/). Si pasa, se puede usar WIA.
- **Conexión:** USB-C 3.2 Gen 1, alimentado por el propio USB. No tiene Wi-Fi.
- **Automatismos:**
  - "Auto Start Scan": escanea al meter el papel, pero solo con un perfil guardado y a través del programa de Brother, no de NAPS2.
  - Salto de páginas en blanco y enderezado.
  - Ranura para tarjetas.
  - Fuentes: el folleto de Brother (enlace de arriba) y https://www.brother.eu/-/media/product-downloads/devices/nordics/eu_en/cheat-sheets/scanner/cds3-scanner-cheatsheet_eng_web.pdf
- **Tiques y papel largo:**
  - Papel largo hasta 5.000 mm, pero solo a una cara y por debajo de 300 ppp (misma guía de Brother).
  - Para tiques Brother recomienda hoja portadora: "Receipts… (carrier sheet recommended)" — https://brother.ca/en/p/ADS1300
- **Rodillos:**
  - Rodillo de arrastre PUR-2001C: unos 100.000 escaneos (https://www.brother.ca/p/PUR2001C); 25,87 € con IVA en https://industry-electronics.com/brother/pur2001c-pur-2001c-pickup-roller-lieske_1481589.htm
  - Almohadilla SP-2001C: unos 10.000 escaneos (https://www.brother.ca/p/SP2001C); 24,99 $ en Brother USA (https://www.brother-usa.com/products/SP2001C). No he encontrado precio en euros.
- **Opiniones:**
  - 4,1/5 con 1.703 reseñas en Amazon EE. UU. (https://sentinel.rocketium.com/products/amazon/B0D1T3SN8B).
  - 4,2/5 con 70 opiniones en PcComponentes.
  - No he encontrado pruebas independientes sobre dobles arrastres.

**2) Canon imageFORMULA DR-C230 — el más recomendable si se puede subir a unos 300 €**
- **A la venta en 2026:** sí.
- **Precio:**
  - MediaMarkt.es: 294,90 € (antes 324,38 €, sin fecha) — https://www.mediamarkt.es/es/product/_escaner-cdp2dviucpw-canon-600-x-600-dpi-negro-100657733.html
  - Amazon.es: 305,00 € (extracto del buscador) — https://www.amazon.es/Canon-imageFORMULA-DR-C230-Scanner-600DPI/dp/B073YKFSK1
  - PcComponentes: 343,06 € — https://www.pccomponentes.fr/canon-imageformula-dr-c230-escaner-documental-a4
- **Velocidad:** 30 ppm / 60 ipm. En lo encontrado, Canon no detalla la velocidad a 300 ppp.
  - https://www.canon.co.uk/business/products/scanners/document-scanners/imageformula-dr-c230/specifications/
  - https://ph.canon/en/business/dr-c240-c230/specification
- **Alimentador:** 60 hojas, papel de 27 a 209 g/m². Óptica 600 ppp. Uso diario 2.000–4.500 escaneos (página de Canon UK de arriba).
- **Doble arrastre:** sí, ultrasónico y por longitud, con botón DFR para continuar tras el aviso.
  - https://files.canon-europe.com/files/soft03-48729/Manual/DR-C240_C230_User_Guide_EN.pdf
  - https://canon.a.bigcontent.io/v1/static/dr-c230_datasheet_em_final_forweb_ec7e95be980944b1a1acafaa6aa1743e
- **Controladores:** ISIS/TWAIN/WIA para Windows (actualizado el 25-dic-2024) — https://asia.canon/en/support/DR-C230/model
- **NAPS2:** no he encontrado informes concretos. Con otro Canon (DR-G2090) hubo que usar el modo TWAIN "Legacy (native UI)" — https://sourceforge.net/p/naps2/tickets/955/
- **Conexión:** USB 2.0. Sin Wi-Fi ni red.
- **Automatismos:** "Auto Start" (escanea al detectar papel) y botón Start con trabajos de CaptureOnTouch (manual de arriba).
- **Papel largo y tarjetas:** modo de documento largo hasta 3.000 mm; tarjetas de plástico y en relieve (página de Canon UK).
- **Rodillos:** kit 0697C003 / 5607B001.
  - Cambio cada unos 200.000 escaneos o 12 meses: https://scannerone.com/product/roller-kit-canon-c240/
  - 66 £ con IVA en https://www.thescannershop.com/roller-kit-for-canon-dr-c230-dr-c240-scanners/
- **Opiniones:** pocas. Un comprador en Adorama dice "reliable, no misfeeds" (https://www.adorama.com/canon-imageformula-dr-c230-compact-document-scanner/p/icadrc230). Un hilo en JustAnswer habla de dobles arrastres con papel grueso o sobres (https://www.justanswer.com/office-equipment/ggln5-dr-c230-continues-double-feed-when-scanning.html).

**3) Canon imageFORMULA DR-C225 II (y DR-C225W II con Wi-Fi) — la opción intermedia**
- **A la venta en 2026:** sí (Canon publicó controlador para Windows 11 el 14-oct-2025).
- **Precio:**
  - Amazon.es: 298,68 € ("29 nuevos desde") y 291,45 € — https://www.amazon.es/Canon-imageFORMULA-Documentos-Alimentador-Instalaci%C3%B3n/dp/B07FQKKQLP
  - comprasmartphone (21-jul-2026): Amazon 291 €, Tradeinn 336 €, PcComponentes 346 € — https://comprasmartphone.com/escaneres-de-documentos/canon-imageformula-dr-c225-ii
  - DR-C225W II (Wi-Fi) en Amazon.es: 277,71 € — https://www.amazon.es/Canon-DR-C225W-II-ultracompacto-Dispositivos/dp/B07FQ99927
- **Velocidad:** 25 ppm / 50 ipm, en color y en blanco y negro.
  - Canon Asia indica que la cifra es a 200 ppp: https://in.canon/en/business/dr-c225-ii-225w-ii/specification
  - LDLC dice que se mantiene a 300 ppp, pero es dato de la tienda: https://ldlc.com/en/product/PB00263516.html
- **Alimentador:** 45 hojas según Canon Europa, 30 según Canon Canadá y B&H. Uso diario 1.000–2.500 escaneos.
  - https://www.canon-europe.com/business/products/scanners/document-scanners/imageformula-dr-c225-ii/specifications/
- **Doble arrastre:** sí, sensor ultrasónico y por longitud (misma página de Canon Europa).
- **Controladores:** ISIS/TWAIN/WIA para Windows 11 — https://canon.com.au/document-scanners/imageformula-dr-c225-ii/support
- **NAPS2:** Neat lo cita como alternativa gratuita para este escáner — https://support.neat.com/3-rdpartyscanners/canon-dr-c-225
- **Conexión:** USB; Wi-Fi solo en el modelo W.
- **Automatismos:**
  - "Auto Start" (comprobado en el manual del DR-C225 original): https://files.canon-europe.com/files/soft45419/Manual/DR-C225_225W%20UM_US.pdf
  - Modo totalmente automático, salto de blancos y enderezado: https://www.adorama.com/col/productManuals/ICADRC225II.pdf
  - En el controlador hay una opción de alimentación "Panel-Feeding / Automatic Feeding" que deja la sesión abierta esperando el siguiente taco: https://www.manualslib.com/manual/2389084/Canon-Imageformula-Dr-C225-2.html?page=56
  - Que esa opción funcione dentro de NAPS2 está sin comprobar; hay que probarlo.
- **Tiques:** trayecto recto para papel de 40–209 g/m² y documentos largos de hasta 3.000 mm (página de Canon Europa).
- **Rodillos:** kit 5484B001 (rodillo de arrastre y de retardo), entre 43 y 95 $.
  - https://www.precisionroller.com/exchange-roller-kits-for-canon-dr-c225-ii-imageformula-scanner/details_76740.html
  - No he encontrado una duración oficial.
- **Opiniones:**
  - PCMag lo considera de gama de entrada, para poco volumen.
  - Un revisor en CDW (modelo W II) tuvo fallos de arrastre con el tiempo.
  - Opiniones positivas en Adorama.
  - Resumen en https://www.priceme.com.au/Canon-Imageformula-DR-C225II/p-903922465.aspx

### Descartados
**Brother**
- **ADS-1200 y ADS-1700W:** ya no se venden en LDLC.
  - https://ldlc.com/en/product/PB00261853.html
  - https://ldlc.com/en/product/PB00259832.html
  - PCMag cuenta el ADS-1800W como sustituto del 1700W: https://tech.yahoo.com/computing/articles/brother-ads-1800w-225120623.html
- **ADS-1350W:** no parece venderse en la UE. Energy Star lo lista para EE. UU., Japón y Canadá, y la declaración de conformidad británica solo cubre ADS-1300 y ADS-1800W.
  - https://www.energystar.gov/productfinder/product/certified-imaging-equipment/details/2668034/export/pdf
  - https://download.brother.com/welcome/doc101538/cv_ads1300_uk_doc_02.pdf
- **ADS-1800W:** sin ultrasonidos, 20 hojas, y caro para lo que añade (Wi-Fi y pantalla).
  - 326 € en Amazon y PcComponentes (21-jul-2026): https://comprasmartphone.com/escaneres-de-documentos/brother-ads-1800w
  - Unos 276 € en Amazon.es según el buscador (sin fecha).
- **ADS-2200 y ADS-2700W:** descatalogados.
  - https://store.brother.co.uk/devices/scanners/ads/ads2700w
  - https://www.thescannershop.com/brother-ads-2200-scanner (indica el ADS-4100 como sustituto)
- **ADS-3100:** no he encontrado ninguna tienda española que lo venda; los precios que salen son de América y Asia. Además, la guía rápida de Brother dice "Multifeed Detection Error (ADS-4300N only)", es decir, el 3100 no tiene detección de doble arrastre.
  - https://download.brother.com/welcome/doc101266/cv_ads4300n_ase_qsg_a.pdf
- **ADS-4100** (el equivalente europeo): 60 hojas y 35/70 ppm, pero 325–363 € y no consta que tenga ultrasonidos.
  - https://comprasmartphone.com/escaneres-de-documentos/brother-ads-4100re1
- **ADS-4300N:** sí tiene ultrasonidos, 80 hojas y red, pero cuesta 364 € (Amazon, vendedor externo) y 372–376 € en PcComponentes.
  - https://comprasmartphone.com/escaneres-de-documentos/brother-ads-4300n
  - https://www.brother.eu/-/media/product-downloads/devices/scanners/ads/ads4300n/ads-4300n-datasheet.pdf

**Canon**
- **R40:** descatalogado en las tiendas Canon de Europa (canon.ie lo marcaba como descatalogado a 589 €). Klarna España da 563 € bajo pedido.
  - https://www.canon.ie/store/canon-imageformula-r40-desktop-scanner/4229C004
  - https://www.klarna.com/es/shopping/pl/cl50/3202813828/Escaneres/Canon-imageFORMULA-R40/
- **R40II** (sucesor, febrero de 2026): Canon USA dice que no admite controladores TWAIN ni ISIS, así que NAPS2 no puede usarlo. Tampoco he encontrado ficha europea.
  - https://www.usa.canon.com/support/p/imageformula-r40ii-office-document-scanner
- **R30 y R10:** funcionan sin controlador, con el CaptureOnTouch Lite que llevan dentro. No he encontrado controlador TWAIN para ninguno; solo servirían con carpeta vigilada. El R10 además solo admite 20 hojas.
  - https://community.usa.canon.com/t5/Scanners/imageFORMULA-R30-quot-CaptureOnTouch-quot-and-drivers-missing/td-p/576640
  - R30 a 329,68 € en PCBox: https://www.pcbox.com/6051c003-imageformula-r30-dokumentenscanner/p
  - R10 entre 212,99 y 259,84 € en PcComponentes: https://www.pccomponentes.com/canon-imageformula-r10-escaner-portatil
- **R50:** cumpliría casi todo (ultrasonidos, TWAIN, Mopria/eSCL, Wi-Fi, 60 hojas, 40/80 ppm), pero no he encontrado precio en España; en EE. UU. y Canadá ronda los 540–590 $.
  - https://www.usa.canon.com/support/p/imageformula-r50-office-document-scanner
- **DR-F120:** descatalogado (canon.ie). 396 € en el marketplace de PcComponentes.
  - https://www.pccomponentes.com/canon-imageformula-dr-f120-escaner-documental-a4
- **DR-C240:** 618,30 € en Bechtle España — https://bechtle.com/es-en/shop/canon-imageformula-dr-c240-scanner--977667-12--p
- **P-215II:** portátil, 15 ppm y 20 hojas. 287,10 € en MediaMarkt.
  - https://www.mediamarkt.es/es/product/_escaner-portatil-p-215ii-canon-600-x-600-dpi-15-ppm-gris-145679700.html
- **DR-C360** (septiembre de 2026): gama profesional (100 hojas, 120 ipm), fuera de presupuesto.
  - https://www.canon-europe.com/press-centre/press-releases/2026/09/canon-launches-imageformula-dr-c360-to-bring-faster-and-more-versatile-desktop-scanning-to-modern-businesses/

### Sobre NAPS2 y la automatización
- **Inicio automático y botón:** en Brother y Canon estas funciones pasan por el programa del fabricante (iPrint&Scan o CaptureOnTouch), no por NAPS2. Para usarlas con su programa habría que guardar en una carpeta vigilada.
- **Por NAPS2.Console:** lo práctico es que el programa lance el escaneo y el controlador TWAIN o WIA haga el resto. El salto de páginas en blanco y el enderezado los hace el propio controlador.
- **Lo que hay que probar:** que el modo "Automatic Feeding" de Canon (esperar al siguiente taco) y la detección ultrasónica respeten la configuración cuando escanea NAPS2.
- **Ningún informe específico:** no he encontrado ningún informe de NAPS2 con estos modelos concretos. Todos tienen TWAIN y WIA oficiales.

## Verificación

**Verificación del informe de escáneres Brother/Canon (9-oct-2026): muchos datos sin poder comprobar y tres errores**

No he podido verificar una buena parte del informe:
- **Webs bloqueadas:** la red de este entorno rechaza amazon.es, idealo.es, mediamarkt.es, pccomponentes, canon-europe, brother.eu, naps2.com y sourceforge. Las peticiones devuelven 403 o ENOTFOUND.
- **Búsquedas agotadas:** el límite de búsquedas del turno, compartido con otros agentes, se acabó tras 5 búsquedas mías.
- **Lo que sí he podido leer:** esas 5 búsquedas y el código fuente de NAPS2 en GitHub (versión 8.4.1, commit 9314194 del 3-oct-2026).

Si queréis seguir buscando, basta con mandar otro mensaje.

### Brother ADS-1300

**Precios**
- **212 € en Amazon.es: no verificable.** La búsqueda no encuentra ninguna ficha de Amazon.es con precio. Como referencia hay 187,37 € en Amazon.fr, según un comparador francés, sin fecha (https://kulturegeek.fr/comparateur/produit/scanner-a-defilement-brother-ads-1300-40067).
- **Precios en tiendas españolas (corrección: no baja de 250 €):**
  - Bechtle España: 251,67 € con IVA, 21 unidades en stock, sin fecha (https://bechtle.com/es-en/finder/product-family/brother-document-scanner--4585--f).
  - MediaMarkt.es: 262,00 €, antes 366,90 € (−28 %). La fecha de entrega que muestra es de julio de 2026, así que el dato es viejo (https://www.mediamarkt.es/es/product/_escaner-portatil-brother-ads1300-600-x-600-ppp-30-ppm-wi-fi-ranura-para-dni-y-tarjetas-alimentacion-directa-via-usb-tipo-c-blanco-1581233.html).
- **Otros precios: confirmados.**
  - PcComponentes: 270,73 €, precio recomendado 279 €, 4,2/5 con 70 opiniones, fechas de julio (https://www.pccomponentes.com/marcas/brother/escaners).
  - PCBox: 271,61 € (https://www.pcbox.com/ads1300un1-brother-escaner-documentos-ads1300/p).
  - LDLC.es: 287,95 € (https://www.ldlc.com/es-es/ficha/PB00609814.html).

**Características**
- **30 ppm: confirmado** solo por el título de la ficha de MediaMarkt. Ese título dice también "Wi-Fi", lo cual es un error de la tienda: el informe dice USB y el Wi-Fi es del ADS-1800W. No lo he contrastado con Brother porque su web está bloqueada.
- **No verificable** (las fuentes del informe están bloqueadas): alimentador de 20 hojas, que no tenga ultrasonidos, controladores TWAIN/WIA, hoja portadora para tiques y duración de los rodillos. No he encontrado nada que lo contradiga.
- **Opiniones en Amazon EE. UU. (4,1/5 con 1.703 reseñas): no verificable.**

### Canon DR-C230

- **Precio en España: no verificable.** No he podido leer ni los 294,90 € de MediaMarkt ni los 305 € de Amazon.es.
- **Precio en el resto de Europa:**
  - Distribuidor europeo para empresas: 313,79 € con IVA (https://responsive5.e-nitiative.eu/product/details/canon/scanners-en-digitale-camera-s/2646c003/0874L076).
  - Reino Unido: 321,44 £ (https://tech-shop.unity.world/canon-imageformula-dr-c230-sheet-fed-scanner-600-x-600-dpi-a4-black.html).
  - El precio de 343,06 € que cita el informe es de **pccomponentes.fr**, no de la tienda española.
- **Características: no verificables aquí** (alimentador de 60 hojas, 30 ppm / 60 ipm, ultrasonidos, papel desde 27 g/m², ISIS/TWAIN/WIA). Coinciden con lo que se conoce del modelo, pero sin fuente leída.

### Canon DR-C225 II / DR-C225W II

- **Precio del DR-C225 II en Amazon.es: confirmado.** 298,68 €, "29 nuevos desde", sin fecha (https://www.amazon.es/Canon-DR-C225-II-ultracompacto-intuitivo/dp/B07FQKKQLP).
- **Precio en PcComponentes: corregido.** Ahora sale a 355,67 €, no 346 € (https://www.pccomponentes.com/canon-imageformula-dr-c225-ii-escaner-compacto-de-documentos).
- **Precio del DR-C225W II (277,71 €): no verificable.** Solo he confirmado que la ficha existe en Amazon.es (https://www.amazon.es/Canon-DR-C225W-II-ultracompacto-Dispositivos/dp/B07FQ99927).
- **Alimentador de "45 hojas según Canon Europa": corregido, son 30 hojas.**
  - 30 hojas de 80 g/m² (o una pila de 6 mm) según Canon India (https://in.canon/en/business/dr-c225-ii-225w-ii/specification) y Canon Indonesia (https://id.canon/id/business/dr-c225-ii-225w-ii/specification).
  - El título de la ficha de Amazon.es del W II dice lo mismo: "30 ADF Sheets".
- **Detección ultrasónica: confirmada solo por una fuente secundaria.** La cita comprasmartphone (https://comprasmartphone.com/escaneres-de-documentos/canon-imageformula-dr-c225-ii). La ficha de Canon no se pudo leer.
- **Uso diario: dato distinto.** Una ficha de distribuidor da 1.500 páginas al día como máximo (https://centrale.cl/wp-content/uploads/Ficha-tecnica-Canon-3258C002.pdf); el informe decía 1.000–2.500.

### NAPS2: comprobado en su código fuente (versión 8.4.1)

- **Controladores: confirmado.** Funciona con WIA, TWAIN y eSCL en Windows (https://github.com/cyanfish/naps2/blob/master/README.md).
- **"El botón solo funciona con el programa del fabricante": corregido.** NAPS2 puede registrarse en Windows como "Scan with NAPS2" para el botón físico del escáner (https://github.com/cyanfish/naps2/blob/master/NAPS2.Lib/Platform/Windows/StillImage.cs).
  - Solo funciona si el controlador WIA del escáner envía el aviso de que se ha pulsado el botón.
  - Si el ADS-1300 o los Canon lo envían está sin comprobar; hay que probarlo.
- **NAPS2 no espera a que se cargue papel.** Los únicos ajustes de alimentación que manda al TWAIN son:
  - activar el alimentador y la doble cara;
  - y, en modo "Auto", elegir el alimentador si tiene papel.

  No envía la orden de escaneo automático ni la de detección de doble arrastre (https://github.com/cyanfish/naps2/blob/master/NAPS2.Sdk/Scan/Internal/Twain/TwainScanRunner.cs). Por tanto los ultrasonidos y el "Automatic Feeding" de Canon dependen de cómo esté configurado el propio controlador. Para activarlos desde NAPS2 hay que usar la opción "Use native UI", que abre la ventana del controlador.
- **"El salto de blancos y el enderezado los hace el controlador": incompleto.** NAPS2 también los hace por su cuenta (https://github.com/cyanfish/naps2/blob/master/NAPS2.Sdk/Scan/ScanOptions.cs).
- **El modo TWAIN "Legacy (native UI)" que cita el informe ya no existe.** NAPS2 8.0 eliminó esa opción (https://github.com/cyanfish/naps2/blob/master/CHANGELOG.md); ahora solo existe "Use native UI".

### ScanSnap: no verificable

No he podido buscarlo. Por lo que sé, sin fuente leída: los ScanSnap iX1300, iX1400 e iX1600 no tienen controlador TWAIN ni WIA, solo ScanSnap Home, así que NAPS2 no los vería. Solo servirían guardando en una carpeta vigilada. Hay que confirmarlo antes de considerarlos.

### Clasificación final

**Dentro de unos 200 €:** ningún Brother o Canon con TWAIN/WIA tiene un precio verificado que quepa. Los tres más cercanos:
1. **Brother ADS-1300.** 212 € en Amazon.es sin verificar; el más bajo verificado en España es 251,67 € (Bechtle). Pegas:
   - no tiene ultrasonidos (no verificado aquí);
   - alimentador de 20 hojas;
   - hoja portadora para tiques;
   - almohadilla de unos 10.000 escaneos;
   - el escaneo al cargar papel va con el programa de Brother, no con NAPS2.
2. **Canon DR-C225W II.** 277,71 € en Amazon.es sin verificar. Pegas:
   - 25 ppm;
   - alimentador de 30 hojas, no 45;
   - el Wi-Fi no aporta nada a NAPS2.
3. **Canon DR-C225 II.** 298,68 € en Amazon.es (dato del buscador, sin fecha); 355,67 € en PcComponentes. Pegas:
   - 25 ppm y 30 hojas;
   - ultrasonidos confirmados solo por una fuente secundaria;
   - pensado para poco volumen (unas 1.500 páginas al día).

**Si se estira el presupuesto: Canon DR-C230.** Es el mejor por características: 60 hojas, ultrasonidos, papel fino para tiques y unos 200.000 escaneos por kit de rodillos. Pero no he podido verificar su precio en España. Las referencias europeas son 313,79 € con IVA (distribuidor para empresas) y 321,44 £ en Reino Unido. Pegas:
- solo USB 2.0;
- las especificaciones no las he podido comprobar con Canon;
- en NAPS2 hay que activar los ultrasonidos y el "Automatic Feeding" desde la ventana del controlador ("Use native UI").

Antes de comprar hay que mirar el precio del día en Amazon.es.

# Escáneres de unos 200 € (epson-otros)

# Escáner para tacos de facturas y tiques: comparativa (consulta del 09/10/2026)

**Cómo se han sacado los datos.** No he podido abrir directamente amazon.es, idealo.es, epson.es, pccomponentes.com ni naps2.com: la red de esta sesión bloquea esas páginas. Todos los precios salen de copias de esas páginas guardadas por el buscador. La fecha de la copia casi nunca aparece, así que los precios son orientativos y hay que confirmarlos el día de la compra. Donde la página indicaba una fecha, la pongo.

## Conclusión

1. **No hay ningún escáner nuevo por unos 200 € que cumpla lo esencial.** Lo esencial es: detección ultrasónica de doble hoja (es justo el fallo de la HP M148), alimentador de 50 hojas o más, y controladores TWAIN o WIA.
   - Por menos de 230 € lo que hay tiene alimentador de 20 hojas, no tiene ultrasonidos, o ninguna de las dos cosas.
   - Ver detalle de cada modelo más abajo.

2. **El más cercano al presupuesto: Ricoh (antes Fujitsu) SP-1120N, unos 233–255 €.**
   - Es el único en esa franja con detección ultrasónica, 50 hojas, TWAIN y WIA en Windows, y conexión USB y red.
   - Pegas: es lento (20 ppm) y los tiques térmicos muy finos o muy cortos quedan en el límite de lo que admite.

3. **Si se puede subir a unos 305 €: Kodak Alaris E1030.** Es claramente mejor para este uso:
   - alimentador de 80 hojas;
   - 30 ppm / 60 ipm a 300 ppp;
   - detección ultrasónica;
   - controladores TWAIN, ISIS y WIA;
   - admite papel desde 27 g/m² y tamaño mínimo 52×52 mm, lo que va mejor con tiques.

   Son unos 50–75 € más que el SP-1120N.

4. **Si prefieren Epson: DS-C330, unos 240–280 € en Amazon.es.**
   - A favor: es más rápido (30 ppm), tiene un modo que arranca solo al meter el papel y una ruta pensada para tiques.
   - En contra: el alimentador es de solo 20 hojas y detecta la doble hoja por longitud, no por ultrasonidos. Para su problema principal encaja peor.

## Tabla de los que encajan o casi

| Modelo | Precio en España (fuente) | Velocidad | Alimentador | Ultrasónico | Controladores en Windows | Conexión |
|---|---|---|---|---|---|---|
| **Ricoh SP-1120N** | 255 € en Amazon.es (vendedor externo, «13 ofertas desde 255 €», «quedan 3»). En PcComponentes: 366,96 € en la ficha (precio válido hasta el 02/09/2026), 232,58 € en los listados, 196,80 € reacondicionado | 20 ppm / 40 ipm a 200/300 ppp | 50 hojas | **Sí** | TWAIN, TWAIN x64, ISIS y WIA (más SANE para Linux) | USB 3.2 y red por cable (Gigabit) |
| **Epson DS-C330** | Amazon.es: 239,99 €, 259 €, 262,78 €, 277,98 € según la copia; terceros desde unos 178–191 €. Epson España: 302,49 € | 30 ppm / 60 ipm (A4 a 300 ppp) | 20 hojas | **No** (detecta por longitud) | WIA, ISIS, TWAIN (Epson Scan 2), SANE | Solo USB 2.0 |
| **Epson ES-C320W** | Amazon.es: 281,87 € (precio recomendado 309,99 €). Epson España: 302,49 € | 30 ppm / 60 ipm | 20 hojas | **Las fuentes se contradicen** | TWAIN (Epson Scan 2); WIA no lo he confirmado | USB y Wi-Fi |
| **Kodak E1030** (algo más caro) | Amazon.es: 305 € (precio recomendado 414,92 €); PcComponentes: 470,05 € | 30 ppm / 60 ipm a 300 ppp | 80 hojas | **Sí** | TWAIN, ISIS, WIA, SANE | USB 3 |
| **Canon DR-C225 II** (algo más caro) | Amazon.es: 298,68 €; PcComponentes: 355,67 € | 25 ppm / 50 ipm (a 200 ppp) | 45 hojas (ficha europea) o 30 | **Sí** (y por longitud) | TWAIN, ISIS; WIA sin confirmar | USB |
| HP ScanJet Pro 2000 s2 | Amazon.es: 245 € (209 € de segunda mano); PcComponentes: 250,87 € (precio vigente hasta julio de 2026) | 35 ppm / 70 ipm | 50 hojas | **No detecta doble hoja** | TWAIN, WIA, ISIS | USB 3.0 |
| Brother ADS-1300 | PcComponentes: 244,99 € (copia antigua); tienda Brother: 312,69 € | 30 ppm / 60 ipm | 20 hojas | No consta | TWAIN, WIA | USB-C |
| Kodak ScanMate i940 | Amazon.es: 225 € (vendedor Kodak) | 20 ppm / 40 ipm en blanco y negro, 15 / 30 en color, a 200 ppp | 20 hojas | No consta | TWAIN, ISIS, WIA | USB |

## Ficha de cada modelo

### Ricoh SP-1120N (la opción más cercana al presupuesto)

- **Sigue a la venta en 2026.** Tiene ficha activa en Ricoh y tiendas, y controladores PaperStream IP 3.42.1 publicados el 10/09/2025. Ricoh también vende el SP-1125N (25 ppm) y el SP-1130N (30 ppm) sobre el mismo aparato.
- **Detección de doble hoja:** «Overlap detection (Ultrasonic sensor)» más rodillo de freno.
- **Papel:**
  - tamaño mínimo 52×74 mm;
  - de 50 a 209 g/m²;
  - papel largo hasta 3.048 mm;
  - tarjetas de plástico hasta 0,76 mm (en relieve hasta 1,24 mm).
- **Aviso sobre los tiques:** los tiques térmicos de menos de 50 g/m², o más cortos de 74 mm, quedan fuera de lo que admite. Habría que probarlos o usar una funda de transporte.
- **Resolución óptica:** 600×600 ppp.
- **Automatización:**
  - Solo tiene botón de Escanear/Parar.
  - El manual explica cómo asociar ese botón en Windows (Propiedades del escáner → pestaña «Eventos») a la aplicación que debe abrirse. PaperStream Capture permite asociar al botón un perfil que guarda el PDF en una carpeta.
  - No he encontrado que tenga arranque automático al meter el papel.
- **Rodillos:** kit PA03708-0001, cambio cada 100.000 hojas o cada año, lo que llegue antes.
  - No he encontrado el precio oficial en euros.
  - Hay un kit compatible no original en Amazon.es por 26,35 €.
- **Opiniones:** 3,9/5 con 35 opiniones en PcComponentes. Un usuario dice que «no se atasca ni se traga ninguna»; las quejas son por los controladores y el software, no por la alimentación del papel. No he encontrado opiniones concretas sobre tiques.
- **Fuentes:**
  - https://www.pfu.ricoh.com/global/scanners/fi/sp1120n/
  - https://www.pfu-emea.ricoh.com/_Assets/Datasheets/SP-Series/Ricoh-SP-Series-1120N-1125N-1130N-ENG.pdf
  - https://www.pfu.ricoh.com/global/scanners/fi/dl/win-11-sp-11xxn.html
  - https://store.pfu-us.ricoh.com/pa03708-0001/
  - https://www.pfu-emea.ricoh.com/es-es/hardware/scanners/sp-series/sp1130
  - https://origin.pfultd.com/downloads/IMAGE/manual/sp-11xxn/P3PC-6882-05ENZ2.pdf
  - https://origin.pfultd.com/downloads/IMAGE/manual/psc/P2WW-4050-07ENZ0.pdf
  - https://www.amazon.es/Ricoh-SP-1120n-Dokumentenscanner-Gigabit-pa03811-B001/dp/B08BKMXM9L
  - https://www.pccomponentes.com/fujitsu-ricoh-sp-1120n-escaner-de-documentos-con-adf-duplex
  - https://www.pccomponentes.com/opiniones/fujitsu-ricoh-sp-1120n-escaner-de-documentos-con-adf-duplex
  - https://www.amazon.es/gp/new-releases/computers/937765031

### Epson DS-C330

- **Lo básico:**
  - 600×600 ppp ópticos;
  - de 40 a 413 g/m²;
  - hasta 5.000 páginas al día;
  - elimina páginas en blanco y endereza.
- **Detección de doble hoja solo por longitud:**
  - Epson Singapur y el folleto de la gama dicen «Length Detection».
  - Epson Oriente Medio pone «Ultrasonic Sensor: No» (y además lo marca como descatalogado en esa región).
  - En la misma gama, Epson España presenta el sensor ultrasónico como la ventaja del DS-C490.
- **Automatización:**
  - Tiene un «Modo de alimentación automática»: el escaneo empieza solo al meter el papel, y al terminar se pulsa el botón o «Finalizar» y el archivo va a la carpeta elegida.
  - El botón del escáner lanza un trabajo de Document Capture Pro que guarda en una carpeta.
- **Tiques:**
  - de 53 a 77 g/m²;
  - de 50,8 a 215,9 mm de ancho y hasta 3.048 mm de largo;
  - en la ruta en U admite un taco de hasta 2,4 mm (20 hojas); en la ruta recta, de uno en uno.
- **Rodillos:** kit B12B819731 a 30,99 € en Epson España (aparece como agotado o con poco stock). La duración del rodillo de recogida es de 50.000 hojas según la guía de los ES-C220/C320W; la guía del DS-C330 remite al contador del escáner.
- **Opiniones:** 3,6/5 con solo 6 valoraciones en Amazon.es. No son suficientes para sacar conclusiones.
- **Fuentes:**
  - https://www.epson.es/es_ES/productos/esc%C3%A1neres/esc%C3%A1neres-para-empresas/ds-c330/p/40555
  - https://www.amazon.es/EPSON-DS-C330-Esc%C3%A1ner-Escritorio-Compacto/dp/B0C9Y719F2
  - https://www.amazon.es/Vertical-Documentos-Alimentador-Autom%C3%A1tico-escaneado/dp/B0C9Y719F2
  - https://www.epson.com.sg/Scanners/Sheetfed-Scanners/Epson-WorkForce-DS-C330-Portable-Sheet-fed-Document-Scanner/p/B11B272501
  - https://www.epson-middleeast.com/en/scanners/document/sheetfed/ds-c330-b11b272401
  - https://download.epson.com.sg/product_brochures/scanner/ESD/Scanner-Range-ES-C380W-ES-C320W.pdf
  - https://download4.epson.biz/sec_pubs/ds-c330/useg/en/GUID-49D1FC41-261C-4A72-961F-072C79B9F04F.htm
  - https://download4.epson.biz/sec_pubs/ds-c330/useg/en/GUID-7E49CCA8-36A7-41B3-BBEF-8AE088035A99.htm
  - https://download4.epson.biz/sec_pubs/ds-c330/useg/en/GUID-A9BB996A-2F8E-4B92-9DAE-83D0357E3B5B.htm
  - https://www.epson.es/es_ES/productos/opciones/roller-assembly-kit/p/40567
  - https://files.support.epson.com/docid/cpd6/cpd63180.pdf

### Epson ES-C320W

- Es el mismo aparato que el DS-C330 con Wi-Fi añadido. Tiene el mismo modo de alimentación automática y admite tiques en la ruta en U.
- **Ultrasonidos sin aclarar:** la ficha de Epson Australia dice «By ultrasonic wave / By length». El folleto de la gama de Epson Singapur y las fichas de Oriente Medio y Sudáfrica dicen solo longitud o «Ultrasonic: No».
- **Opiniones:** 4,0/5 con 85 valoraciones en Amazon.es.
  - Quejas: el software, que no escanea a una unidad de red sin PC y que «la alimentación no está bien resuelta» (una opinión de 3 estrellas).
  - Recomiendan usar USB porque el Wi-Fi es más lento.
- **Fuentes:**
  - https://www.epson.es/es_ES/productos/esc%C3%A1neres/business/es-c320w/p/40558
  - https://www.amazon.es/Epson-ES-C320W-alimentaci%C3%B3n-procesamiento-Multimedia/dp/B0C9Y8PLHW
  - https://epson.com.au/products/scanner/WorkForceES-C320W_Specs.asp
  - https://www.epson-middleeast.com/en/scanners/document/sheetfed/es-c320w-b11b270402bb
  - https://download4.epson.biz/sec_pubs/es-c320w/useg/en/GUID-49D1FC41-261C-4A72-961F-072C79B9F04F.htm
  - https://epson.com/faq/SPT_B11B270201~faq-0000601-esc220_c320w_rr400w

### Kodak E1030 (la mejor opción si se acepta pagar unos 305 €)

- **Lo básico:** sustituye al E1025, hasta 4.000 páginas al día, 600 ppp ópticos, papel largo hasta 3.000 mm.
- **Opiniones:** 4,2/5 con solo 7 valoraciones en Amazon.es (silencioso y rápido; pide USB 3.0 y cable de 3 m como máximo).
- **Rodillos:** el kit dura unas 200.000 lecturas. Cuesta 90 £ con IVA en una tienda del Reino Unido; no he encontrado precio en España.
- **Sin comprobar:** si arranca solo al meter el papel.
- **Fuentes:**
  - https://www.amazon.es/KODAK-8011876-E1030-A4/dp/B0BVL18BHN
  - https://www.argecy.com/kodak-e1030-scanner
  - https://www.shidirect.com/product/45626755/Kodak-E1030-Document-scanner
  - https://www.pccomponentes.com/escaner-kodak-e1030-cmos-cis-adf-216x3000mm-600x600-dpi-24bit-led-rgb-blanco-negro
  - https://www.thescannershop.com/genuine-kodak-alaris-e1000-roller-kit/

### Canon DR-C225 II (algo más caro)

- Detecta la doble hoja por ultrasonidos y por longitud.
- Tiene una ruta en J (de 52 a 128 g/m²) y una ruta recta (de 40 a 209 g/m²).
- Es más lento que el E1030 y tiene menos alimentador.
- **Fuentes:**
  - https://www.canon-europe.com/business/products/scanners/document-scanners/imageformula-dr-c225-ii/specifications/
  - https://www.amazon.es/Canon-imageFORMULA-Documentos-Alimentador-Instalaci%C3%B3n/dp/B07FQKKQLP
  - https://www.pccomponentes.com/canon-imageformula-dr-c225-ii-escaner-compacto-de-documentos

### HP ScanJet Pro 2000 s2 (casi; queda fuera por no detectar doble hoja)

- La ficha oficial de HP dice «Multifeed detection: No». Es el mismo fallo que ya tienen con la M148.
- **Opiniones:** entre 4,1 y 4,3 sobre 5 con 275–418 valoraciones en Amazon.es. Hay quejas con Windows 11, averías al cabo del tiempo y el software fallando en tandas de unas 200 páginas.
- **Fuentes:**
  - https://www.hp.com/emea_africa-en/products/scanners/product-details/product-specifications/28517071
  - https://h20195.www2.hp.com/v2/GetPDF.aspx/c08112377.pdf
  - https://www.amazon.es/HP-6FW06A-B19-ScanJet-2000s2/dp/B085VQJR93
  - https://www.pccomponentes.com/hp-scanjet-pro-2000-s2-escaner-documental-a4

### Brother ADS-1300 y Kodak ScanMate i940 (quedan fuera)

- Los dos tienen alimentador de 20 hojas y ninguna ficha indica detección ultrasónica.
- El i940 además solo aguanta 1.000 páginas al día y va lento en color.
- **Fuentes:**
  - https://www.brother.es/escaneres/ads-1300
  - https://www.brother.eu/-/media/product-downloads/devices/scanners/ads/ads1300/ads-1300.pdf
  - https://store.brother.es/devices/scanners/ads/ads1300
  - https://www.amazon.es/Kodak-ScanMate-i940-Scanner-Esc%C3%A1ner/dp/B008DLXAFA
  - https://alarisworld.com/solutions/document-scanners/desktop/scanmate-i940-scanner

## Descartados

| Modelo | Motivo | Fuente |
|---|---|---|
| Epson ES-C220 | Solo lo he encontrado con referencia de EE. UU. (B11B272202); no aparece en la gama de Epson España | https://epson.com/p/B11B272202 |
| Epson RR-60 | Portátil de hoja a hoja, sin alimentador; mercado de EE. UU. y Canadá | https://www.staples.ca/products/3000775-en-epson-rapidreceipt-rr-60-mobile-receipt-and-colour-document-scanner |
| Epson ES-C380W | 423,90 € en Epson (hasta 369,99 € en oferta); 20 hojas | https://epson.es/es_ES/productos/esc%C3%A1neres/esc%C3%A1neres-para-empresas/es-c380w/p/40561 |
| Epson DS-C490 | Sí es ultrasónico, pero cuesta 497,97 € en Amazon.es y 567,90 € en Epson | https://www.amazon.es/Epson-Premium-Scanner-DS-C490-procesamiento/dp/B0CB1M5ZZD |
| Epson ES-400 II | No está en Epson España; en Amazon.es solo por importación, 342,61 € (incluye 64,61 € de aduana) | https://www.amazon.es/Epson-ES-400-II-alimentador-herramientas/dp/B08P3YVH3X |
| Epson ES-500W II | Descatalogado por Epson España; 369–415 € | https://www.epson.es/es_ES/productos/esc%C3%A1neres/esc%C3%A1neres-para-empresas/workforce-es-500w-ii/p/30513 |
| Epson ES-580W | 397–476 € | https://www.amazon.es/Epson-Workforce-ES-580W-Esc%C3%A1ner-alimentatore/dp/B08R3XPHGH |
| Epson DS-410, DS-530 II | 320–477 € | https://www.amazon.es/Epson-Workforce-DS-410-Manual-Scanner/dp/B074PLQ21W · https://www.pccomponentes.com/epson-workforce-ds-530ii-escaner-de-documentos |
| ScanSnap iX1300 | 319 € y sin TWAIN ni WIA; con NAPS2 solo funcionaría con carpeta vigilada | https://www.amazon.es/Esc%C3%A1ner-autom%C3%A1tico-Documentos-ScanSnap-iX1300/dp/B09H2SS5K9 |
| ScanSnap iX1400 / iX1600 | 380–440 € y 459–630 €; Ricoh confirma que en Windows no tienen TWAIN ni ISIS | https://www.pfu-ca.ricoh.com/-/media/project/scanners-pci/files/products/datasheets/scansnap_ix1400_1600_en_ca.pdf |
| Ricoh fi-800R | 440–474 € | https://www.pccomponentes.com/escaners/fujitsu |
| Plustek PS186 | 298,61 €, descatalogado según la tienda CDW, sin ultrasonidos en la ficha | https://www.amazon.es/Plustek-Documentos-Velocidad-alimentador-autom%C3%A1tico/dp/B074TCWHYR |
| Avision AD215L / AD230U / AD240U | AD215L: 266,35 €, 20 hojas, la versión L no tiene ultrasonidos. AD230U: 385 €. AD240U: 485–520 € | https://www.amazon.es/Avision-1513B-esc%C3%A1ner-Documentos-ad215l/dp/B07HDXSWZ7 · https://www.thescannershop.com/docs/AD215%20series%20ENG_20171108.pdf |
| Kodak E1025 | Ya no se vende nuevo; lo sustituye el E1030 | https://support.alarisworld.com/e1025-scanner |
| Doxie Pro DX400 / Q2 | DX400: 486,68 €. Q2: no disponible y sin dúplex | https://www.amazon.es/Doxie-Pro-DX400-documentos-escritorio/dp/B08KKMYRBN |
| HP N4000 snw1 / 3000 s4 / 2600 f1 | 603,79 € / 311–430 € / 286–299 € (el 2600 f1 lleva cristal plano y va a 25 ppm) | https://www.hp.com/es-es/shop/products/printers/hp-scanjet-pro-n4000-snw1-arkmatad-skanner-6fw08a-b19 · https://www.pccomponentes.com/hp-scanjet-pro-3000-s4-escaner-de-documentos |
| Canon R40 | 373–432 € | https://www.canon.es/store/canon-escaner-de-sobremesa-imageformula-r40-de-canon/4229C002/ |
| Brother ADS-2200 / ADS-4100 / ADS-1800W | Unos 274–385 €; no he podido confirmar que tengan ultrasonidos | https://www.mediamarkt.es/es/product/_escaner-brother-ads4100-600-x-600-ppp-35-ppm-hasta-70-paginas-negro-y-blanco-1535592.html · https://store.brother.es/devices/scanners/ads/ads1800w |

## Cómo encaja con su programa (NAPS2)

- **NAPS2 no publica lista de escáneres compatibles.** Usa el controlador WIA o TWAIN que instala el fabricante, o ESCL por red. Con la consola se elige así: `--driver twain|wia|escl`, se buscan los escáneres con `--listdevices` y el dúplex con `--source duplex`.
  - https://www.naps2.com/doc/command-line
  - https://www.naps2.com/windows-scanning
- **No he encontrado informes de NAPS2 con ninguno de estos modelos.** Hay un caso abierto en el GitHub de NAPS2 de un multifunción Epson cuyo alimentador no aparecía (#618). Conviene probar `--listdevices` y una tanda en dúplex antes de que acabe el plazo de devolución.
  - https://github.com/cyanfish/naps2/issues/618
- **NAPS2 elimina páginas en blanco y endereza por su cuenta** (opción `--deskew`), sea cual sea el escáner. La detección de doble hoja, en cambio, es del controlador: hay que comprobar que siga activa al escanear desde NAPS2.
  - https://www.naps2.com/doc/profile-settings
- **Funciones automáticas sin comprobar con NAPS2:**
  - El modo de alimentación automática de Epson está en la ventana de Epson Scan 2; no sé si funciona llamado desde NAPS2.Console.
  - El botón del escáner (Ricoh: pestaña Eventos de Windows o perfil de PaperStream Capture; Epson: trabajo de Document Capture Pro) se puede llevar a una carpeta vigilada.
  - No he podido comprobar si el botón puede lanzar directamente un script que llame a NAPS2.Console.

## Verificación

# Verificación adversarial: escáneres para la asesoría (consulta del 09/10/2026)

**No he podido comprobar ningún precio.** Las especificaciones de los fabricantes tampoco las he podido comprobar. Lo que sí he podido comprobar es la compatibilidad con NAPS2, y eso corrige varias cosas del informe.

- **Búsqueda web:** se agotó el cupo (200 búsquedas por turno, compartidas con los otros agentes) antes de mi primera consulta.
- **Webs bloqueadas:** no se pueden abrir amazon.es, idealo.es, pccomponentes.com, mediamarkt.es, fnac.es, elcorteingles.es, alternate.es, camelcamelcamel, epson.es/.com, pfu.ricoh.com, canon-europe.com, hp.com, alarisworld.com ni naps2.com.
- **Lo que sí funciona:** github.com, raw.githubusercontent.com y gitlab.com. Con ellos he revisado el código y los casos abiertos de NAPS2 y las listas de escáneres compatibles de SANE (los controladores de Linux).
- **Para seguir:** el usuario puede enviar otro mensaje para reanudar las búsquedas, o subir el límite con CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION.

## 1. Precios y disponibilidad

**Ningún precio se puede verificar hoy.** Hay que confirmarlos todos el día de la compra.

| Afirmación del informe | Veredicto |
|---|---|
| SP-1120N: 255 € en Amazon.es («13 ofertas», «quedan 3») | No verificable. Ojo: lo venden terceros, no Amazon, y eso afecta a devoluciones y garantía. |
| SP-1120N: 366,96 € en la ficha de PcComponentes, «válido hasta el 02/09/2026» | **Dato caducado**: esa fecha ya ha pasado. Los 232,58 € de los listados y los 196,80 € del reacondicionado no tienen fecha. |
| HP 2000 s2: 250,87 € en PcComponentes, «vigente hasta julio de 2026» | **Dato caducado**. |
| DS-C330: de 239,99 a 277,98 € en Amazon.es; terceros desde unos 178–191 € | No verificable. Si los 178–191 € son reales, sería el único modelo nuevo dentro de 200 €. |
| DS-C330 y ES-C320W: los dos a 302,49 € en Epson España | **Probable error de copia.** Es raro que el modelo con Wi-Fi cueste lo mismo; hay que revisarlo. |
| Kodak E1030: 305 € en Amazon.es frente a 470,05 € en PcComponentes | No verificable. Una diferencia del 54 % hace pensar en una oferta puntual o de un vendedor externo. |
| Canon DR-C225 II 298,68 €, ES-C320W 281,87 €, Kodak i940 225 €, Brother ADS-1300 244,99 € («copia antigua») | No verificables. |
| Que se sigan vendiendo (SP-1120N, DS-C330, E1030, i940) | No verificable. El DS-C330 consta como descatalogado en Oriente Medio. Del i940 (de 2012) conviene confirmar que no esté descatalogado. |

## 2. Especificaciones: ultrasonidos, alimentador, velocidad

No he podido abrir ninguna ficha de fabricante. Por eso todo lo de esta tabla es **no verificable hoy**, salvo donde indico un dato concreto.

| Afirmación | Veredicto |
|---|---|
| SP-1120N: ultrasónico, 50 hojas, 20 ppm / 40 ipm, papel de 50 a 209 g/m², mínimo 52×74 mm | No verificable. Coincide con lo que sé del modelo. |
| DS-C330: 20 hojas, detecta la doble hoja por longitud y no por ultrasonidos, 30 ppm | No verificable. Coincide con lo que sé. |
| ES-C320W: ultrasonidos sí o no | No verificable. Sigue sin aclararse; hay que preguntarlo a Epson España antes de comprarlo. |
| E1030: 80 hojas, ultrasónico, 30 ppm, papel desde 27 g/m², mínimo 52×52 mm | No verificable. Los dos últimos datos (27 g/m² y 52×52 mm) son los que más dudas me generan. |
| DR-C225 II: «45 hojas (ficha europea) o 30» | **Dudoso.** Recuerdo 30 hojas (dato de memoria, sin comprobar). Hay que confirmarlo en la ficha de Canon. |
| HP 2000 s2: «Multifeed detection: No» | No verificable. Coincide con lo que sé. |

## 3. Controladores TWAIN y WIA, y compatibilidad con NAPS2

**Opciones de la consola de NAPS2: confirmado.** Sus opciones de línea de comandos (`--driver twain|wia|escl`, `--listdevices`, `--source duplex` y `--deskew`) existen.
- El código admite además `sane` y `apple`.
- https://raw.githubusercontent.com/cyanfish/naps2/master/NAPS2.Lib/Automation/AutomatedScanningOptions.cs

**Quitar páginas en blanco y enderezar: confirmado.** Los perfiles de NAPS2 tienen `ExcludeBlankPages`, `AutoDeskew` y `EnableAutoSave`.
- Quitar páginas en blanco no tiene opción propia en la consola: se activa en el perfil y se usa con `--profile`.
- https://raw.githubusercontent.com/cyanfish/naps2/master/NAPS2.Lib/Scan/ScanProfile.cs

**Caso #618 de NAPS2: corregido.** El informe dice que es «un caso abierto», pero está **cerrado** (08/06/2025).
- Es de un multifunción Epson PX820FWD.
- La solución que dio el autor de NAPS2 fue cambiar entre WIA y TWAIN o reinstalar el controlador de Epson.
- https://github.com/cyanfish/naps2/issues/618

**ScanSnap iX1300 sin TWAIN ni WIA: confirmado.**
- Caso #439 de NAPS2: el autor dice que añadir controladores no estándar queda fuera del proyecto. Lo único que propone es una máquina virtual con Linux.
- SANE sí admite el iX1300 y el iX1600, pero solo en Linux, así que no es práctico para la asesoría.
- https://github.com/cyanfish/naps2/issues/439
- https://gitlab.com/sane-project/backends/-/raw/master/doc/descriptions/fujitsu.desc

**«Con NAPS2 solo funcionaría con carpeta vigilada»: corregido.** NAPS2 no vigila carpetas: es una función pedida y todavía sin hacer (caso #660, abierto). Con un ScanSnap, NAPS2 no participaría en el escaneo. Haría falta que su propio programa recogiera los PDF de la carpeta.
- https://github.com/cyanfish/naps2/issues/660

**«No he encontrado informes de NAPS2 con ninguno de estos modelos»: corregido.**
- Con el SP-1125, de la misma familia de controladores PaperStream IP que el SP-1120N, NAPS2.Console funciona con `--driver twain` (casos #423 y #412).
- Un usuario con un **SP-1120N** cuenta que el botón del escáner arranca NAPS2 (caso #792).
- https://github.com/cyanfish/naps2/issues/423
- https://github.com/cyanfish/naps2/issues/412
- https://github.com/cyanfish/naps2/issues/792

**«El botón puede lanzar NAPS2»: aclarado.** NAPS2 se apunta en Windows para los avisos del botón del escáner (`/StiDevice`, que pone `ShouldScan=true`). La función existe desde la versión 4.4.0.
- Lanza la ventana normal de NAPS2, no NAPS2.Console.
- **Fallo abierto (#792, NAPS2 8.2.1):** si ningún perfil usa WIA, al pulsar el botón se abre la ventana de crear perfil en vez de escanear. Hay que tener un perfil WIA como predeterminado.
- https://raw.githubusercontent.com/cyanfish/naps2/master/NAPS2.Lib/Platform/Windows/StillImage.cs
- https://raw.githubusercontent.com/cyanfish/naps2/master/CHANGELOG.md

**Epson Scan 2 con NAPS2.Console: problema nuevo.** Con un DS-530 II y TWAIN, cuando el alimentador está vacío sale una ventana de error que bloquea la automatización.
- Con WIA, la consola se queda colgada unos segundos después de unas 4 tandas.
- El caso #714 sigue abierto y sin respuesta del autor. Es probable que afecte también al DS-C330, que usa el mismo controlador.
- https://github.com/cyanfish/naps2/issues/714

**Controladores de Linux (SANE):** el DS-C330 aparece como totalmente compatible. El ES-C320W no aparece en esa lista.
- https://gitlab.com/sane-project/backends/-/raw/master/doc/descriptions/epsonds.desc

**Controladores de Windows de Kodak E1030, Canon DR-C225 II, HP 2000 s2, Brother ADS-1300 y Kodak i940:** no verificables. No he encontrado casos de NAPS2 con esos modelos.

## 4. Arranque automático al meter el papel

**NAPS2 no tiene ninguna opción de «esperar a que haya papel»: confirmado.** Lo más parecido en el perfil es una pausa entre escaneos con WIA.
- https://raw.githubusercontent.com/cyanfish/naps2/master/NAPS2.Lib/Scan/ScanProfile.cs

**Modo de alimentación automática de Epson:** solo está en la ventana de Epson Scan 2.
- Desde NAPS2.Console no funciona, porque la consola no tiene esa opción.
- Desde la ventana de NAPS2 con la ventana propia del controlador activada (`UseNativeUI`), quizá sí. No lo he podido verificar.

**SP-1120N, Kodak E1030 y Canon DR-C225 II:** no hay pruebas de que arranquen solos al meter el papel. Lo más automático que está comprobado es el botón del escáner, que arranca NAPS2 con un perfil WIA y guardado automático.

## 5. Fallos de planteamiento del informe

- **«Si se estira un poco» no puede ser el E1030.** A unos 305 € está un 50 % por encima de los 200 €. Lo que de verdad es estirar un poco es el SP-1120N, a unos 233–255 €.
- **El SP-1120N reacondicionado (196,80 € en PcComponentes, sin fecha) entra en presupuesto.** Contradice la conclusión 1 («no hay nada por unos 200 €»), aunque no sea nuevo ni de Amazon.

## Clasificación final

**Ninguno de estos precios lo he verificado hoy.** Son los del informe, de copias guardadas por el buscador y casi siempre sin fecha. Hay que confirmarlos el día de la compra.

1. **Ricoh SP-1120N**
   - Precio: unos 232,58 € en PcComponentes, 196,80 € reacondicionado; 255 € en Amazon.es, de vendedores externos.
   - A favor: detección ultrasónica de doble hoja, alimentador de 50 hojas y TWAIN y WIA. Es el único con pruebas de que funciona con NAPS2: consola con TWAIN en el SP-1125 y botón que arranca NAPS2 en el SP-1120N.
   - Pegas:
     - 20 ppm;
     - no arranca solo al meter el papel;
     - el fallo #792 obliga a tener un perfil WIA como predeterminado;
     - los tiques de menos de 50 g/m² o de menos de 74 mm quedan fuera de lo que admite;
     - en Amazon solo hay vendedores externos.
2. **Epson DS-C330**
   - Precio: 239,99 € en Amazon.es; 178–191 € en vendedores externos.
   - A favor: 30 ppm, modo de alimentación automática y una ruta pensada para tiques.
   - Pegas:
     - alimentador de 20 hojas;
     - detecta la doble hoja por longitud, no por ultrasonidos;
     - el modo automático solo funciona en Epson Scan 2, no desde NAPS2.Console;
     - es probable que en NAPS2.Console salga la ventana de error con el alimentador vacío (#714);
     - solo USB 2.0;
     - descatalogado en Oriente Medio.
3. **HP ScanJet Pro 2000 s2**
   - Precio: 245 € en Amazon.es; 209 € de segunda mano.
   - A favor: 35 ppm, 50 hojas, TWAIN y WIA, y muchas opiniones.
   - Pega: no detecta la doble hoja de ninguna manera. Si su problema es justo ese, descartadlo. El Kodak i940 (225 €) y el Brother ADS-1300 son peores: 20 hojas y sin ultrasonidos.

**Si se estira un poco:**
- **Hasta unos 255 €:** el SP-1120N nuevo en Amazon.es.
- **Hasta unos 305 €:** el Kodak E1030.
  - A favor: 80 hojas, ultrasonidos y TWAIN, ISIS y WIA (no verificado hoy).
  - Pegas:
    - el precio de 305 € es dudoso: PcComponentes lo tiene a 470 €;
    - solo 7 opiniones en Amazon.es;
    - no hay pruebas con NAPS2;
    - no se sabe si arranca solo al meter el papel.

