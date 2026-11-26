import os
import config


def test_cargar_env_no_pisa_y_no_expone_valores(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# comentario\nSIG_PRUEBA_A=valor_a\nSIG_PRUEBA_B='b'\nYA_DEFINIDA=nuevo\n", encoding="utf-8")
    monkeypatch.setenv("YA_DEFINIDA", "original")
    monkeypatch.delenv("SIG_PRUEBA_A", raising=False)
    monkeypatch.delenv("SIG_PRUEBA_B", raising=False)
    cargadas = config.cargar_env(f, forzar=True)
    assert cargadas == ["SIG_PRUEBA_A", "SIG_PRUEBA_B"]   # solo nombres, nunca valores
    assert os.environ["SIG_PRUEBA_A"] == "valor_a" and os.environ["SIG_PRUEBA_B"] == "b"
    assert os.environ["YA_DEFINIDA"] == "original"         # el entorno real tiene prioridad


def test_cargar_env_no_actua_en_pytest(tmp_path):
    f = tmp_path / ".env"
    f.write_text("SIG_PRUEBA_C=x\n", encoding="utf-8")
    assert config.cargar_env(f) == []
