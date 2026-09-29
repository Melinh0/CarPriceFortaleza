import os
import time

from app import create_app
from app.services import report, search

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "data"
)
CONFIG = {"DATA_DIR": DATA_DIR, "CACHE_DIR": os.path.join(DATA_DIR, "cache")}


def _resultado_base(**extras) -> dict:
    filtros = {"marca": "Peugeot", "modelo": "208"}
    ofertas = search.ofertas_estimadas(
        filtros, search.carregar_catalogo(DATA_DIR)
    )
    resultado = {
        "id": "teste00000000",
        "ts": time.time(),
        "filtros": filtros,
        "filtros_relaxados": [],
        "ofertas": ofertas,
        "estatisticas": search._estatisticas(ofertas),
        "mencoes_web": [],
        "comentarios": {
            "resumo_base": {"pontos_positivos": ["ok"], "pontos_negativos": [], "sobre_preco": []},
            "comentarios_web": [],
            "origem": {"base_local": "base"},
        },
        "fontes_ao_vivo": 0,
        "consulta_portais": False,
        "fontes_status": [
            {"nome": "Portais de anuncios", "ok": False, "detalhe": "nenhum"},
            {"nome": "Pesquisa web de precos", "ok": False, "detalhe": "nenhuma"},
            {"nome": "Comentarios de usuarios", "ok": True, "detalhe": "base local"},
        ],
        "erros": [{"fonte": "portais", "motivo": "bloqueio"}],
    }
    resultado.update(extras)
    return resultado


def test_relatorio_completo_com_todas_as_secoes():
    rel = report.gerar_relatorio(_resultado_base(), CONFIG)
    assert rel["ofertas"]
    assert rel["histograma"]
    assert rel["stats"]["total"] == len(rel["ofertas"])
    assert rel["melhor_oferta"] is not None
    assert rel["exemplo_financiamento"] is not None
    assert len(rel["fontes"]) == 3
    assert rel["concessionarias"], "relatorio deve indicar concessionarias"
    assert rel["comparativo"], "relatorio deve trazer comparativo da marca"
    assert rel["metodos"] and rel["guia"] and rel["dicas"]
    assert rel["comentarios"]["resumo_base"]
    assert rel["erros"]


def test_relatorio_renderiza_no_template():
    app = create_app()
    resultado = _resultado_base()
    search._SEARCHES[resultado["id"]] = resultado
    client = app.test_client()
    resp = client.get(f"/relatorio/{resultado['id']}")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Fontes consultadas" in html
    assert "Comparativo da marca" in html
    assert "Ofertas e pre" in html
    assert "Como comprar o carro" in html
    assert "concession" in html


def test_relatorio_sem_marca_lista_concessionarias_genericas():
    resultado = _resultado_base(filtros={"marca": "", "modelo": ""})
    rel = report.gerar_relatorio(resultado, CONFIG)
    assert rel["concessionarias"], "busca generica deve listar lojas"

    resultado = _resultado_base(filtros={"marca": "Marca Inexistente", "modelo": ""})
    rel = report.gerar_relatorio(resultado, CONFIG)
    assert rel["concessionarias"], "marca desconhecida deve listar alternativas"
    assert rel["concessionarias_genericas"] is True


def test_concessionarias_fallback_para_marca_desconhecida():
    genericas = report.concessionarias_para("Marca Inexistente XYZ", DATA_DIR)
    assert genericas, "marca sem cadastro deve cair em lojas multimarcas"
    assert all(d.get("multimarcas") for d in genericas)


def test_concessionarias_por_marca_com_acento():
    citroen = report.concessionarias_para("Citroen", DATA_DIR)
    assert citroen
    assert any("Citroën" in d["marcas"] for d in citroen)


def test_todas_marcas_do_catalogo_tem_concessionaria():
    catalogo = search.carregar_catalogo(DATA_DIR)
    for marca_info in catalogo["marcas"]:
        marca = marca_info["nome"]
        lista = report.concessionarias_para(marca, DATA_DIR)
        assert lista, f"{marca} sem nenhuma alternativa de loja"
        exatas = [
            d for d in lista if report._marca_bate(search.normalizar(marca), d["marcas"])
        ]
        assert exatas, f"{marca} sem concessionaria exata no cadastro"


def test_eletricos_economicos_no_catalogo():
    catalogo = search.carregar_catalogo(DATA_DIR)
    eletricos = [
        m for m in catalogo["modelos"] if m["combustivel"] == "Eletrico"
    ]
    assert len(eletricos) >= 5, "catalogo deve ter varios eletricos"
    economicos = [m for m in eletricos if m["preco_novo_ref"] <= 150000]
    assert economicos, "deve haver eletricos com preco de entrada"


def test_filtro_impossivel_relaxa_em_vez_de_zerar():
    catalogo = search.carregar_catalogo(DATA_DIR)
    ofertas = search.ofertas_estimadas({}, catalogo)
    impossivel = {"preco_max": 1000, "marca": "", "modelo": ""}
    atuais = search._aplicar_filtros(ofertas, impossivel)
    assert atuais == []
    relaxadas, rotulos = search._filtrar_sem_vazio(ofertas, impossivel)
    assert relaxadas
    assert "preço" in rotulos


def test_estatisticas_sempre_com_chaves_completas():
    stats = search._estatisticas([])
    for chave in ("total", "min", "max", "media", "mediana", "desvio", "ao_vivo"):
        assert chave in stats
    assert stats["min"] is None


def test_modelo_aproximado_por_erro_de_digitacao():
    catalogo = search.carregar_catalogo(DATA_DIR)
    selecionados = search._modelos_selecionados({"marca": "Volkswager"}, catalogo)
    assert selecionados
    assert all(m["marca"] == "Volkswagen" for m in selecionados)


def test_geely_no_catalogo_com_eletricos_e_loja():
    catalogo = search.carregar_catalogo(DATA_DIR)
    geely = [m for m in catalogo["modelos"] if m["marca"] == "Geely"]
    assert {m["modelo"] for m in geely} >= {
        "EX2", "EX2 Max", "EX5", "EX5 Max",
        "EX5 EM-i", "EX5 EM-i Max", "EX5 EM-i Ultra",
    }
    assert all(m["combustivel"] in ("Eletrico", "Hibrido") for m in geely)
    assert any(m["preco_novo_ref"] <= 130000 for m in geely), "EX2 e de entrada"

    lojas = report.concessionarias_para("Geely", DATA_DIR)
    assert any("Jangada Geely" in d["nome"] for d in lojas)
    jangada = next(d for d in lojas if "Jangada Geely" in d["nome"])
    assert jangada["telefone"] and "Fortaleza" in jangada["cidade"]
