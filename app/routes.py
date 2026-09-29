"""Rotas do CarPrice: busca, relatorio, CDI, financiamento e concessionarias."""

from __future__ import annotations

from urllib.parse import quote

from flask import Blueprint, abort, current_app, render_template, request

from .services import cdi as cdi_service
from .services import payments
from .services import report as report_service
from .services import search as search_service

bp = Blueprint("routes", __name__)

MAPS_BUSCA = "https://www.google.com/maps/search/?api=1&query={query}"


def _num(valor: str | None) -> float | None:
    if not valor:
        return None
    texto = valor.replace("R$", "").strip()
    if not texto:
        return None
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def _parse_filtros(valores) -> dict:
    def get(chave: str) -> str:
        valor = valores.get(chave, "")
        return valor.strip() if isinstance(valor, str) else valor

    combustivel = get("combustivel")
    cambio = get("cambio")
    carroceria = get("carroceria")
    return {
        "marca": get("marca"),
        "modelo": get("modelo"),
        "preco_min": _num(get("preco_min")),
        "preco_max": _num(get("preco_max")),
        "ano_min": int(_num(get("ano_min")) or 0) or None,
        "ano_max": int(_num(get("ano_max")) or 0) or None,
        "km_max": _num(get("km_max")),
        "combustivel": combustivel if combustivel and combustivel != "Qualquer" else "",
        "cambio": cambio if cambio and cambio != "Qualquer" else "",
        "carroceria": carroceria if carroceria and carroceria != "Qualquer" else "",
        "caracteristicas": valores.getlist("caracteristicas"),
        "ordenar": get("ordenar") or "menor_preco",
    }


@bp.route("/")
def index():
    catalogo = search_service.carregar_catalogo(current_app.config["DATA_DIR"])
    return render_template("index.html", catalogo=catalogo)


@bp.route("/buscar", methods=["GET", "POST"])
def buscar():
    filtros = _parse_filtros(request.values)
    search_id, resultado = search_service.executar_busca(filtros, current_app.config)
    return render_template(
        "results.html", resultado=resultado, filtros=filtros, search_id=search_id
    )


@bp.route("/relatorio/<search_id>")
def relatorio(search_id: str):
    resultado = search_service.recuperar_busca(search_id, current_app.config)
    if not resultado:
        abort(404)
    relatorio_dados = report_service.gerar_relatorio(resultado, current_app.config)
    return render_template("report.html", rel=relatorio_dados)


@bp.route("/cdi", methods=["GET", "POST"])
def cdi():
    resultado = None
    erro = None
    valores = {"valor": "", "meses": "12", "pct": "100", "cdi": "13.65"}
    if request.method in ("GET", "POST") and (
        request.values.get("valor") or request.method == "POST"
    ):
        valor = _num(request.values.get("valor"))
        meses = _num(request.values.get("meses"))
        pct = _num(request.values.get("pct")) or 100.0
        cdi_aa = _num(request.values.get("cdi")) or 13.65
        valores = {
            "valor": request.values.get("valor", ""),
            "meses": request.values.get("meses", "12"),
            "pct": request.values.get("pct", "100"),
            "cdi": request.values.get("cdi", "13.65"),
        }
        try:
            if not valor:
                raise ValueError("Informe o valor a ser aplicado.")
            resultado = cdi_service.calcular(
                valor=valor,
                meses=int(meses or 0),
                pct_cdi=pct,
                cdi_aa=cdi_aa,
            )
        except ValueError as exc:
            erro = str(exc)
    return render_template("cdi.html", resultado=resultado, erro=erro, valores=valores)


@bp.route("/financiamento", methods=["GET", "POST"])
def financiamento():
    resultado = None
    erro = None
    valores = {"preco": "", "entrada": "", "taxa": "14.9", "meses": "48"}
    if request.values.get("preco"):
        preco = _num(request.values.get("preco"))
        entrada = _num(request.values.get("entrada")) or 0.0
        taxa = _num(request.values.get("taxa")) or 0.0
        meses = int(_num(request.values.get("meses")) or 0)
        valores = {k: request.values.get(k, "") for k in valores}
        try:
            if not preco:
                raise ValueError("Informe o preço do carro.")
            resultado = payments.simulate_financing(
                preco=preco, entrada=entrada, taxa_aa=taxa, meses=meses
            )
        except ValueError as exc:
            erro = str(exc)
    return render_template(
        "financiamento.html", resultado=resultado, erro=erro, valores=valores
    )


@bp.route("/concessionarias")
def concessionarias():
    marca = request.args.get("marca", "").strip()
    data_dir = current_app.config["DATA_DIR"]
    if marca:
        lista = report_service.concessionarias_para(marca, data_dir)
        busca_mapa = MAPS_BUSCA.format(query=quote(f"concessionaria {marca} Fortaleza CE"))
    else:
        lista = search_service.carregar_concessionarias(data_dir)
        for item in lista:
            item["maps_url"] = MAPS_BUSCA.format(
                query=quote(f"{item['nome']}, {item['endereco']}, Fortaleza - CE")
            )
            item["rota_url"] = "https://www.google.com/maps/dir/?api=1&destination=" + quote(
                f"{item['endereco']}, {item['bairro']}, Fortaleza - CE"
            )
        busca_mapa = ""
    marcas = sorted(
        {m for item in lista for m in item.get("marcas", [])}
        or {m for item in search_service.carregar_concessionarias(data_dir) for m in item["marcas"]}
    )
    return render_template(
        "concessionarias.html",
        concessionarias=lista,
        marca=marca,
        marcas=marcas,
        busca_mapa=busca_mapa,
    )
