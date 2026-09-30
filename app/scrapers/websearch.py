"""Pesquisa diversificada na web (DuckDuckGo + Bing) por precos e mencoes reais."""

from __future__ import annotations

import time
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from .base import HEADERS, parse_price

DDG_URL = "https://html.duckduckgo.com/html/"
DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
BING_URL = "https://www.bing.com/search"

SLEEP_ENTRE_QUERIES = 0.35
MAX_MENCOES = 20
MAX_COMENTARIOS = 14
MAX_MENCOES_DETALHES = 18
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


ENGINES = [_buscar_ddg_html, _buscar_ddg_lite, _buscar_bing]
TEMPO_MAX_POR_QUERY = 20
TEMPO_MAX_PRECOS = 40
TEMPO_MAX_COMENTARIOS = 25
TIMEOUT_ENGINE = 5
COOLDOWN_ENGINE = 180  # segundos: motor que errou rede fica fora do caminho

_motores_fora: dict[str, float] = {}


def _motor_disponivel(engine) -> bool:
    return time.time() >= _motores_fora.get(engine.__name__, 0.0)


def _marcar_motor_fora(engine) -> None:
    _motores_fora[engine.__name__] = time.time() + COOLDOWN_ENGINE


def buscar_na_web(query: str, max_resultados: int = 8, timeout: int | None = None) -> list[dict]:
    """Busca uma query; tenta DuckDuckGo, DuckDuckGo Lite e Bing ate achar algo.

    Motor que falha na rede entra em cooldown: nas proximas queries ele e
    pulado, entao o buscador que funciona (ex.: Bing) e alcancado rapido.
    """
    timeout = TIMEOUT_ENGINE if timeout is None else timeout
    limite = time.perf_counter() + TEMPO_MAX_POR_QUERY
    motores = [e for e in ENGINES if _motor_disponivel(e)] or list(ENGINES)
    for engine in motores:
        if time.perf_counter() > limite:
            break
        try:
            resultados = engine(query, max_resultados, timeout)
        except Exception:
            # rede bloqueada/indisponivel: nao insiste, marca e passa adiante
            _marcar_motor_fora(engine)
            continue
        if resultados:
            time.sleep(SLEEP_ENTRE_QUERIES)
            return resultados
    return []


def _consultas_precos(filtros: dict) -> list[str]:
    marca = filtros.get("marca") or ""
    modelo = filtros.get("modelo") or ""
    base = f"{marca} {modelo}".strip()
    if not base:
        # busca generica (sem marca): eletricos/hibridos viram pesquisa local
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
            ]
        return []
    consultas = [
        f"{base} preco usado",
        f"{base} preco Fortaleza",
        f"{base} vale a pena preco",
        f"{base} preco 0 km",
        f"{base} tabela fipe preco",
    ]
    if marca and modelo:
        consultas.append(f'"{modelo}" preco site:icarros.com.br')
        consultas.append(f'"{modelo}" preco site:webmotors.com.br')
        consultas.append(f'"{modelo}" preco site:mobiauto.com.br')
    if normalizar_combustivel(filtros.get("combustivel")) in ("eletrico", "hibrido"):
        consultas.insert(0, f"{base} preco eletrico autonomia")
        consultas.append(f"{base} vale a pena eletrico")
    return consultas


def normalizar_combustivel(valor: str) -> str:
    return (valor or "").lower().strip()


def pesquisar_precos(filtros: dict) -> dict:
    """Roda consultas variadas sobre o modelo para levantar precos reais na web."""
    consultas = _consultas_precos(filtros)
    if not consultas:
        return {"consultas": [], "mencoes": []}

    mencoes: list[dict] = []
    vistas: set[str] = set()
    fim = time.perf_counter() + TEMPO_MAX_PRECOS
    for query in consultas:
        if time.perf_counter() > fim:
            break
        for item in buscar_na_web(query, max_resultados=8):
            url = item.get("url", "")
            if not url or url in vistas:
                continue
            vistas.add(url)
            item["consulta"] = query
            mencoes.append(item)
        if len(mencoes) >= MAX_MENCOES:
            break

    return {"consultas": consultas, "mencoes": mencoes[:MAX_MENCOES]}


def pesquisar_comentarios(filtros: dict) -> list[dict]:
    """Busca opinioes e comentarios de usuarios sobre o modelo."""
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
    ]
    comentarios: list[dict] = []
    vistas: set[str] = set()
    fim = time.perf_counter() + TEMPO_MAX_COMENTARIOS
    for query in consultas:
        if time.perf_counter() > fim:
            break
        for item in buscar_na_web(query, max_resultados=6):
            url = item.get("url", "")
            if not url or url in vistas:
                continue
            vistas.add(url)
            item["consulta"] = query
            comentarios.append(item)
        if len(comentarios) >= MAX_COMENTARIOS:
            break
    return comentarios[:MAX_COMENTARIOS]


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
    ]


def _tipo_mencao(consulta: str) -> str:
    consulta = consulta.lower()
    if "garantia" in consulta:
        return "garantia"
    if "financiamento" in consulta or "sem juros" in consulta:
        return "campanha"
    return "preco"


def pesquisar_detalhes(marca: str, modelo: str) -> dict:
    """Levanta precos a vista, campanhas de financiamento e garantia de um modelo novo.

    Diferente de pesquisar_precos (que recebe filtros de busca usados), esta funcao
    recebe marca/modelo direto e classifica cada mencao em preco, campanha ou garantia.
    """
    consultas = _consultas_detalhes(marca, modelo)
    if not consultas:
        return {"consultas": [], "mencoes": []}

    mencoes: list[dict] = []
    vistas: set[str] = set()
    fim = time.perf_counter() + TEMPO_MAX_DETALHES
    for query in consultas:
        if time.perf_counter() > fim:
            break
        for item in buscar_na_web(query, max_resultados=8):
            url = item.get("url", "")
            if not url or url in vistas:
                continue
            vistas.add(url)
            item["consulta"] = query
            item["tipo"] = _tipo_mencao(query)
            mencoes.append(item)
        if len(mencoes) >= MAX_MENCOES_DETALHES:
            break
    return {"consultas": consultas, "mencoes": mencoes[:MAX_MENCOES_DETALHES]}
