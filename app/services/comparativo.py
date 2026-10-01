from __future__ import annotations

import json
import os
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
from urllib.parse import quote

from ..scrapers.websearch import _tipo_mencao, pesquisar_detalhes, pesquisar_precos
from . import payments
from .report import ROTA_GOOGLE_MAPS, concessionarias_para
from .search import _modelos_selecionados, carregar_catalogo, normalizar

COMPARATIVO_TTL = 2 * 60 * 60
COMPARATIVO_TIMEOUT = 75
COMPARATIVO_GRACIA = 15
MAX_CARROS = 8
MAX_CONCESSIONARIAS_POR_CARRO = 4
FAIXA_PRECO_0KM = (0.75, 1.10)
FAIXA_PRECO_USADO = (0.72, 1.12)
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
    "cambio": "",
}


def normalizar_condicao(valor: str) -> str:
    chave = normalizar(valor or "")
    if chave.startswith("semin") or chave in ("usado", "usada", "ocasiao"):
        return "seminovo"
    return "novo"


def normalizar_cambio(valor: str) -> str:
    chave = normalizar(valor or "")
    if not chave or chave in ("qualquer", "todas", "todos", "nenhum"):
        return ""
    for opcao in ("Manual", "Automatico", "CVT", "Robotizado"):
        if normalizar(opcao) == chave:
            return opcao
    return (valor or "").strip()


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


def _precos_plausiveis(
    mencoes: list[dict], preco_loja: float, faixa: tuple[float, float] | None = None
) -> list[float]:
    if not preco_loja:
        return []
    inferior, superior = (faixa or FAIXA_PRECO_0KM)[0] * preco_loja, (
        faixa or FAIXA_PRECO_0KM
    )[1] * preco_loja
    return sorted(
        {
            float(m["preco"])
            for m in mencoes
            if m.get("tipo") == "preco"
            and m.get("preco")
            and inferior <= float(m["preco"]) <= superior
        }
    )


def _definir_preco_avista(
    preco_base: float, precos_web: list[float], contexto: str = "0 km"
) -> tuple[float, str, str | None]:
    if len(precos_web) < MINIMOS_PRECOS_WEB:
        return preco_base, "base", None

    mediana = statistics.median(precos_web)
    faixa = FAIXA_CONFIANCA_WEB
    if mediana < preco_base and faixa[0] * preco_base <= mediana <= faixa[1] * preco_base:
        return mediana, "web", None
    if mediana < faixa[0] * preco_base:
        return preco_base, "base", (
            f"A web traz valores muito baixos para {contexto} (provavelmente outras "
            "versões); manteve-se a estimativa local da base."
        )
    return preco_base, "base", (
        "A mediana dos preços encontrados na web está acima da estimativa local; usou-se o "
        "menor valor entre os dois."
    )


GARANTIA_SEMINOVO = {
    "anos": 1,
    "km": None,
    "rotulo": "90 dias da loja + remanescente de fábrica",
    "obs": (
        "Garantia da loja: 90 dias contra vícios ocultos (Código de Defesa do Consumidor) "
        "e, quando houver, o remanescente de garantia de fábrica — peça a cobertura, a "
        "quilometragem e a assistência por escrito no contrato."
    ),
}


def montar_ficha(
    item: dict,
    cond: dict,
    resultado_web: dict | None,
    data_dir: str,
    condicao: str = "novo",
) -> dict:
    seminovo = condicao == "seminovo"
    preco_loja = float(item["preco_usado_ref"] if seminovo else item["preco_novo_ref"])
    preco_base = float(
        preco_loja if seminovo else (item.get("preco_a_vista_ref") or preco_loja)
    )
    mencoes = (resultado_web or {}).get("mencoes", [])
    precos_web = _precos_plausiveis(
        mencoes, preco_loja, FAIXA_PRECO_USADO if seminovo else FAIXA_PRECO_0KM
    )
    contexto = "seminovo" if seminovo else "0 km"
    preco_avista, origem, nota_web = _definir_preco_avista(
        preco_base, precos_web, contexto
    )

    garantia = dict(GARANTIA_SEMINOVO) if seminovo else dict(item.get("garantia") or {})
    titulo = f"{item['marca']} {item['modelo']} — {item['motor']} {item['cambio']}"
    if seminovo:
        titulo += " (seminovo)"
    else:
        titulo = f"{item['marca']} {item['modelo']} 0 km — {item['motor']} {item['cambio']}"

    return {
        "marca": item["marca"],
        "modelo": item["modelo"],
        "condicao": condicao,
        "titulo": titulo,
        "carroceria": item["carroceria"],
        "combustivel": item["combustivel"],
        "cambio": item["cambio"],
        "motor": item["motor"],
        "tipo_motor": item.get("tipo_motor", ""),
        "consumo_km_l": item.get("consumo_km_l") or None,
        "autonomia_km": item.get("autonomia_km") or None,
        "bateria_kwh": item.get("bateria_kwh") or None,
        "preco_loja": preco_loja,
        "preco_a_vista": preco_avista,
        "preco_a_vista_base": preco_base,
        "preco_a_vista_web": statistics.median(precos_web) if len(precos_web) >= MINIMOS_PRECOS_WEB else None,
        "origem_avista": origem,
        "nota_a_vista": item.get("nota_a_vista", "") if not seminovo else "",
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


def _buscar_web_em_paralelo(
    pares: list[tuple[dict, str]], erros: list[dict]
) -> dict[str, dict]:
    web: dict[str, dict] = {}
    if not pares:
        return web

    pool = ThreadPoolExecutor(max_workers=min(4, len(pares)))
    futuros: dict = {}
    for item, condicao in pares:
        chave = f"{item['marca']}|{item['modelo']}"
        futuros[pool.submit(pesquisar_detalhes, item["marca"], item["modelo"])] = (
            chave,
            "detalhes",
        )
        if condicao == "seminovo":
            futuros[
                pool.submit(
                    pesquisar_precos,
                    {"marca": item["marca"], "modelo": item["modelo"], "condicao": "seminovo"},
                )
            ] = (chave, "precos")

    concluidos, pendentes = futures_wait(set(futuros), timeout=COMPARATIVO_TIMEOUT)
    if pendentes:
        extras, pendentes = futures_wait(pendentes, timeout=COMPARATIVO_GRACIA)
        concluidos = set(concluidos) | set(extras)

    def _guardar(chave: str, tipo: str, resultado: dict) -> None:
        entrada = web.setdefault(chave, {"consultas": [], "mencoes": []})
        entrada["consultas"].extend(
            q for q in resultado.get("consultas", []) if q not in entrada["consultas"]
        )
        vistos = {m.get("url") for m in entrada["mencoes"]}
        for mencao in resultado.get("mencoes", []):
            if mencao.get("url") in vistos:
                continue
            vistos.add(mencao.get("url"))
            entrada["mencoes"].append(mencao)

    for futuro in concluidos:
        chave, tipo = futuros[futuro]
        try:
            resultado = futuro.result() or {"consultas": [], "mencoes": []}
        except Exception as exc:
            resultado = {"consultas": [], "mencoes": []}
            erros.append({"fonte": chave, "motivo": str(exc)})
        _guardar(chave, tipo, resultado)
    for futuro in pendentes:
        chave, tipo = futuros[futuro]
        web.setdefault(chave, {"consultas": [], "mencoes": []})
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
    cond["cambio"] = normalizar_cambio(cond.get("cambio") or "")

    erros: list[dict] = []
    itens: list[tuple[dict, str]] = []
    selecoes_norm: list[dict] = []
    for selecao in selecoes[:MAX_CARROS]:
        marca = (selecao.get("marca") or "").strip()
        modelo = (selecao.get("modelo") or "").strip()
        condicao = normalizar_condicao(selecao.get("condicao") or "")
        selecoes_norm.append({"marca": marca, "modelo": modelo, "condicao": condicao})
        item = resolver_modelo(selecao, catalogo)
        if item is None:
            erros.append(
                {
                    "fonte": "catalogo",
                    "motivo": f"modelo não encontrado: {selecao.get('marca', '')} {selecao.get('modelo', '')}".strip(),
                }
            )
            continue
        cambio_filtro = cond["cambio"]
        if cambio_filtro and normalizar(item["cambio"]) != normalizar(cambio_filtro):
            erros.append(
                {
                    "fonte": f"{item['marca']} {item['modelo']}",
                    "motivo": f"não há versão com câmbio {cambio_filtro} para este modelo "
                    f"(o catálogo traz {item['cambio']})",
                }
            )
            continue
        itens.append((item, condicao))

    web = _buscar_web_em_paralelo(itens, erros)

    carros = [
        montar_ficha(
            item,
            cond,
            web.get(f"{item['marca']}|{item['modelo']}"),
            data_dir,
            condicao,
        )
        for item, condicao in itens
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
        "selecoes": selecoes_norm,
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
