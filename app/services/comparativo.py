from __future__ import annotations

import json
import os
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
from urllib.parse import quote

from ..scrapers.websearch import pesquisar_detalhes
from . import payments
from .report import ROTA_GOOGLE_MAPS, concessionarias_para
from .search import _modelos_selecionados, carregar_catalogo, normalizar

COMPARATIVO_TTL = 2 * 60 * 60
COMPARATIVO_TIMEOUT = 75
COMPARATIVO_GRACIA = 15
MAX_CARROS = 6
MAX_CONCESSIONARIAS_POR_CARRO = 4
FAIXA_PRECO_0KM = (0.75, 1.10)
FAIXA_CONFIANCA_WEB = (0.85, 1.02)
MINIMOS_PRECOS_WEB = 3

CONDICOES_PADRAO = {
    "entrada": None,
    "entrada_pct": 30.0,
    "taxa_aa": 14.9,
    "meses": 48,
    "meses_sem_juros": 12,
    "meses_consorcio": 60,
    "taxa_adm": 10.0,
}

_COMPARATIVOS: dict[str, dict] = {}


def resolver_modelo(selecao: dict, catalogo: dict) -> dict | None:
    encontrados = _modelos_selecionados(selecao, catalogo)
    if not encontrados:
        return None
    modelo_n = normalizar(selecao.get("modelo") or "")
    if len(encontrados) > 1 and modelo_n:
        exatos = [m for m in encontrados if normalizar(m["modelo"]) == modelo_n]
        if exatos:
            return exatos[0]
    return encontrados[0]


def _entrada_para(preco: float, cond: dict) -> float:
    if cond.get("entrada") is not None:
        return min(float(cond["entrada"]), preco)
    return round(preco * float(cond.get("entrada_pct") or 0) / 100, 2)


def montar_cenarios(preco: float, cond: dict) -> dict:
    entrada = _entrada_para(preco, cond)
    meses = int(cond.get("meses") or 0)
    meses_sem_juros = int(cond.get("meses_sem_juros") or 0)
    meses_consorcio = int(cond.get("meses_consorcio") or 0)
    taxa_adm = float(cond.get("taxa_adm") or 0)

    com_juros = payments.simulate_financing(
        preco=preco, entrada=entrada, taxa_aa=float(cond.get("taxa_aa") or 0), meses=meses
    )

    financiado = max(preco - entrada, 0.0)
    parcela_sem_juros = financiado / meses_sem_juros if meses_sem_juros > 0 else 0.0
    sem_juros = {
        "entrada": entrada,
        "financiado": financiado,
        "meses": meses_sem_juros,
        "parcela": parcela_sem_juros,
        "total_pago": entrada + parcela_sem_juros * meses_sem_juros,
        "juros": 0.0,
    }

    adm_total = preco * taxa_adm / 100
    total_consorcio = preco + adm_total
    parcela_consorcio = total_consorcio / meses_consorcio if meses_consorcio > 0 else 0.0
    consorcio = {
        "carta_credito": preco,
        "taxa_adm_pct": taxa_adm,
        "adm_total": adm_total,
        "meses": meses_consorcio,
        "parcela": parcela_consorcio,
        "total_pago": total_consorcio,
        "juros": 0.0,
    }

    a_vista = {
        "entrada": preco,
        "financiado": 0.0,
        "meses": 0,
        "parcela": 0.0,
        "total_pago": preco,
        "juros": 0.0,
    }

    return {
        "entrada": entrada,
        "entrada_pct": (entrada / preco * 100) if preco else 0.0,
        "a_vista": a_vista,
        "com_juros": com_juros,
        "sem_juros": sem_juros,
        "consorcio": consorcio,
    }


def _precos_plausiveis(mencoes: list[dict], preco_loja: float) -> list[float]:
    if not preco_loja:
        return []
    inferior, superior = FAIXA_PRECO_0KM[0] * preco_loja, FAIXA_PRECO_0KM[1] * preco_loja
    return sorted(
        {
            float(m["preco"])
            for m in mencoes
            if m.get("tipo") == "preco"
            and m.get("preco")
            and inferior <= float(m["preco"]) <= superior
        }
    )


def _definir_preco_avista(preco_base: float, precos_web: list[float]) -> tuple[float, str, str | None]:
    if len(precos_web) < MINIMOS_PRECOS_WEB:
        return preco_base, "base", None

    mediana = statistics.median(precos_web)
    faixa = FAIXA_CONFIANCA_WEB
    if mediana < preco_base and faixa[0] * preco_base <= mediana <= faixa[1] * preco_base:
        return mediana, "web", None
    if mediana < faixa[0] * preco_base:
        return preco_base, "base", (
            "A web traz valores muito abaixo da referência (provavelmente usados ou outras "
            "versões); manteve-se a estimativa local de 0 km."
        )
    return preco_base, "base", (
        "A mediana dos preços encontrados na web está acima da estimativa local; usou-se o "
        "menor valor entre os dois."
    )


def montar_ficha(item: dict, cond: dict, resultado_web: dict | None, data_dir: str) -> dict:
    preco_loja = float(item["preco_novo_ref"])
    preco_base = float(item.get("preco_a_vista_ref") or preco_loja)
    mencoes = (resultado_web or {}).get("mencoes", [])
    precos_web = _precos_plausiveis(mencoes, preco_loja)
    preco_avista, origem, nota_web = _definir_preco_avista(preco_base, precos_web)

    garantia = dict(item.get("garantia") or {})

    return {
        "marca": item["marca"],
        "modelo": item["modelo"],
        "titulo": f"{item['marca']} {item['modelo']} 0 km — {item['motor']} {item['cambio']}",
        "carroceria": item["carroceria"],
        "combustivel": item["combustivel"],
        "cambio": item["cambio"],
        "motor": item["motor"],
        "preco_loja": preco_loja,
        "preco_a_vista": preco_avista,
        "preco_a_vista_base": preco_base,
        "preco_a_vista_web": statistics.median(precos_web) if len(precos_web) >= MINIMOS_PRECOS_WEB else None,
        "origem_avista": origem,
        "nota_a_vista": item.get("nota_a_vista", ""),
        "nota_web": nota_web,
        "precos_web": precos_web,
        "economia": preco_loja - preco_avista,
        "economia_pct": ((preco_loja - preco_avista) / preco_loja * 100) if preco_loja else 0.0,
        "garantia": garantia,
        "mencoes_precos": [m for m in mencoes if m.get("tipo") == "preco"],
        "mencoes_campanhas": [m for m in mencoes if m.get("tipo") == "campanha"],
        "mencoes_garantia": [m for m in mencoes if m.get("tipo") == "garantia"],
        "cenarios": montar_cenarios(preco_avista, cond),
        "concessionarias": concessionarias_para(item["marca"], data_dir)[:MAX_CONCESSIONARIAS_POR_CARRO],
        "maps_busca": ROTA_GOOGLE_MAPS.format(
            query=quote(f"concessionaria {item['marca']} Fortaleza CE")
        ),
        "ao_vivo": bool(mencoes),
    }


def _buscar_detalhes_em_paralelo(itens: list[dict], erros: list[dict]) -> dict[str, dict]:
    web: dict[str, dict] = {}
    if not itens:
        return web

    pool = ThreadPoolExecutor(max_workers=min(4, len(itens)))
    futuros = {
        pool.submit(pesquisar_detalhes, item["marca"], item["modelo"]): item for item in itens
    }
    concluidos, pendentes = futures_wait(set(futuros), timeout=COMPARATIVO_TIMEOUT)
    if pendentes:
        extras, pendentes = futures_wait(pendentes, timeout=COMPARATIVO_GRACIA)
        concluidos = set(concluidos) | set(extras)

    for futuro in concluidos:
        item = futuros[futuro]
        chave = f"{item['marca']}|{item['modelo']}"
        try:
            web[chave] = futuro.result() or {"consultas": [], "mencoes": []}
        except Exception as exc:
            web[chave] = {"consultas": [], "mencoes": []}
            erros.append({"fonte": chave, "motivo": str(exc)})
    for futuro in pendentes:
        item = futuros[futuro]
        chave = f"{item['marca']}|{item['modelo']}"
        web[chave] = {"consultas": [], "mencoes": []}
        erros.append({"fonte": chave, "motivo": "tempo esgotado"})
    pool.shutdown(wait=False, cancel_futures=True)
    return web


def executar_comparativo(
    selecoes: list[dict], condicoes: dict, config: dict
) -> tuple[str, dict]:
    data_dir = config["DATA_DIR"]
    catalogo = carregar_catalogo(data_dir)
    cond = {k: v for k, v in CONDICOES_PADRAO.items()}
    for chave, valor in (condicoes or {}).items():
        if valor is not None:
            cond[chave] = valor

    erros: list[dict] = []
    itens: list[dict] = []
    for selecao in selecoes[:MAX_CARROS]:
        item = resolver_modelo(selecao, catalogo)
        if item is None:
            erros.append(
                {
                    "fonte": "catalogo",
                    "motivo": f"modelo não encontrado: {selecao.get('marca', '')} {selecao.get('modelo', '')}".strip(),
                }
            )
        else:
            itens.append(item)

    web = _buscar_detalhes_em_paralelo(itens, erros)

    carros = [
        montar_ficha(item, cond, web.get(f"{item['marca']}|{item['modelo']}"), data_dir)
        for item in itens
    ]

    total_mencoes = sum(
        len(c["mencoes_precos"]) + len(c["mencoes_campanhas"]) + len(c["mencoes_garantia"])
        for c in carros
    )
    resultado = {
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "gerado_em": time.strftime("%d/%m/%Y às %H:%M"),
        "condicoes": cond,
        "selecoes": selecoes,
        "carros": carros,
        "erros": erros,
        "fontes": [
            {
                "nome": "Busca web (preços à vista, campanhas e garantia)",
                "ok": any(c["ao_vivo"] for c in carros),
                "detalhe": f"{total_mencoes} menções encontradas"
                if total_mencoes
                else "buscador indisponível agora — usando base local",
            },
            {
                "nome": "Base local (tabela, estimativa à vista e garantia)",
                "ok": True,
                "detalhe": f"{len(carros)} modelo(s) com dados de referência",
            },
        ],
        "metodos": payments.METODOS,
        "dicas": payments.DICAS_NEGOCIACAO,
    }

    _salvar(resultado, config)
    _COMPARATIVOS[resultado["id"]] = resultado
    return resultado["id"], resultado


def recuperar_comparativo(cmp_id: str, config: dict) -> dict | None:
    if cmp_id in _COMPARATIVOS:
        resultado = _COMPARATIVOS[cmp_id]
        if time.time() - resultado["ts"] <= COMPARATIVO_TTL:
            return resultado
    path = os.path.join(config["CACHE_DIR"], "comparativos", f"{cmp_id}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def _salvar(resultado: dict, config: dict) -> None:
    pasta = os.path.join(config["CACHE_DIR"], "comparativos")
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, f"{resultado['id']}.json"), "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False)
