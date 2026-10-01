from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from .base import HEADERS, parse_price

DDG_URL = "https://html.duckduckgo.com/html/"
DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
BING_URL = "https://www.bing.com/search"
MOJEEK_URL = "https://www.mojeek.com/search"
YAHOO_URL = "https://search.yahoo.com/search"

SLEEP_ENTRE_QUERIES = 0.3
MAX_MENCOES = 30
MAX_COMENTARIOS = 18
MAX_MENCOES_DETALHES = 24
TEMPO_MAX_DETALHES = 30


def _parse_ddg_html(html: str, max_resultados: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    resultados = []
    for bloco in soup.select(".result")[:max_resultados]:
        link = bloco.select_one("a.result__a")
        trecho = bloco.select_one(".result__snippet")
        if not link:
            continue
        texto_trecho = trecho.get_text(" ", strip=True) if trecho else ""
        resultados.append(
            {
                "titulo": link.get_text(" ", strip=True),
                "url": link.get("href", ""),
                "trecho": texto_trecho,
                "preco": parse_price(texto_trecho)
                or parse_price(link.get_text(" ", strip=True)),
            }
        )
    return resultados


def _parse_ddg_lite(html: str, max_resultados: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    seletor = "a.result-link, td.result-link a, table.links a"
    links = soup.select(seletor)
    if not links:
        return []
    resultados = []
    for link in links:
        titulo = link.get_text(" ", strip=True)
        url = link.get("href", "")
        if not titulo or len(titulo) < 10 or not url:
            continue
        if "duckduckgo.com/y.js" in url:
            continue
        pai = link.find_parent("tr")
        trecho = ""
        if pai:
            proxima = pai.find_next_sibling("tr")
            if proxima:
                trecho = proxima.get_text(" ", strip=True)[:300]
        resultados.append(
            {
                "titulo": titulo[:160],
                "url": url,
                "trecho": trecho,
                "preco": parse_price(trecho) or parse_price(titulo),
            }
        )
        if len(resultados) >= max_resultados:
            break
    return resultados


def _parse_bing(html: str, max_resultados: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    resultados = []
    for bloco in soup.select("li.b_algo")[:max_resultados]:
        link = bloco.select_one("h2 a")
        trecho = bloco.select_one(".b_caption p") or bloco.select_one("p")
        if not link:
            continue
        texto_trecho = trecho.get_text(" ", strip=True) if trecho else ""
        resultados.append(
            {
                "titulo": link.get_text(" ", strip=True),
                "url": link.get("href", ""),
                "trecho": texto_trecho,
                "preco": parse_price(texto_trecho)
                or parse_price(link.get_text(" ", strip=True)),
            }
        )
    return resultados


def _parse_mojeek(html: str, max_resultados: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    resultados = []
    for bloco in soup.select("ul.results-standard li")[: max_resultados * 2]:
        link = bloco.select_one("h2 a") or bloco.select_one("a.title")
        if not link:
            continue
        trecho = bloco.select_one("p") or bloco.select_one(".s")
        texto_trecho = trecho.get_text(" ", strip=True) if trecho else ""
        url = link.get("href", "")
        if not url:
            continue
        resultados.append(
            {
                "titulo": link.get_text(" ", strip=True)[:160],
                "url": url,
                "trecho": texto_trecho,
                "preco": parse_price(texto_trecho) or parse_price(link.get_text(" ", strip=True)),
            }
        )
        if len(resultados) >= max_resultados:
            break
    return resultados


def _parse_yahoo(html: str, max_resultados: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    resultados = []
    for bloco in soup.select("div.algo, div.dd.algo")[:max_resultados]:
        link = bloco.select_one("h3 a") or bloco.select_one("a")
        if not link:
            continue
        trecho = bloco.select_one(".compText") or bloco.select_one("p")
        texto_trecho = trecho.get_text(" ", strip=True) if trecho else ""
        resultados.append(
            {
                "titulo": link.get_text(" ", strip=True)[:160],
                "url": link.get("href", ""),
                "trecho": texto_trecho,
                "preco": parse_price(texto_trecho) or parse_price(link.get_text(" ", strip=True)),
            }
        )
    return resultados


def _buscar_ddg_html(query: str, max_resultados: int, timeout: int) -> list[dict]:
    resp = requests.post(
        DDG_URL, data={"q": query, "kl": "br-pt"}, headers=HEADERS, timeout=timeout
    )
    if resp.status_code != 200:
        return []
    return _parse_ddg_html(resp.text, max_resultados)


def _buscar_ddg_lite(query: str, max_resultados: int, timeout: int) -> list[dict]:
    resp = requests.post(
        DDG_LITE_URL, data={"q": query, "kl": "br-pt"}, headers=HEADERS, timeout=timeout
    )
    if resp.status_code != 200:
        resp = requests.get(
            DDG_LITE_URL + "?q=" + quote_plus(query),
            headers=HEADERS,
            timeout=timeout,
        )
        if resp.status_code != 200:
            return []
    return _parse_ddg_lite(resp.text, max_resultados)


def _buscar_bing(query: str, max_resultados: int, timeout: int) -> list[dict]:
    resp = requests.get(
        BING_URL,
        params={"q": query, "setlang": "pt-br", "cc": "BR"},
        headers=HEADERS,
        timeout=timeout,
    )
    if resp.status_code != 200:
        return []
    return _parse_bing(resp.text, max_resultados)


def _buscar_mojeek(query: str, max_resultados: int, timeout: int) -> list[dict]:
    resp = requests.get(
        MOJEEK_URL,
        params={"q": query, "fmt": "html"},
        headers=HEADERS,
        timeout=timeout,
    )
    if resp.status_code != 200:
        return []
    return _parse_mojeek(resp.text, max_resultados)


def _buscar_yahoo(query: str, max_resultados: int, timeout: int) -> list[dict]:
    resp = requests.get(
        YAHOO_URL,
        params={"p": query, "fr": "yfp-t", "ei": "UTF-8"},
        headers=HEADERS,
        timeout=timeout,
    )
    if resp.status_code != 200:
        return []
    return _parse_yahoo(resp.text, max_resultados)


ENGINES = [
    _buscar_ddg_html,
    _buscar_ddg_lite,
    _buscar_bing,
    _buscar_mojeek,
    _buscar_yahoo,
]
TEMPO_MAX_POR_QUERY = 20
TEMPO_MAX_PRECOS = 40
TEMPO_MAX_COMENTARIOS = 25
TIMEOUT_ENGINE = 5
COOLDOWN_ENGINE = 180

_motores_fora: dict[str, float] = {}


def _motor_disponivel(engine) -> bool:
    return time.time() >= _motores_fora.get(engine.__name__, 0.0)


def _marcar_motor_fora(engine) -> None:
    _motores_fora[engine.__name__] = time.time() + COOLDOWN_ENGINE


def buscar_na_web(query: str, max_resultados: int = 8, timeout: int | None = None) -> list[dict]:
    timeout = TIMEOUT_ENGINE if timeout is None else timeout
    limite = time.perf_counter() + TEMPO_MAX_POR_QUERY
    motores = [e for e in ENGINES if _motor_disponivel(e)] or list(ENGINES)
    resultados: list[dict] = []
    vistas: set[str] = set()
    for engine in motores:
        if time.perf_counter() > limite:
            break
        if len(resultados) >= max_resultados:
            break
        try:
            parciais = engine(query, max_resultados, timeout)
        except Exception:
            _marcar_motor_fora(engine)
            continue
        for item in parciais or []:
            url = item.get("url", "")
            if url and url in vistas:
                continue
            vistas.add(url)
            resultados.append(item)
            if len(resultados) >= max_resultados:
                break
        if parciais:
            time.sleep(SLEEP_ENTRE_QUERIES)
    return resultados[:max_resultados]


def _tipo_mencao(consulta: str) -> str:
    consulta = (consulta or "").lower()
    if "garantia" in consulta:
        return "garantia"
    if "financiamento" in consulta or "sem juros" in consulta or "campanha" in consulta:
        return "campanha"
    return "preco"


def _executar_consultas(
    consultas: list[str],
    max_resultados: int,
    limite: int,
    tempo_max: int,
    workers: int = 5,
) -> list[dict]:
    """Roda as consultas em paralelo e devolve mencoes deduplicadas por URL."""
    if not consultas:
        return []
    pool = ThreadPoolExecutor(max_workers=min(workers, len(consultas)))
    futuros = {
        pool.submit(buscar_na_web, query, max_resultados): query for query in consultas
    }
    concluidos, _ = futures_wait(set(futuros), timeout=tempo_max)

    mencoes: list[dict] = []
    vistas: set[str] = set()
    for futuro in concluidos:
        query = futuros[futuro]
        try:
            itens = futuro.result() or []
        except Exception:
            continue
        for item in itens:
            url = item.get("url", "")
            if not url or url in vistas:
                continue
            vistas.add(url)
            item["consulta"] = query
            item.setdefault("tipo", _tipo_mencao(query))
            mencoes.append(item)
    pool.shutdown(wait=False, cancel_futures=True)

    ordem = {query: i for i, query in enumerate(consultas)}
    mencoes.sort(key=lambda m: ordem.get(m.get("consulta", ""), len(ordem)))
    return mencoes[:limite]


def _consultas_precos(filtros: dict) -> list[str]:
    marca = filtros.get("marca") or ""
    modelo = filtros.get("modelo") or ""
    base = f"{marca} {modelo}".strip()
    if not base:
        if normalizar_combustivel(filtros.get("combustivel")) in (
            "eletrico",
            "hibrido",
        ):
            return [
                "carros eletricos a venda em Fortaleza CE preco",
                "carros eletricos usados Fortaleza preco",
                "carros eletricos 0 km preco Brasil 2026",
                "concessionaria carro eletrico Fortaleza",
                "carros hibridos a venda em Fortaleza preco",
                "carros hibridos usados Fortaleza CE preco tabela",
            ]
        return []
    consultas = [
        f"{base} preco usado",
        f"{base} preco seminovo Fortaleza",
        f"{base} preco Fortaleza CE",
        f"{base} preco 0 km",
        f"{base} preco a vista concessionaria",
        f"{base} tabela fipe preco",
        f"{base} vale a pena preco",
    ]
    if marca and modelo:
        consultas += [
            f'"{modelo}" preco site:icarros.com.br',
            f'"{modelo}" preco site:webmotors.com.br',
            f'"{modelo}" preco site:mobiauto.com.br',
            f'"{modelo}" preco site:napista.com.br',
            f'"{modelo}" preco site:olx.com.br',
            f'"{modelo}" preco site:seminovosbh.com.br',
        ]
    if filtros.get("cambio"):
        consultas.insert(0, f"{base} {filtros['cambio']} preco")
    if normalizar_combustivel(filtros.get("condicao")) == "seminovo":
        consultas.insert(0, f"{base} preco usado quanto custa seminovo")
    if normalizar_combustivel(filtros.get("combustivel")) in ("eletrico", "hibrido"):
        consultas.insert(0, f"{base} preco eletrico autonomia")
        consultas.append(f"{base} vale a pena eletrico")
    return consultas


def normalizar_combustivel(valor: str) -> str:
    return (valor or "").lower().strip()


def pesquisar_precos(filtros: dict) -> dict:
    consultas = _consultas_precos(filtros)
    if not consultas:
        return {"consultas": [], "mencoes": []}
    mencoes = _executar_consultas(
        consultas,
        max_resultados=8,
        limite=MAX_MENCOES,
        tempo_max=TEMPO_MAX_PRECOS,
    )
    return {"consultas": consultas, "mencoes": mencoes}


def pesquisar_comentarios(filtros: dict) -> list[dict]:
    marca = filtros.get("marca") or ""
    modelo = filtros.get("modelo") or ""
    base = f"{marca} {modelo}".strip()
    if not base:
        return []
    consultas = [
        f"{base} vale a pena opiniao de quem tem",
        f"{base} experiencia dono problema",
        f"{base} quanto paguei",
        f"{base} review donos longo prazo",
        f"{base} reclamacao defeito",
        f"{base} custo manutencao troca de pecas",
        f"{base} consumo real no dia a dia",
    ]
    return _executar_consultas(
        consultas,
        max_resultados=6,
        limite=MAX_COMENTARIOS,
        tempo_max=TEMPO_MAX_COMENTARIOS,
    )


def _consultas_detalhes(marca: str, modelo: str) -> list[str]:
    base = f"{marca} {modelo}".strip()
    if not base:
        return []
    return [
        f"{base} preco a vista concessionaria 0 km",
        f"{base} preco tabela 2026",
        f"{base} campanha financiamento sem juros parcelas",
        f"{base} garantia fabrica anos quilometros",
        f"{base} desconto negociacao loja fisica",
        f"{base} preco a vista Fortaleza CE",
        f"{base} site:icarros.com.br preco",
        f"{base} site:webmotors.com.br preco",
        f"{base} site:napista.com.br preco",
    ]


def pesquisar_detalhes(marca: str, modelo: str) -> dict:
    consultas = _consultas_detalhes(marca, modelo)
    if not consultas:
        return {"consultas": [], "mencoes": []}
    mencoes = _executar_consultas(
        consultas,
        max_resultados=8,
        limite=MAX_MENCOES_DETALHES,
        tempo_max=TEMPO_MAX_DETALHES,
    )
    return {"consultas": consultas, "mencoes": mencoes}
