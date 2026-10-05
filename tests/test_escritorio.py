"""El Escritorio que se ve, también con OneDrive (1.23)."""

import os
import sys
import types

from facturas_excel import archivo, escaner, rutas


def _windows_con_escritorio(monkeypatch, valor):
    """Simula Windows y lo que dice su registro de dónde está el Escritorio."""
    class Clave:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    winreg = types.SimpleNamespace(
        HKEY_CURRENT_USER=0, OpenKey=lambda *_a: Clave(),
        QueryValueEx=lambda _clave, _nombre: (valor, 2))
    monkeypatch.setitem(sys.modules, "winreg", winreg)
    monkeypatch.setattr(rutas.sys, "platform", "win32")


def test_con_onedrive_el_excel_va_al_escritorio_que_se_ve(tmp_path, monkeypatch):
    casa = tmp_path / "casa"
    onedrive = casa / "OneDrive" / "Escritorio"
    onedrive.mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(casa))
    monkeypatch.setenv("HOME", str(casa))
    _windows_con_escritorio(monkeypatch, "%USERPROFILE%" + os.sep
                            + os.path.join("OneDrive", "Escritorio"))

    assert rutas.escritorio() == str(onedrive)
    ruta = archivo.ruta_excel_consolidado("CLIENTE", 2026, "gastos")
    assert os.path.dirname(ruta) == str(onedrive)
    assert escaner.carpeta_por_defecto() == str(onedrive / "Documentación Facturas")


def test_el_archivo_que_ya_existia_no_se_cambia_de_sitio(tmp_path, monkeypatch):
    casa = tmp_path / "casa"
    antigua = casa / "Desktop" / "Documentación Facturas"
    antigua.mkdir(parents=True)
    (casa / "OneDrive" / "Escritorio").mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(casa))
    monkeypatch.setenv("HOME", str(casa))
    _windows_con_escritorio(monkeypatch, str(casa / "OneDrive" / "Escritorio"))

    assert escaner.carpeta_por_defecto() == str(antigua)


def test_un_escritorio_fuera_de_la_carpeta_del_usuario_no_se_usa(
        tmp_path, monkeypatch):
    """Una carpeta de red, o el perfil real en las pruebas: el de siempre."""
    casa = tmp_path / "casa"
    fuera = tmp_path / "servidor" / "Desktop"
    fuera.mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(casa))
    monkeypatch.setenv("HOME", str(casa))
    _windows_con_escritorio(monkeypatch, str(fuera))
    assert rutas.escritorio() == os.path.join(str(casa), "Desktop")


def test_sin_registro_el_escritorio_de_siempre(tmp_path, monkeypatch):
    casa = tmp_path / "casa"
    monkeypatch.setenv("USERPROFILE", str(casa))
    monkeypatch.setenv("HOME", str(casa))
    monkeypatch.setattr(rutas.sys, "platform", "linux")
    assert rutas.escritorio() == os.path.join(str(casa), "Desktop")
