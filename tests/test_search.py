import os

import pytest

from app.services import payments, search

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "data")


@pytest.fixture
def catalogo():
    return search.carregar_catalogo(DATA_DIR)


def test_ofertas_estimadas_para_modelo(catalogo):
    filtros = {"marca": "Chevrolet", "modelo": "Onix"}
    ofertas = search.ofertas_estimadas(filtros, catalogo)
    assert ofertas
    assert all(o["marca"] == "Chevrolet" and o["modelo"] == "Onix" for o in ofertas)
    assert all(o["preco"] > 0 for o in ofertas)
    assert any(o["ano"] == 2026 for o in ofertas), "deve ter oferta 0 km de referencia"


def test_filtro_por_preco_e_ano(catalogo):
    filtros = {
        "marca": "Fiat",
        "modelo": "Mobi",
        "preco_min": 40000,
        "preco_max": 60000,
        "ano_min": 2020,
        "ano_max": 2025,
    }
    ofertas = search.ofertas_estimadas(filtros, catalogo)
    filtradas = search._aplicar_filtros(ofertas, filtros)
    assert filtradas
    for oferta in filtradas:
        assert 40000 <= oferta["preco"] <= 60000
        assert 2020 <= oferta["ano"] <= 2025


def test_filtro_por_caracteristica_obrigatoria(catalogo):
    filtros = {"marca": "Toyota", "modelo": "Corolla", "caracteristicas": []}
    ofertas = search.ofertas_estimadas(filtros, catalogo)
    assert ofertas
    alvo = ofertas[1]
    if alvo.get("caracteristicas"):
        filtros["caracteristicas"] = [alvo["caracteristicas"][0]]
        filtradas = search._aplicar_filtros(ofertas, filtros)
        assert filtradas
        assert all(
            alvo["caracteristicas"][0] in o["caracteristicas"] for o in filtradas
        )


def test_ordenacao_por_preco(catalogo):
    filtros = {"marca": "Hyundai", "modelo": "HB20", "ordenar": "menor_preco"}
    ofertas = search._ordenar(search.ofertas_estimadas(filtros, catalogo), "menor_preco")
    precos = [o["preco"] for o in ofertas]
    assert precos == sorted(precos)


def test_estatisticas(catalogo):
    filtros = {"marca": "Volkswagen", "modelo": "Polo"}
    ofertas = search.ofertas_estimadas(filtros, catalogo)
    stats = search._estatisticas(ofertas)
    assert stats["total"] == len(ofertas)
    assert stats["min"] <= stats["mediana"] <= stats["max"]


def test_concessionarias_filtradas_por_marca():
    concessionarias = search.carregar_concessionarias(DATA_DIR)
    toyota = [d for d in concessionarias if "Toyota" in d["marcas"]]
    assert toyota
    for d in toyota:
        assert d["endereco"] and "Fortaleza" in d["cidade"]


def test_financiamento_preco_zero_entrada():
    resultado = payments.simulate_financing(preco=100000, entrada=100000, taxa_aa=14.9, meses=48)
    assert resultado["parcela"] == 0
    assert resultado["total_pago"] == 100000


def test_financiamento_price():
    resultado = payments.simulate_financing(preco=90000, entrada=30000, taxa_aa=12.0, meses=48)
    assert resultado["financiado"] == 60000
    assert resultado["parcela"] > 0
    assert resultado["total_pago"] == pytest.approx(30000 + resultado["parcela"] * 48)
    assert resultado["juros"] > 0


def test_financiamento_sem_juros():
    resultado = payments.simulate_financing(preco=48000, entrada=0, taxa_aa=0, meses=48)
    assert resultado["parcela"] == pytest.approx(1000)
