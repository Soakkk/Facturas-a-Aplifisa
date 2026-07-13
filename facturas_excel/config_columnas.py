"""Lee la configuracion XML del gestor fiscal (gastos.xml / ingresos.xml) y la
convierte en un mapa {campo_semantico -> letra de columna}.

Asi el Excel que generamos coincide EXACTAMENTE con la configuracion que el
usuario carga en su gestor con 'Leer configuracion'.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict


# Etiqueta XML del gestor -> nombre de campo en nuestro modelo Factura.
# EDITFRAPROVE (compras) y EDITFRARECIB (ventas) apuntan al mismo dato: num_factura.
TAG_A_CAMPO = {
    "EDITFRAPROVE": "num_factura",
    "EDITFRARECIB": "num_factura",
    "EDITFECHA": "fecha",
    "EDITFECHADEDUCCION": "fecha_deduccion",
    "EDITFECHAOPER": "fecha_operacion",
    "EDITCONCEPTO": "concepto",
    "EDITBASEIVA": "base_iva",
    "EDITIVA": "pct_iva",
    "EDITCUOTAIVA": "cuota_iva",
    "EDITBASEIRPF": "base_irpf",
    "EDITIRPF": "pct_irpf",
    "EDITCUOTAIRPF": "cuota_irpf",
    "EDITBASEREQUIV": "base_requiv",
    "EDITREQUIV": "pct_requiv",
    "EDITCUOTAREQUIV": "cuota_requiv",
    "EDITNIF": "nif",
    "EDITNOMBRE": "nombre",
    "EDITDESCRIPSII": "descripcion_sii",
    "EDITTIPOFACT": "tipo_factura",
    "EDITCLAVEREGESP": "clave_reg_esp",
    "EDITISP": "isp",
    "EDITSUJETACERO": "base_sujeta_cero",
    "EDITRECC": "recc",
    "EDITSUPLIDOS": "suplidos",
    "EDITNOSUJETA": "no_sujeta",
}

# Etiquetas de cabecera legibles para la fila 1 del Excel.
ETIQUETA_CABECERA = {
    "num_factura": "Nº Factura",
    "fecha": "Fecha",
    "fecha_deduccion": "Fecha Deduc.",
    "fecha_operacion": "Fecha Oper.",
    "concepto": "Concepto",
    "base_iva": "Base IVA",
    "pct_iva": "% IVA",
    "cuota_iva": "Cuota IVA",
    "base_irpf": "Base IRPF",
    "pct_irpf": "% IRPF",
    "cuota_irpf": "Cuota IRPF",
    "base_requiv": "Base R.Equiv",
    "pct_requiv": "% R.Equiv",
    "cuota_requiv": "Cuota R.Equiv",
    "nif": "NIF",
    "nombre": "Nombre",
    "descripcion_sii": "Descripcion SII",
    "tipo_factura": "Tipo Factura",
    "clave_reg_esp": "Clave Reg. Esp.",
    "isp": "ISP",
    "base_sujeta_cero": "Base sujeta 0%",
    "recc": "RECC",
    "suplidos": "Suplidos",
    "no_sujeta": "No sujeta",
}


@dataclass
class ConfigColumnas:
    tipo: str                              # "COMPRAS/GASTOS" o "VENTAS/INGRESOS"
    incluye_cabecera: bool = True
    primera_fila: int = 2
    # campo semantico -> letra de columna (solo los que tienen columna asignada)
    columnas: Dict[str, str] = field(default_factory=dict)

    @property
    def es_gastos(self) -> bool:
        return self.tipo.upper().startswith("COMPRAS")


def _texto(root: ET.Element, tag: str) -> str:
    el = root.find(tag)
    return (el.text or "").strip() if el is not None else ""


def leer_config(ruta_xml: str) -> ConfigColumnas:
    """Parsea un XML de configuracion del gestor y devuelve ConfigColumnas."""
    tree = ET.parse(ruta_xml)
    root = tree.getroot()

    tipo = _texto(root, "COMBOBOXCOMPRASVENTAS") or "COMPRAS/GASTOS"
    incluye = _texto(root, "CHECKBOXFICHEROINCLUYECABECERA").upper() == "S"
    try:
        primera = int(_texto(root, "PRIMERAFILADATOSCSV") or "2")
    except ValueError:
        primera = 2

    columnas: Dict[str, str] = {}
    for tag, campo in TAG_A_CAMPO.items():
        letra = _texto(root, tag).upper()
        if letra:
            # Si dos etiquetas apuntan al mismo campo (FRAPROVE/FRARECIB),
            # gana la que tenga valor (solo una lo tiene en cada XML).
            columnas[campo] = letra

    return ConfigColumnas(
        tipo=tipo,
        incluye_cabecera=incluye,
        primera_fila=primera,
        columnas=columnas,
    )
