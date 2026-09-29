"""Orquestra a busca: scrapers ao vivo, base local, web e comentarios."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import random
import statistics
import time
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait

from ..scrapers.base import configure_cache
from ..scrapers.marketplaces import buscar_em_portais
from ..scrapers.opinions import coletar_comentarios
from ..scrapers.websearch import pesquisar_precos

SEARCH_TTL = 2 * 60 * 60
BUSCA_TIMEOUT = 75
BUSCA_GRACIA = 15
_SEARCHES: dict[str, dict] = {}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower().strip()


def carregar_catalogo(data_dir: str) -> dict:
    with open(os.path.join(data_dir, "catalog.json"), encoding="utf-8") as fh:
        return json.load(fh)


def carregar_concessionarias(data_dir: str) -> list[dict]:
    with open(os.path.join(data_dir, "dealers.json"), encoding="utf-8") as fh:
        return json.load(fh)["concessionarias"]


def _aproximar(alvo: str, opcoes: list[str]) -> str:
    """Aproxima um nome digitado pelo usuario pelo nome real do catalogo."""
    if not alvo or alvo in opcoes:
        return alvo
    proximo = difflib.get_close_matches(alvo, sorted(opcoes), n=1, cutoff=0.65)
    if proximo:
        return proximo[0]
    contidos = [o for o in opcoes if alvo in o or o in alvo]
    return contidos[0] if contidos else alvo


def _modelos_selecionados(filtros: dict, catalogo: dict) -> list[dict]:
    marca = normalizar(filtros.get("marca") or "")
    modelo = normalizar(filtros.get("modelo") or "")
    if not marca and not modelo:
        return catalogo["modelos"]

    exatos = [
        item
        for item in catalogo["modelos"]
        if (not marca or normalizar(item["marca"]) == marca)
        and (not modelo or normalizar(item["modelo"]) == modelo)
    ]
    if exatos:
        return exatos

    # acentos, erro de digitacao ou trecho em comum
    marcas_cat = sorted({normalizar(i["marca"]) for i in catalogo["modelos"]})
    marca = _aproximar(marca, marcas_cat) if marca else marca
    modelos_cat = sorted(
        {
            normalizar(i["modelo"])
            for i in catalogo["modelos"]
            if not marca or normalizar(i["marca"]) == marca
        }
    )
    modelo = _aproximar(modelo, modelos_cat) if modelo else modelo

    flexiveis = [
        item
        for item in catalogo["modelos"]
        if (not marca or normalizar(item["marca"]) == marca)
        and (not modelo or normalizar(item["modelo"]) == modelo)
    ]
    if flexiveis:
        return flexiveis

    # modelo nao pertence a marca escolhida: prioriza o modelo
    if modelo:
        por_modelo = [
            item for item in catalogo["modelos"] if normalizar(item["modelo"]) == modelo
        ]
        if por_modelo:
            return por_modelo

    # ultimo recurso: qualquer item da marca (evita relatorio sem ofertas)
    if marca and not modelo:
        return [
            item
            for item in catalogo["modelos"]
            if normalizar(item["marca"]) == marca
        ]
    return []


def ofertas_estimadas(filtros: dict, catalogo: dict) -> list[dict]:
    """Ofertas de referencia geradas da base local (rotuladas como estimativa)."""
    modelos = _modelos_selecionados(filtros, catalogo)
    caracteristicas_pool = catalogo["caracteristicas"]
    vendedores = ["Concessionaria autorizada", "Multimarcas", "Particular"]
    cidades = ["Fortaleza - CE"] * 8 + ["Maracanau - CE", "Caucaia - CE"]

    ofertas: list[dict] = []
    for item in modelos:
        seed = int(hashlib.md5(
            f"{item['marca']}|{item['modelo']}|{filtros}".encode()
        ).hexdigest()[:8], 16)
        rng = random.Random(seed)

        ofertas.append(
            {
                "titulo": f"{item['marca']} {item['modelo']} 0 km - {item['motor']} {item['cambio']}",
                "marca": item["marca"],
                "modelo": item["modelo"],
                "preco": item["preco_novo_ref"],
                "ano": 2026,
                "km": 0,
                "combustivel": item["combustivel"],
                "cambio": item["cambio"],
                "carroceria": item["carroceria"],
                "vendedor": "Concessionaria autorizada (0 km)",
                "cidade": "Fortaleza - CE",
                "caracteristicas": caracteristicas_pool[:6],
                "fonte": "Base local - preco 0 km de referencia",
                "ao_vivo": False,
                "url": "",
                "tipo": "estimativa",
            }
        )

        for i in range(5):
            preco = item["preco_usado_ref"] * (1 + rng.uniform(-0.13, 0.15))
            ano = rng.randint(2019, 2025)
            km = rng.randint(8_000, 12_000) * (2026 - ano)
            extras = rng.sample(caracteristicas_pool, k=5)
            ofertas.append(
                {
                    "titulo": f"{item['marca']} {item['modelo']} {ano}/{ano % 100:02d} - {item['motor']} {item['cambio']}",
                    "marca": item["marca"],
                    "modelo": item["modelo"],
                    "preco": round(preco, -2),
                    "ano": ano,
                    "km": km,
                    "combustivel": item["combustivel"],
                    "cambio": item["cambio"],
                    "carroceria": item["carroceria"],
                    "vendedor": vendedores[i % len(vendedores)],
                    "cidade": cidades[i % len(cidades)],
                    "caracteristicas": extras,
                    "fonte": "Base local - estimativa de mercado",
                    "ao_vivo": False,
                    "url": "",
                    "tipo": "estimativa",
                }
            )
    return ofertas


def _enriquecer_oferta_viva(
    oferta: dict, filtros: dict, selecionados: list[dict]
) -> dict | None:
    titulo = normalizar(oferta.get("titulo") or "")
    preco = oferta.get("preco")
    if preco is None:
        return None

    marcas_ok = sorted({normalizar(m["marca"]) for m in selecionados})
    modelos_ok = sorted({normalizar(m["modelo"]) for m in selecionados})
    if marcas_ok and not any(m in titulo for m in marcas_ok):
        return None
    if modelos_ok and not any(mo in titulo for mo in modelos_ok):
        return None

    catalogo_match = next(
        (m for m in selecionados if normalizar(m["modelo"]) in titulo), None
    )
    oferta = dict(oferta)
    oferta["marca"] = oferta.get("marca") or (
        catalogo_match["marca"] if catalogo_match else (filtros.get("marca") or "")
    )
    oferta["modelo"] = oferta.get("modelo") or (
        catalogo_match["modelo"] if catalogo_match else (filtros.get("modelo") or "")
    )
    oferta.setdefault("cidade", "Fortaleza - CE")
    oferta["tipo"] = "anuncio"
    if catalogo_match:
        oferta.setdefault("carroceria", catalogo_match["carroceria"])
        oferta.setdefault("combustivel", catalogo_match["combustivel"])
        oferta.setdefault("cambio", catalogo_match["cambio"])
        oferta.setdefault("caracteristicas", [])
    return oferta


def _aplicar_filtros(ofertas: list[dict], filtros: dict) -> list[dict]:
    resultado = []
    for oferta in ofertas:
        ano = oferta.get("ano") or 0
        km = oferta.get("km") if oferta.get("km") is not None else 0
        preco = oferta.get("preco") or 0

        if filtros.get("ano_min") and ano and ano < filtros["ano_min"]:
            continue
        if filtros.get("ano_max") and ano and ano > filtros["ano_max"]:
            continue
        if filtros.get("km_max") and km and km > filtros["km_max"]:
            continue
        if filtros.get("preco_min") and preco < filtros["preco_min"]:
            continue
        if filtros.get("preco_max") and preco > filtros["preco_max"]:
            continue
        if filtros.get("combustivel") and oferta.get("combustivel"):
            if normalizar(oferta["combustivel"]) != normalizar(filtros["combustivel"]):
                continue
        if filtros.get("cambio") and oferta.get("cambio"):
            if normalizar(oferta["cambio"]) != normalizar(filtros["cambio"]):
                continue
        if filtros.get("carroceria") and oferta.get("carroceria"):
            if normalizar(oferta["carroceria"]) != normalizar(filtros["carroceria"]):
                continue
        caracteristicas_busca = [normalizar(c) for c in (filtros.get("caracteristicas") or [])]
        if caracteristicas_busca and oferta.get("caracteristicas"):
            tem = {normalizar(c) for c in oferta["caracteristicas"]}
            if not all(c in tem for c in caracteristicas_busca):
                continue
        resultado.append(oferta)
    return resultado


def _ordenar(ofertas: list[dict], ordenar: str) -> list[dict]:
    chaves = {
        "menor_preco": lambda o: o.get("preco") or 0,
        "maior_preco": lambda o: -(o.get("preco") or 0),
        "ano": lambda o: -(o.get("ano") or 0),
        "km": lambda o: o.get("km") or 0,
    }
    return sorted(ofertas, key=chaves.get(ordenar, chaves["menor_preco"]))


def _estatisticas(ofertas: list[dict]) -> dict:
    precos = [o["preco"] for o in ofertas if o.get("preco")]
    por_fonte: dict[str, int] = {}
    for oferta in ofertas:
        chave = oferta.get("fonte", "desconhecida")
        por_fonte[chave] = por_fonte.get(chave, 0) + 1
    base = {
        "total": len(precos),
        "min": None,
        "max": None,
        "media": None,
        "mediana": None,
        "desvio": 0.0,
        "por_fonte": por_fonte,
        "ao_vivo": sum(1 for o in ofertas if o.get("ao_vivo")),
        "estimativas": sum(1 for o in ofertas if not o.get("ao_vivo")),
    }
    if not precos:
        return base
    base.update(
        {
            "min": min(precos),
            "max": max(precos),
            "media": statistics.fmean(precos),
            "mediana": statistics.median(precos),
            "desvio": statistics.pstdev(precos) if len(precos) > 1 else 0.0,
        }
    )
    return base


FILTROS_SUAVES = {
    "preco_min": "preço",
    "preco_max": "preço",
    "ano_min": "ano",
    "ano_max": "ano",
    "km_max": "km",
    "caracteristicas": "características",
}
FILTROS_RIGIDOS = {
    "combustivel": "combustível",
    "cambio": "câmbio",
    "carroceria": "carroceria",
}
MINIMO_OFERTAS = 3


def _rotulos_relaxados(chaves: set[str]) -> list[str]:
    rotulos = [
        rotulo
        for chave, rotulo in {**FILTROS_SUAVES, **FILTROS_RIGIDOS}.items()
        if chave in chaves
    ]
    vistos: dict[str, None] = {}
    for rotulo in rotulos:
        vistos.setdefault(rotulo, None)
    return list(vistos)


def _filtrar_sem_vazio(ofertas: list[dict], filtros: dict) -> tuple[list[dict], list[str]]:
    """Aplica os filtros e, se sobrarem poucos resultados, relaxa em etapas.

    1a etapa: solta preco/ano/km/caracteristicas (mantem marca, modelo e
    combustivel). 2a etapa: solta tudo. Assim o relatorio nunca fica vazio.
    """
    if not ofertas:
        return [], []

    principais = [
        "marca",
        "modelo",
        "combustivel",
        "cambio",
        "carroceria",
        "ordenar",
    ]
    apenas_principais = {k: v for k, v in filtros.items() if k in principais}

    atuais = _aplicar_filtros(ofertas, filtros)
    if len(atuais) >= MINIMO_OFERTAS:
        return atuais, []

    etapa1 = _aplicar_filtros(ofertas, apenas_principais)
    if len(etapa1) >= MINIMO_OFERTAS:
        relaxadas = {k for k in FILTROS_SUAVES if filtros.get(k)}
        return etapa1, _rotulos_relaxados(relaxadas)

    if not atuais:
        if etapa1:
            relaxadas = {k for k in FILTROS_SUAVES if filtros.get(k)}
            return etapa1, _rotulos_relaxados(relaxadas)
        usados = {k for k in {**FILTROS_SUAVES, **FILTROS_RIGIDOS} if filtros.get(k)}
        if usados:
            return list(ofertas), _rotulos_relaxados(usados)
    return atuais, []


def executar_busca(filtros: dict, config: dict) -> tuple[str, dict]:
    data_dir = config["DATA_DIR"]
    configure_cache(config["CACHE_DIR"])
    catalogo = carregar_catalogo(data_dir)

    ofertas_vivas: list[dict] = []
    mencoes_web: list[dict] = []
    comentarios: dict = {"resumo_base": {}, "comentarios_web": []}
    erros: list[dict] = []

    pool = ThreadPoolExecutor(max_workers=4)
    futuros = {
        pool.submit(buscar_em_portais, filtros): "portais",
        pool.submit(pesquisar_precos, filtros): "web",
        pool.submit(coletar_comentarios, filtros, data_dir): "comentarios",
    }

    def _guardar(tipo: str, dados) -> None:
        nonlocal ofertas_vivas, mencoes_web, comentarios
        if tipo == "portais":
            ofertas_vivas = dados or []
        elif tipo == "web":
            mencoes_web = (dados or {}).get("mencoes", [])
        elif tipo == "comentarios":
            comentarios = dados or comentarios

    # coleta tudo o que terminar dentro do tempo, sem descartar fontes
    concluidos, pendentes = futures_wait(set(futuros), timeout=BUSCA_TIMEOUT)
    if pendentes:
        # pequena graca para nao perder fontes que estavam quase prontas
        extras, pendentes = futures_wait(pendentes, timeout=BUSCA_GRACIA)
        concluidos = set(concluidos) | set(extras)

    for futuro in concluidos:
        tipo = futuros[futuro]
        try:
            _guardar(tipo, futuro.result())
        except Exception as exc:
            erros.append({"fonte": tipo, "motivo": str(exc)})
    for futuro in pendentes:
        futuro.cancel()
        erros.append({"fonte": futuros[futuro], "motivo": "tempo esgotado"})
    # nao bloqueia a resposta esperando threads presas em rede
    pool.shutdown(wait=False, cancel_futures=True)

    selecionados = _modelos_selecionados(filtros, catalogo)
    enriquecidas = [
        enriquecida
        for oferta in ofertas_vivas
        if (enriquecida := _enriquecer_oferta_viva(oferta, filtros, selecionados))
    ]

    ofertas_brutas = enriquecidas + ofertas_estimadas(filtros, catalogo)
    ofertas, relaxados = _filtrar_sem_vazio(ofertas_brutas, filtros)

    ofertas = _ordenar(ofertas, filtros.get("ordenar") or "menor_preco")

    fontes_status = [
        {
            "nome": "Portais de anuncios",
            "ok": bool(ofertas_vivas),
            "detalhe": (
                f"{len(ofertas_vivas)} anuncios ao vivo"
                if ofertas_vivas
                else "nenhum anuncio vivo capturado (bloqueio ou layout diferente)"
            ),
        },
        {
            "nome": "Pesquisa web de precos",
            "ok": bool(mencoes_web),
            "detalhe": f"{len(mencoes_web)} mencoes encontradas" if mencoes_web
            else "buscador nao retornou mencoes agora",
        },
        {
            "nome": "Comentarios de usuarios",
            "ok": bool(comentarios.get("comentarios_web")),
            "detalhe": (
                f"{len(comentarios.get('comentarios_web', []))} comentarios da web + base local"
                if comentarios.get("comentarios_web")
                else "usando base local (web indisponivel)"
            ),
        },
    ]

    resultado = {
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "filtros": filtros,
        "filtros_relaxados": relaxados,
        "ofertas": ofertas,
        "estatisticas": _estatisticas(ofertas),
        "mencoes_web": mencoes_web,
        "comentarios": comentarios,
        "fontes_ao_vivo": len(enriquecidas),
        "consulta_portais": bool(ofertas_vivas),
        "fontes_status": fontes_status,
        "erros": erros,
    }

    _salvar(resultado, config)
    _SEARCHES[resultado["id"]] = resultado
    return resultado["id"], resultado


def recuperar_busca(search_id: str, config: dict) -> dict | None:
    if search_id in _SEARCHES:
        resultado = _SEARCHES[search_id]
        if time.time() - resultado["ts"] <= SEARCH_TTL:
            return resultado
    path = os.path.join(config["CACHE_DIR"], "searches", f"{search_id}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def _salvar(resultado: dict, config: dict) -> None:
    pasta = os.path.join(config["CACHE_DIR"], "searches")
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, f"{resultado['id']}.json"), "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False)
