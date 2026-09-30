from __future__ import annotations

from urllib.parse import quote

from . import payments
from .search import carregar_catalogo, carregar_concessionarias, normalizar

ROTA_GOOGLE_MAPS = "https://www.google.com/maps/search/?api=1&query={query}"
ROTA_GOOGLE_MAPS_ROTA = "https://www.google.com/maps/dir/?api=1&destination={query}"
MAX_CONCESSIONARIAS_RELATORIO = 12


def _maps_url(endereco: str) -> str:
    return ROTA_GOOGLE_MAPS.format(query=quote(f"{endereco}, Fortaleza - CE"))


def _maps_rota_url(endereco: str) -> str:
    return ROTA_GOOGLE_MAPS_ROTA.format(query=quote(f"{endereco}, Fortaleza - CE"))


def _marca_bate(marca: str, lista: list[str]) -> bool:
    if not marca:
        return False
    for item in lista:
        alvo = normalizar(item)
        if marca == alvo or marca in alvo or alvo in marca:
            return True
    return False


def concessionarias_para(marca: str, data_dir: str) -> list[dict]:
    todos = carregar_concessionarias(data_dir)
    marca_n = normalizar(marca or "")
    if not marca_n:
        filtradas = list(todos)
    else:
        filtradas = [d for d in todos if _marca_bate(marca_n, d.get("marcas", []))]
        if not filtradas:
            filtradas = [
                d
                for d in todos
                if d.get("multimarcas") or "Multimarcas" in d.get("marcas", [])
            ]
    for d in filtradas:
        d["maps_url"] = _maps_url(f"{d['endereco']}, {d['bairro']}")
        d["rota_url"] = _maps_rota_url(f"{d['endereco']}, {d['bairro']}")
    return filtradas


def _inferir_marca_modelo(resultado: dict, ofertas: list[dict]) -> tuple[str, str]:
    filtros = resultado.get("filtros", {})
    marca = (filtros.get("marca") or "").strip()
    modelo = (filtros.get("modelo") or "").strip()
    if not marca:
        marcas = {o.get("marca") for o in ofertas if o.get("marca")}
        if len(marcas) == 1:
            marca = marcas.pop()
    if not marca and not modelo:
        return "", ""
    return marca, modelo


def _fontes_do(resultado: dict) -> list[dict]:
    status = resultado.get("fontes_status")
    if status:
        return status
    fontes = [
        {
            "nome": "Portais de anuncios",
            "ok": bool(resultado.get("consulta_portais")),
            "detalhe": f"{resultado.get('fontes_ao_vivo', 0)} anuncios ao vivo",
        },
        {
            "nome": "Pesquisa web de precos",
            "ok": bool(resultado.get("mencoes_web")),
            "detalhe": f"{len(resultado.get('mencoes_web', []))} mencoes encontradas",
        },
        {
            "nome": "Comentarios de usuarios",
            "ok": bool((resultado.get("comentarios") or {}).get("comentarios_web")),
            "detalhe": "base local + web",
        },
    ]
    return fontes


def _comparativo_marca(marca: str, catalogo: dict) -> list[dict]:
    marca_n = normalizar(marca or "")
    if not marca_n:
        return []
    itens = [
        item
        for item in catalogo.get("modelos", [])
        if normalizar(item["marca"]) == marca_n and item.get("preco_novo_ref")
    ]
    itens.sort(key=lambda i: i["preco_novo_ref"])
    return [
        {
            "modelo": item["modelo"],
            "combustivel": item["combustivel"],
            "carroceria": item["carroceria"],
            "preco_novo_ref": item["preco_novo_ref"],
            "preco_usado_ref": item["preco_usado_ref"],
        }
        for item in itens[:12]
    ]


def _histograma(ofertas: list[dict], faixas: int = 6) -> list[dict]:
    precos = [o["preco"] for o in ofertas if o.get("preco")]
    if not precos:
        return []
    menor, maior = min(precos), max(precos)
    if menor == maior:
        return [{"faixa": f"R$ {menor:,.0f}".replace(",", "."), "total": len(precos), "percentual": 100}]
    passo = (maior - menor) / faixas
    buckets = [0] * faixas
    for preco in precos:
        idx = min(int((preco - menor) / passo), faixas - 1)
        buckets[idx] += 1
    faixas_label = []
    for i, total in enumerate(buckets):
        inicio = menor + i * passo
        fim = inicio + passo
        faixas_label.append(
            {
                "faixa": f"{_brl(inicio)} - {_brl(fim)}",
                "total": total,
                "percentual": round(total / len(precos) * 100),
            }
        )
    return faixas_label


def _brl(valor: float) -> str:
    return f"R$ {valor:,.0f}".replace(",", ".")


def gerar_relatorio(resultado: dict, config: dict) -> dict:
    ofertas = resultado.get("ofertas", [])
    stats = resultado.get("estatisticas", {}) or {}
    data_dir = config["DATA_DIR"]
    catalogo = carregar_catalogo(data_dir)

    marca, modelo = _inferir_marca_modelo(resultado, ofertas)

    dealers = concessionarias_para(marca, data_dir)
    marca_tem_dealer = bool(marca) and any(
        _marca_bate(normalizar(marca), d.get("marcas", [])) for d in dealers
    )
    concessionarias_genericas = bool(marca) and bool(dealers) and not marca_tem_dealer
    dealers = dealers[:MAX_CONCESSIONARIAS_RELATORIO]

    melhor_oferta = min(
        (o for o in ofertas if o.get("preco")), key=lambda o: o["preco"], default=None
    )

    exemplo_financiamento = None
    if melhor_oferta:
        exemplo_financiamento = payments.simulate_financing(
            preco=melhor_oferta["preco"],
            entrada=melhor_oferta["preco"] * 0.3,
            taxa_aa=14.9,
            meses=48,
        )

    comentarios = resultado.get("comentarios") or {}
    comentarios.setdefault("resumo_base", {})
    comentarios.setdefault("comentarios_web", [])
    comentarios.setdefault("origem", {})

    relaxados = resultado.get("filtros_relaxados") or []
    if isinstance(relaxados, bool):
        relaxados = ["preço, ano e km"] if relaxados else []
    if not isinstance(relaxados, list):
        relaxados = [str(relaxados)]

    return {
        "id": resultado["id"],
        "filtros": resultado.get("filtros", {}),
        "filtros_relaxados": relaxados,
        "marca": marca,
        "modelo": modelo,
        "ofertas": ofertas,
        "stats": stats,
        "histograma": _histograma(ofertas),
        "mencoes_web": resultado.get("mencoes_web", []),
        "comentarios": comentarios,
        "concessionarias": dealers,
        "concessionarias_genericas": concessionarias_genericas,
        "comparativo": _comparativo_marca(marca, catalogo),
        "fontes": _fontes_do(resultado),
        "erros": resultado.get("erros", []),
        "maps_busca_marca": ROTA_GOOGLE_MAPS.format(
            query=quote(f"concessionaria {marca} Fortaleza CE")
        )
        if marca
        else ROTA_GOOGLE_MAPS.format(query=quote("concessionaria carro Fortaleza CE")),
        "metodos": payments.METODOS,
        "guia": payments.GUIA_COMPRA,
        "dicas": payments.DICAS_NEGOCIACAO,
        "melhor_oferta": melhor_oferta,
        "exemplo_financiamento": exemplo_financiamento,
        "fontes_ao_vivo": resultado.get("fontes_ao_vivo", 0),
        "gerado_em": resultado.get("ts", 0),
    }
