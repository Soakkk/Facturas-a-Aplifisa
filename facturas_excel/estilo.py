"""Sistema visual unificado de Facturas a Aplifisa."""

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

PAGE = "#F7F8FB"
CARD = "#FFFFFF"
SOFT = "#FAFBFD"
HEAD = "#F8FAFC"
BAR = "#071A3A"
INK = "#111827"
MUTED = "#64748B"
DIM = "#0B2A6F"
BORDER = "#D7DFEA"
ACCENT = "#0B2A6F"
ACCENT_HOVER = "#071F55"
ACCENT_FAINT = "#EEF4FF"
SUCCESS = "#16A35A"
WARNING = "#D68A00"
DANGER = "#E11D2E"

# La referencia usa una sola familia sans-serif en toda la interfaz.
FUENTE_UI = '"Segoe UI Variable", "Segoe UI", sans-serif'

QSS = f"""
QWidget {{ color: {INK}; font-family: {FUENTE_UI}; font-size: 12px; }}
QMainWindow, QDialog, QMessageBox, QFileDialog {{ background: {PAGE}; }}

QMenuBar {{
    background: {BAR}; color: #F1F5F9; border: none;
    border-bottom: 1px solid #1B3358; padding: 0 10px; min-height: 30px;
}}
QMenuBar::item {{ padding: 6px 10px; border-radius: 2px; font-weight: 600; }}
QMenuBar::item:selected {{ background: rgba(255,255,255,0.14); }}
QMenu {{ background: {CARD}; border: 1px solid {BORDER}; padding: 3px; }}
QMenu::item {{ padding: 7px 24px 7px 10px; border-radius: 3px; }}
QMenu::item:selected {{ background: {ACCENT_FAINT}; color: {ACCENT}; }}

QWidget#barraRapida, QFrame#filaBarraEstrecha {{
    background: {BAR}; border: none; border-bottom: 1px solid #1B3358;
}}
QWidget#barraRapida QPushButton {{
    min-height: 24px; max-height: 24px; padding: 1px 10px;
    border-radius: 3px; font-size: 12px; font-weight: 600;
    color: #F1F5F9; background: transparent; border: 1px solid #8DA0BA;
}}
QWidget#barraRapida QPushButton:hover {{
    color: white; background: #132B50; border-color: #C2CDDC;
}}
QWidget#barraRapida QPushButton#accesoPeligro {{
    color: #FF5364; border-color: #D13243; background: transparent;
}}
QWidget#barraRapida QPushButton#accesoPeligro:hover {{
    color: white; border-color: #EF4052; background: #6F1F2B;
}}
QWidget#barraRapida QPushButton#accesoExito {{
    color: #35D978; border-color: #1EB866; background: transparent;
}}
QWidget#barraRapida QPushButton#accesoExito:hover {{
    color: white; border-color: #35D978; background: #145A35;
}}
QWidget#barraRapida QPushButton:disabled {{
    color: #788397; border-color: #354158; background: transparent;
}}

QFrame#tarjeta {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 5px; }}
QFrame#barraCliente {{
    background: {CARD}; border: none; border-bottom: 1px solid {BORDER};
}}
QLabel#tituloSeccion {{ color: {ACCENT}; font-size: 11px; font-weight: 700; }}
QLabel#textoSuave {{ color: {MUTED}; font-size: 11px; }}
QLabel#cliente {{ color: {INK}; font-size: 12px; font-weight: 500; }}
QLabel#visor {{ background: {CARD}; color: {MUTED}; border: none; }}
QScrollArea#visorScroll {{ background: {CARD}; border: 1px solid {BORDER}; }}

QFrame#alerta {{ background: #FFF8E8; border: 1px solid {WARNING}; border-radius: 4px; }}
QLabel#alertaTitulo {{ color: #9A6400; font-size: 11px; font-weight: 700; }}
QLabel#alertaTexto {{ color: {INK}; font-size: 12px; }}

QPushButton {{
    background: {CARD}; color: {INK}; border: 1px solid {BORDER};
    border-radius: 3px; padding: 6px 11px; font-weight: 500;
    font-family: {FUENTE_UI}; font-size: 12px;
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT_FAINT}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ background: {SOFT}; color: #A3AAB3; border-color: #E1E6ED; }}
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
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 3px;
    padding: 6px 8px; font-family: {FUENTE_UI};
    selection-background-color: {ACCENT}; selection-color: white;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{
    background: {CARD}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT_FAINT}; selection-color: {ACCENT};
}}

QTableWidget {{
    background: {CARD}; alternate-background-color: {SOFT};
    border: 1px solid {BORDER}; border-radius: 2px; gridline-color: #E1E7EF;
    selection-background-color: {ACCENT_FAINT}; selection-color: {INK};
    font-family: {FUENTE_UI}; font-size: 11px;
}}
QHeaderView::section {{
    background: {HEAD}; color: {DIM}; border: none;
    border-right: 1px solid {BORDER}; border-bottom: 1px solid {BORDER};
    padding: 8px 6px; font-weight: 700; font-size: 10px;
}}
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
    app.setFont(QFont(familia, 9))
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
