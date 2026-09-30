import os

from werkzeug.datastructures import MultiDict

from app import create_app
from app.services import comparativo

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "data"
)
CONFIG = {"DATA_DIR": DATA_DIR, "CACHE_DIR": os.path.join(DATA_DIR, "cache")}

SELECOES_USUARIO = [
    {"marca": "BYD", "modelo": "Dolphin Mini"},
    {"marca": "Geely", "modelo": "EX2"},
    {"marca": "Volkswagen", "modelo": "Polo Track"},
    {"marca": "Volkswagen", "modelo": "Polo"},
]


def _web_falso(marca: str, modelo: str) -> dict:
    mencoes = [
        {
            "titulo": f"Oferta 0 km {marca} {modelo} ({i})",
            "url": f"https://exemplo.com/oferta{i}",
            "trecho": "preço à vista na concessionária",
            "preco": preco,
            "tipo": "preco",
            "consulta": "preco a vista",
        }
        for i, preco in enumerate((107000, 108000, 109000))
    ]
    mencoes += [
        {
            "titulo": f"Campanha {marca} {modelo}",
            "url": "https://exemplo.com/campanha",
            "trecho": "24x sem juros, taxa 0%",
            "preco": None,
            "tipo": "campanha",
            "consulta": "campanha",
        },
        {
            "titulo": f"Garantia {marca} {modelo}",
            "url": "https://exemplo.com/garantia",
            "trecho": "garantia de fábrica da montadora",
            "preco": None,
            "tipo": "garantia",
            "consulta": "garantia",
        },
    ]
    return {"consultas": ["q1"], "mencoes": mencoes}


def _sem_web(marca: str, modelo: str) -> dict:
    return {"consultas": [], "mencoes": []}


def _executar(monkeypatch, selecoes=None, **condicoes):
    monkeypatch.setattr(comparativo, "pesquisar_detalhes", _web_falso)
    return comparativo.executar_comparativo(
        selecoes or SELECOES_USUARIO, condicoes, CONFIG
    )


def test_catalogo_todos_modelos_com_preco_a_vista_e_garantia():
    import json

    with open(os.path.join(DATA_DIR, "catalog.json"), encoding="utf-8") as fh:
        catalogo = json.load(fh)
    assert len(catalogo["modelos"]) >= 115
    for item in catalogo["modelos"]:
        assert item.get("preco_a_vista_ref"), item["modelo"]
        assert item["preco_a_vista_ref"] <= item["preco_novo_ref"], item["modelo"]
        garantia = item.get("garantia") or {}
        assert garantia.get("anos", 0) >= 3, item["modelo"]
        assert garantia.get("obs"), item["modelo"]


def test_modelos_desejados_pelo_usuario_existem():
    import json

    with open(os.path.join(DATA_DIR, "catalog.json"), encoding="utf-8") as fh:
        catalogo = json.load(fh)
    por_modelo = {(m["marca"], m["modelo"]): m for m in catalogo["modelos"]}

    dolphin = por_modelo[("BYD", "Dolphin Mini")]
    assert dolphin["preco_novo_ref"] == 118990
    assert dolphin["preco_a_vista_ref"] == 109990
    assert dolphin["garantia"]["anos"] == 6
    assert dolphin["garantia"]["bateria_anos"] == 8

    ex2 = por_modelo[("Geely", "EX2")]
    assert ex2["garantia"]["anos"] == 6 and ex2["garantia"]["km"] == 150000
    assert ex2["garantia"]["bateria_km"] == 150000

    track = por_modelo[("Volkswagen", "Polo Track")]
    assert track["preco_novo_ref"] == 96690
    assert track["preco_a_vista_ref"] < track["preco_novo_ref"]
    assert por_modelo[("Volkswagen", "Polo")]["garantia"]["anos"] == 3

    marcas_vw = next(m for m in catalogo["marcas"] if m["nome"] == "Volkswagen")
    assert "Polo Track" in marcas_vw["modelos"]


def test_cenarios_matematica_correta():
    cenarios = comparativo.montar_cenarios(
        100000.0, {**comparativo.CONDICOES_PADRAO, "entrada": 20000.0}
    )
    assert cenarios["entrada"] == 20000.0
    assert cenarios["a_vista"]["total_pago"] == 100000.0
    assert cenarios["a_vista"]["juros"] == 0.0

    cj = cenarios["com_juros"]
    assert cj["financiado"] == 80000.0
    assert cj["parcela"] > 0
    assert cj["juros"] > 0
    assert cj["total_pago"] > 100000.0

    sj = cenarios["sem_juros"]
    assert sj["juros"] == 0.0
    assert sj["parcela"] == 80000.0 / 12
    assert abs(sj["total_pago"] - 100000.0) < 0.01

    co = cenarios["consorcio"]
    assert co["juros"] == 0.0
    assert abs(co["total_pago"] - 110000.0) < 0.01
    assert abs(co["parcela"] - 110000.0 / 60) < 0.01


def test_entrada_fixa_e_pct():
    fixa = comparativo.montar_cenarios(
        90000.0, {**comparativo.CONDICOES_PADRAO, "entrada": 50000.0}
    )
    assert fixa["entrada"] == 50000.0

    pct = comparativo.montar_cenarios(
        90000.0, {**comparativo.CONDICOES_PADRAO, "entrada": None, "entrada_pct": 50.0}
    )
    assert pct["entrada"] == 45000.0

    estourada = comparativo.montar_cenarios(
        90000.0, {**comparativo.CONDICOES_PADRAO, "entrada": 120000.0}
    )
    assert estourada["com_juros"]["parcela"] == 0.0
    assert estourada["sem_juros"]["parcela"] == 0.0


def test_comparativo_com_busca_web(monkeypatch):
    cmp_id, rel = _executar(monkeypatch)
    assert cmp_id and rel["carros"]
    assert len(rel["carros"]) == 4
    assert rel["fontes"][0]["ok"] is True

    dolphin = next(c for c in rel["carros"] if c["modelo"] == "Dolphin Mini")
    assert dolphin["preco_loja"] == 118990
    assert dolphin["preco_a_vista"] == 108000
    assert dolphin["origem_avista"] == "web"
    assert dolphin["economia"] > 0
    assert dolphin["mencoes_campanhas"] and dolphin["mencoes_garantia"]
    assert dolphin["garantia"]["anos"] == 6
    assert dolphin["cenarios"]["com_juros"]["juros"] > 0
    assert dolphin["cenarios"]["sem_juros"]["juros"] == 0
    assert dolphin["concessionarias"] or dolphin["maps_busca"]


def test_comparativo_sem_web_usa_base_local(monkeypatch):
    monkeypatch.setattr(comparativo, "pesquisar_detalhes", _sem_web)
    cmp_id, rel = comparativo.executar_comparativo(SELECOES_USUARIO, {}, CONFIG)
    assert rel["fontes"][0]["ok"] is False
    track = next(c for c in rel["carros"] if c["modelo"] == "Polo Track")
    assert track["preco_a_vista"] == 89990
    assert track["origem_avista"] == "base"
    assert track["ao_vivo"] is False


def test_preco_web_fora_da_faixa_nao_substitui(monkeypatch):
    def web_suspeito(marca, modelo):
        precos = [
            {"titulo": "usado barato", "url": f"https://u{i}", "trecho": "", "preco": preco,
             "tipo": "preco", "consulta": "q"}
            for i, preco in enumerate((74000, 74500, 75000, 75500))
        ]
        return {"consultas": ["q"], "mencoes": precos}

    monkeypatch.setattr(comparativo, "pesquisar_detalhes", web_suspeito)
    _, rel = comparativo.executar_comparativo(
        [{"marca": "Volkswagen", "modelo": "Polo Track"}], {}, CONFIG
    )
    track = rel["carros"][0]
    assert track["preco_a_vista"] == 89990
    assert track["origem_avista"] == "base"
    assert track["nota_web"]


def test_modelo_desconhecido_vira_erro_sem_parar_relatorio(monkeypatch):
    selecoes = SELECOES_USUARIO + [{"marca": "Marca", "modelo": "Inexistente XYZ"}]
    _, rel = _executar(monkeypatch, selecoes=selecoes)
    assert len(rel["carros"]) == 4
    assert any("não encontrado" in e["motivo"] for e in rel["erros"])


def test_rota_comparativo_formulario():
    app = create_app()
    resp = app.test_client().get("/comparativo")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Adicionar ao comparativo" in html
    assert 'name="entrada"' in html
    assert 'name="meses_sem_juros"' in html
    assert 'name="taxa_adm"' in html


def test_post_gera_relatorio_e_permanece_acessivel(monkeypatch):
    monkeypatch.setattr(comparativo, "pesquisar_detalhes", _web_falso)
    app = create_app()
    client = app.test_client()
    resp = client.post(
        "/comparativo",
        data=MultiDict([
            ("carros", "BYD|Dolphin Mini"),
            ("carros", "Geely|EX2"),
            ("carros", "Volkswagen|Polo Track"),
            ("entrada", "20000"),
            ("taxa", "14.9"),
            ("meses", "48"),
            ("meses_sem_juros", "12"),
            ("meses_consorcio", "60"),
            ("taxa_adm", "10"),
        ]),
    )
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Preços e garantia" in html
    assert "Garantia do veículo" in html
    assert "Parcelas" in html
    assert "R$ 20.000,00" in html
    assert "Dolphin Mini" in html and "Polo Track" in html
    assert "consórcio" in html.lower()

    import re

    cmp_id = re.search(r"/comparativo/([0-9a-f]{12})", html).group(1)
    comparativo._COMPARATIVOS.clear()
    resp = client.get(f"/comparativo/{cmp_id}")
    assert resp.status_code == 200
    assert "Preços e garantia" in resp.data.decode("utf-8")


def test_post_sem_carros_mostra_erro():
    app = create_app()
    resp = app.test_client().post("/comparativo", data={"entrada": "10000"})
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "pelo menos um carro" in html


def test_comparativo_id_inexistente_retorna_404():
    app = create_app()
    resp = app.test_client().get("/comparativo/naoexiste")
    assert resp.status_code == 404


def test_limite_de_carros_por_relatorio(monkeypatch):
    monkeypatch.setattr(comparativo, "pesquisar_detalhes", _sem_web)
    app = create_app()
    resp = app.test_client().post(
        "/comparativo",
        data=MultiDict([("carros", "Volkswagen|Polo")] * 7),
    )
    assert "no máximo" in resp.data.decode("utf-8")
