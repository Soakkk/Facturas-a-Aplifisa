"""Sistema visual unificado de Facturas a Aplifisa."""

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

PAGE = "#F5F8FC"
CARD = "#FFFFFF"
SOFT = "#FAFCFE"
HEAD = "#F5F8FC"
BAR = "#FFFFFF"
INK = "#24384D"
MUTED = "#5D7084"
DIM = "#5D7084"
BORDER = "#DCE5F0"
ACCENT = "#326FA6"
ACCENT_HOVER = "#285E90"
ACCENT_FAINT = "#EAF3FC"
SUCCESS = "#19724E"
WARNING = "#86500A"
DANGER = "#B43737"

# La referencia usa una sola familia sans-serif en toda la interfaz.
FUENTE_UI = '"Segoe UI Variable", "Segoe UI", sans-serif'

QSS = f"""
QWidget {{ color: {INK}; font-family: {FUENTE_UI}; font-size: 12px; }}
QMainWindow, QDialog, QMessageBox, QFileDialog {{ background: {PAGE}; }}

QMenuBar {{
    background: {BAR}; color: {MUTED}; border: none;
    padding: 0 10px; min-height: 28px;
}}
QMenuBar::item {{ padding: 6px 10px; border-radius: 2px; font-weight: 600; }}
QMenuBar::item:selected {{ background: {ACCENT_FAINT}; color: {ACCENT}; }}
QMenu {{ background: {CARD}; border: 1px solid {BORDER}; padding: 3px; }}
QMenu::item {{ padding: 7px 24px 7px 10px; border-radius: 3px; }}
QMenu::item:selected {{ background: {ACCENT_FAINT}; color: {ACCENT}; }}

QWidget#barraRapida, QFrame#filaBarraEstrecha {{
    background: {BAR}; border: none; border-bottom: 1px solid {BORDER};
}}
QWidget#barraRapida QPushButton {{
    min-height: 24px; padding: 5px 12px;
    border-radius: 7px; font-size: 12px; font-weight: 500;
    color: {INK}; background: {CARD}; border: 1px solid {BORDER};
}}
QWidget#barraRapida QPushButton:hover {{
    color: {ACCENT}; background: {ACCENT_FAINT}; border-color: {ACCENT};
}}
QWidget#barraRapida QPushButton#accesoPeligro {{
    color: {DANGER}; border-color: {BORDER}; background: {CARD};
}}
QWidget#barraRapida QPushButton#accesoPeligro:hover {{
    color: {DANGER}; border-color: {DANGER}; background: #FFEDED;
}}
QWidget#barraRapida QPushButton#accesoExito {{
    color: white; border-color: {ACCENT}; background: {ACCENT};
}}
QWidget#barraRapida QPushButton#accesoExito:hover {{
    color: white; border-color: {ACCENT_HOVER}; background: {ACCENT_HOVER};
}}
QWidget#barraRapida QPushButton:disabled {{
    color: {MUTED}; border-color: {BORDER}; background: {SOFT};
}}

QFrame#tarjeta {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#barraCliente {{
    background: {CARD}; border: none; border-bottom: 1px solid {BORDER};
}}
QLabel#tituloSeccion {{ color: {INK}; font-size: 13px; font-weight: 600; }}
QLabel#marca {{ color: {INK}; font-size: 16px; font-weight: 600; }}
QLabel#marcaIcono {{ background: {ACCENT_FAINT}; color: {ACCENT}; border-radius: 8px; font-size: 18px; font-weight: 600; }}
QLabel#tituloMesa {{ color: {INK}; font-size: 20px; font-weight: 600; }}
QLabel#contadorLote {{ color: {MUTED}; font-size: 12px; }}
QLabel#textoSuave {{ color: {MUTED}; font-size: 11px; }}
QLabel#cliente {{ color: {INK}; font-size: 12px; font-weight: 500; }}
QLabel#visor {{ background: {PAGE}; color: {MUTED}; border: none; }}
QScrollArea#visorScroll {{ background: {PAGE}; border: none; border-radius: 6px; }}

QFrame#alerta {{ background: #FFF4DF; border: none; border-radius: 8px; }}
QLabel#alertaTitulo {{ color: {WARNING}; font-size: 12px; font-weight: 600; }}
QLabel#alertaTexto {{ color: {INK}; font-size: 12px; }}

QPushButton {{
    background: {CARD}; color: {INK}; border: 1px solid {BORDER};
    border-radius: 7px; padding: 7px 12px; font-weight: 500;
    font-family: {FUENTE_UI}; font-size: 12px;
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; background: {ACCENT_FAINT}; }}
QPushButton:pressed {{ background: {ACCENT_FAINT}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ background: {SOFT}; color: {MUTED}; border-color: {BORDER}; }}
QPushButton#filtroTipo:checked, QPushButton#paso:checked {{ background: {ACCENT_FAINT}; color: {ACCENT}; border-color: {ACCENT}; }}
QPushButton#paso {{ border-color: transparent; background: transparent; }}
QPushButton#primario {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
QPushButton#primario:hover {{ background: {ACCENT_HOVER}; color: white; }}
QPushButton#exito {{ background: {SUCCESS}; color: white; border-color: {SUCCESS}; }}
QPushButton#exito:hover {{ background: #128249; color: white; }}
QPushButton#peligro {{ color: {DANGER}; }}
QPushButton#peligro:hover {{ border-color: {DANGER}; color: {DANGER}; }}
QPushButton#compacto {{ padding: 5px 11px; }}
QPushButton#compacto:disabled {{
    background: {CARD}; color: {INK}; border-color: {BORDER};
}}
QPushButton#accionTabla, QPushButton#menuAcciones {{ padding: 6px 10px; }}
QPushButton#botonIcono {{ min-width: 28px; max-width: 28px; padding: 4px 0; }}
QPushButton#botonVisor {{
    min-width: 28px; max-width: 28px; min-height: 26px; max-height: 26px;
    padding: 0; border: none; background: transparent; color: {ACCENT};
}}
QPushButton#botonVisor:hover {{ background: {ACCENT_FAINT}; border: none; }}

QLineEdit, QComboBox {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 7px;
    padding: 6px 8px; font-family: {FUENTE_UI};
    selection-background-color: {ACCENT}; selection-color: white;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QLineEdit#buscadorLote {{ padding: 10px 12px; font-size: 13px; }}
QComboBox QAbstractItemView {{
    background: {CARD}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT_FAINT}; selection-color: {ACCENT};
}}

QTableWidget {{
    background: {CARD}; alternate-background-color: {SOFT};
    border: none; border-radius: 4px; gridline-color: {BORDER};
    selection-background-color: {ACCENT_FAINT}; selection-color: {INK};
    font-family: {FUENTE_UI}; font-size: 12px;
}}
QHeaderView::section {{
    background: {HEAD}; color: {DIM}; border: none;
    border-bottom: 1px solid {BORDER};
    padding: 9px 6px; font-weight: 500; font-size: 12px;
}}
QTableWidget QComboBox {{ border: none; border-radius: 3px; padding: 3px 5px; background: transparent; }}
QSplitter::handle {{ background: {PAGE}; }}
QProgressBar {{
    background: #E8EDF4; border: none; border-radius: 2px;
    min-height: 8px; max-height: 8px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}
QStatusBar {{ background: {CARD}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QToolTip {{
    background: {CARD}; color: {INK}; border: 1px solid {BORDER};
    border-left: 3px solid {ACCENT}; padding: 8px 10px;
}}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #A9ADB3; border-radius: 4px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: #858B94; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #A9ADB3; border-radius: 4px; min-width: 36px; }}
QScrollBar::handle:horizontal:hover {{ background: #858B94; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QFrame#ficha {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 5px; }}
QLabel#fichaTitulo {{ font-size: 11px; font-weight: 700; color: {DANGER}; }}
QLabel#fichaLinea {{ color: {INK}; font-size: 12px; }}
QLabel#fichaPie {{ color: {MUTED}; font-size: 11px; }}
"""

ESTADO_OK = SUCCESS
ESTADO_REVISAR = WARNING
ESTADO_ERROR = DANGER
ESTADO_REVISADO = ACCENT
ESTADO_MANUAL = MUTED

# Compatibilidad con nombres importados por app.py.
NAVY = ACCENT
NAVY_HOVER = ACCENT_HOVER
WARNING_ = WARNING


def aplicar_tema(app):
    app.setStyle("Fusion")
    familias = set(QFontDatabase.families())
    familia = ("Segoe UI Variable" if "Segoe UI Variable" in familias
               else "Segoe UI")
    app.setFont(QFont(familia, 10))
    paleta = app.palette()
    rol = QPalette.ColorRole
    paleta.setColor(rol.Window, QColor(PAGE))
    paleta.setColor(rol.WindowText, QColor(INK))
    paleta.setColor(rol.Base, QColor(CARD))
    paleta.setColor(rol.AlternateBase, QColor(SOFT))
    paleta.setColor(rol.Text, QColor(INK))
    paleta.setColor(rol.Button, QColor(CARD))
    paleta.setColor(rol.ButtonText, QColor(INK))
    paleta.setColor(rol.Highlight, QColor(ACCENT))
    paleta.setColor(rol.HighlightedText, QColor("#FFFFFF"))
    paleta.setColor(rol.PlaceholderText, QColor(MUTED))
    app.setPalette(paleta)
    app.setStyleSheet(QSS)
