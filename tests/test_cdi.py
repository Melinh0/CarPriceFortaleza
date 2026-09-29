import pytest

from app.services import cdi


def test_rendimento_12_meses_100_cdi():
    resultado = cdi.calcular(valor=10000, meses=12, pct_cdi=100, cdi_aa=13.65)
    assert resultado["dias_uteis"] == 252
    assert resultado["rendimento_bruto"] == pytest.approx(1365.0, rel=1e-6)
    assert resultado["aliquota_ir"] == 20.0
    assert resultado["ir"] == pytest.approx(1365.0 * 0.20, rel=1e-6)
    assert resultado["total_final"] == pytest.approx(
        10000 + 1365 - 1365 * 0.20, rel=1e-6
    )


def test_percentual_do_cdi_escala_rendimento():
    cem = cdi.calcular(valor=5000, meses=6, pct_cdi=100, cdi_aa=10.0)
    cento_e_dez = cdi.calcular(valor=5000, meses=6, pct_cdi=110, cdi_aa=10.0)
    assert cento_e_dez["rendimento_bruto"] > cem["rendimento_bruto"]
    assert cento_e_dez["rendimento_bruto"] == pytest.approx(
        cem["rendimento_bruto"] * 1.1, rel=0.01
    )


def test_ir_regressivo_por_prazo():
    curto = cdi.calcular(valor=1000, meses=3, pct_cdi=100, cdi_aa=13.65)
    medio = cdi.calcular(valor=1000, meses=12, pct_cdi=100, cdi_aa=13.65)
    longo = cdi.calcular(valor=1000, meses=36, pct_cdi=100, cdi_aa=13.65)
    assert curto["aliquota_ir"] == 22.5
    assert medio["aliquota_ir"] == 20.0
    assert longo["aliquota_ir"] == 15.0


def test_tabela_mensal_crescente():
    resultado = cdi.calcular(valor=1000, meses=6, pct_cdi=100, cdi_aa=13.65)
    assert len(resultado["tabela"]) == 6
    brutos = [linha["bruto"] for linha in resultado["tabela"]]
    assert brutos == sorted(brutos)
    assert resultado["tabela"][-1]["bruto"] == pytest.approx(
        1000 * (1 + resultado["taxa_dia_pct"] / 100) ** 126, abs=0.01
    )


def test_validacoes_de_entrada():
    with pytest.raises(ValueError):
        cdi.calcular(valor=0, meses=12)
    with pytest.raises(ValueError):
        cdi.calcular(valor=100, meses=0)
    with pytest.raises(ValueError):
        cdi.calcular(valor=100, meses=12, pct_cdi=0)


def test_iof_sinalizado_para_prazo_curto():
    curto = cdi.calcular(valor=1000, meses=1, pct_cdi=100, cdi_aa=13.65)
    longo = cdi.calcular(valor=1000, meses=6, pct_cdi=100, cdi_aa=13.65)
    assert curto["iof_relevante"] is True
    assert longo["iof_relevante"] is False
