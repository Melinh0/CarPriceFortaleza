import pytest

from app.scrapers import marketplaces, websearch
from app.scrapers.marketplaces import SCRAPERS


def _scraper(nome: str):
    return next(s for s in SCRAPERS if s.nome == nome)


def test_candidatos_de_url_comecam_no_modelo():
    filtros = {"marca": "BYD", "modelo": "Dolphin Mini"}
    esperado = {
        "Webmotors": "webmotors.com.br/carros/comprar/byd/dolphin-mini",
        "Napista": "napista.com.br/busca/byd/dolphin-mini",
        "Seminovos BH": "seminovosbh.com.br/carros/byd/dolphin-mini",
        "iCarros": "icarros.com.br/catalogo/marcas/byd/dolphin-mini",
    }
    for nome, trecho in esperado.items():
        urls = _scraper(nome).build_urls(filtros)
        assert trecho in urls[0], nome
        assert urls[-1] != urls[0], "deve ter candidato de reserva"


def test_candidatos_sem_modelo_usam_marca():
    urls = _scraper("Webmotors").build_urls({"marca": "Peugeot", "modelo": ""})
    assert "https://www.webmotors.com.br/carros/comprar/peugeot" in urls
    assert urls[0] == "https://www.webmotors.com.br/carros/comprar/peugeot"


def test_candidatos_genericos_caem_na_base():
    urls = _scraper("Napista").build_urls({"marca": "", "modelo": ""})
    assert urls == ["https://www.napista.com.br/busca"]


def test_portais_com_nome_unico_e_base_http():
    nomes = [s.nome for s in SCRAPERS]
    assert len(nomes) == len(set(nomes))
    assert len(SCRAPERS) >= 4
    for scraper in SCRAPERS:
        assert scraper.base_url.startswith("https://")


def test_motor_com_falha_entra_em_cooldown(monkeypatch):
    chamadas = {}

    def quebra(query, max_resultados, timeout):
        chamadas["quebrou"] = chamadas.get("quebrou", 0) + 1
        raise ConnectionError("rede bloqueada")

    def funciona(query, max_resultados, timeout):
        chamadas["ok"] = chamadas.get("ok", 0) + 1
        return [{"titulo": "x", "url": "http://x", "trecho": "", "preco": 10}]

    monkeypatch.setattr(websearch, "ENGINES", [quebra, funciona], raising=False)
    monkeypatch.setattr(websearch, "_motores_fora", {}, raising=False)

    primeira = websearch.buscar_na_web("carro")
    assert primeira and chamadas["ok"] == 1
    assert not websearch._motor_disponivel(quebra), "motor com erro deve esfriar"

    chamadas.clear()
    segunda = websearch.buscar_na_web("carro de novo")
    assert segunda
    assert chamadas.get("quebrou") is None, "motor em cooldown nao deve ser chamado"


def test_resultado_vazio_nao_resfria_motor(monkeypatch):
    def sem_resultado(query, max_resultados, timeout):
        return []

    def funciona(query, max_resultados, timeout):
        return [{"titulo": "y", "url": "http://y", "trecho": "", "preco": 20}]

    monkeypatch.setattr(websearch, "ENGINES", [sem_resultado, funciona], raising=False)
    monkeypatch.setattr(websearch, "_motores_fora", {}, raising=False)

    assert websearch.buscar_na_web("consulta")
    assert websearch._motor_disponivel(sem_resultado), "vazio nao e erro de rede"


def test_consultas_genericas_de_eletricos_sao_locais():
    consultas = websearch._consultas_precos(
        {"marca": "", "modelo": "", "combustivel": "Eletrico"}
    )
    assert consultas, "busca generica de eletrico deve ter consultas"
    assert any("Fortaleza" in c for c in consultas), "deve citar a cidade"
    assert any("hibrido" in c.lower() for c in websearch._consultas_precos(
        {"marca": "", "modelo": "", "combustivel": "Hibrido"}
    ))


def test_consultas_genericas_sem_eletrico_continuam_vazias():
    assert websearch._consultas_precos({"marca": "", "modelo": ""}) == []
    assert websearch._consultas_precos({"marca": "Geely", "modelo": "EX2"})


def test_portais_novos_de_busca():
    olx = _scraper("OLX")
    urls = olx.build_urls({"marca": "BYD", "modelo": "Dolphin Mini"})
    assert urls[0] == "https://www.olx.com.br/busca?q=BYD+Dolphin+Mini"
    assert olx.build_urls({"marca": "", "modelo": ""}) == ["https://www.olx.com.br/busca"]

    ml = _scraper("Mercado Livre")
    urls = ml.build_urls({"marca": "BYD", "modelo": "Dolphin Mini"})
    assert urls[0] == "https://lista.mercadolivre.com.br/byd/dolphin-mini"
    assert ml.build_urls({"marca": "", "modelo": ""}) == [
        "https://lista.mercadolivre.com.br"
    ]


def test_busca_na_web_merge_resultados_e_deduplica(monkeypatch):
    monkeypatch.setattr(websearch, "_motores_fora", {}, raising=False)
    monkeypatch.setattr(websearch, "SLEEP_ENTRE_QUERIES", 0, raising=False)

    def motor_a(query, max_resultados, timeout):
        return [
            {"titulo": "a1", "url": "http://comum", "trecho": "", "preco": None},
            {"titulo": "a2", "url": "http://a2", "trecho": "", "preco": 10},
        ]

    def motor_b(query, max_resultados, timeout):
        return [
            {"titulo": "b1", "url": "http://comum", "trecho": "", "preco": None},
            {"titulo": "b2", "url": "http://b2", "trecho": "", "preco": 20},
        ]

    monkeypatch.setattr(websearch, "ENGINES", [motor_a, motor_b], raising=False)
    resultados = websearch.buscar_na_web("query", max_resultados=8)
    urls = [r["url"] for r in resultados]
    assert urls == ["http://comum", "http://a2", "http://b2"], "mergeia e remove repetidos"


def test_padrao_tem_varios_motores():
    assert len(websearch.ENGINES) >= 5
    nomes = [e.__name__ for e in websearch.ENGINES]
    assert len(nomes) == len(set(nomes))
