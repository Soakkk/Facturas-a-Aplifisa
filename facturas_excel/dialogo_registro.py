"""El resultado de contrastar el lote con el listado de apuntes de Aplifisa.

Cierra el circulo de comprobaciones: factura escaneada -> Excel -> lo que de
verdad quedo registrado. Se ve de un vistazo lo que falta por registrar, lo que
esta registrado de mas y lo que entro con otro importe.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QTextBrowser, QVBoxLayout,
)

from .registro import Informe, Registro
from .resumen import eur


class DialogoRegistro(QDialog):
    def __init__(self, informe: Informe, registro: Registro, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Comprobación contra el registro de Aplifisa")
        self.resize(760, 560)
        raiz = QVBoxLayout(self)

        if not registro.bien_leido:
            aviso = QLabel(
                "⚠ El listado no se ha podido leer del todo: sus propios "
                "totales no cuadran con lo leído. Trate el resultado con "
                "cuidado.")
            aviso.setObjectName("alertaTitulo")
            aviso.setWordWrap(True)
            raiz.addWidget(aviso)

        titulo = QLabel(
            "<b>Todo cuadra.</b> Cada factura del programa está registrada en "
            "Aplifisa con los mismos importes." if informe.todo_cuadra else
            "<b>Hay diferencias.</b> Revise lo que no coincide antes de dar el "
            "trimestre por bueno.")
        titulo.setWordWrap(True)
        raiz.addWidget(titulo)

        texto = QTextBrowser()
        texto.setHtml(self._html(informe, registro))
        raiz.addWidget(texto, 1)

        botones = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        botones.rejected.connect(self.reject)
        botones.accepted.connect(self.accept)
        raiz.addWidget(botones)

    @staticmethod
    def _html(informe: Informe, registro: Registro) -> str:
        partes = [
            "<h3>Totales</h3>",
            "<table cellpadding='4'>",
            "<tr><td></td><td><b>En el programa</b></td>"
            "<td><b>En Aplifisa</b></td></tr>",
            f"<tr><td>Base</td><td>{eur(informe.base_programa)}</td>"
            f"<td>{eur(informe.base_registro)}</td></tr>",
            f"<tr><td>IVA</td><td>{eur(informe.cuota_programa)}</td>"
            f"<td>{eur(informe.cuota_registro)}</td></tr>",
            f"<tr><td>Líneas</td><td>{informe.emparejadas + len(informe.sin_registrar) + len(informe.distintas)}</td>"
            f"<td>{len(registro.apuntes)}</td></tr>",
            "</table>",
        ]
        if informe.descuadre_base:
            partes.append(
                f"<p><b>Descuadre de base: {eur(informe.descuadre_base)}</b></p>")
        partes.append(f"<p>Emparejadas correctamente: "
                      f"<b>{informe.emparejadas}</b></p>")

        for titulo, lista, explicacion in (
            ("NO están registradas en Aplifisa", informe.sin_registrar,
             "Están en el programa pero no aparecen en el listado: revise si "
             "se quedaron sin importar."),
            ("Registradas con otro importe", informe.distintas,
             "Coinciden en fecha y base, pero el IVA registrado es otro."),
            ("Están en Aplifisa y no en el programa", informe.de_mas,
             "Puede que se registraran a mano, que vengan de otro lote, o que "
             "estén duplicadas."),
        ):
            if not lista:
                continue
            partes.append(f"<h3>{titulo} ({len(lista)})</h3>")
            partes.append(f"<p><i>{explicacion}</i></p><ul>")
            partes += [f"<li>{linea}</li>" for linea in lista[:40]]
            if len(lista) > 40:
                partes.append(f"<li>… y {len(lista) - 40} más</li>")
            partes.append("</ul>")
        return "".join(partes)
