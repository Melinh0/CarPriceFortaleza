from __future__ import annotations

import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
)

HEADERS = {
    "User-Agent": USER_AGENTS[0],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Upgrade-Insecure-Requests": "1",
}

CACHE_TTL_SECONDS = 6 * 60 * 60
CACHE_MAX_ENTRADAS = 140
FETCH_TENTATIVAS = 2
FETCH_BACKOFF = 0.6
PRICE_RE = re.compile(r"R\$\s*([\d]{1,3}(?:\.[\d]{3})+(?:,[\d]{1,2})?|[\d]+(?:,[\d]{1,2})?)")
ANO_RE = re.compile(r"\b(20[0-2]\d)(?:\s*[/\-]\s*\d{2})?\b")
KM_RE = re.compile(r"\b([\d]{1,3}(?:\.[\d]{3})+|\d{3,7})\s*km\b", re.IGNORECASE)
MAX_OFERTAS_POR_PAGINA = 80

_cache: dict[str, dict] = {}
_cache_path: str | None = None

_session = requests.Session()
_retry = Retry(
    total=2,
    connect=2,
    read=2,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET"}),
)
_session.mount("https://", HTTPAdapter(max_retries=_retry, pool_connections=10, pool_maxsize=20))
_session.mount("http://", HTTPAdapter(max_retries=_retry, pool_connections=10, pool_maxsize=20))


def configure_cache(cache_dir: str) -> None:
    global _cache_path, _cache
    _cache_path = os.path.join(cache_dir, "http_cache.json")
    if os.path.exists(_cache_path):
        try:
            with open(_cache_path, encoding="utf-8") as fh:
                _cache = json.load(fh)
        except (OSError, json.JSONDecodeError):
            _cache = {}


def _cache_get(key: str):
    entry = _cache.get(key)
    if not entry:
        return None
    if time.time() - entry.get("ts", 0) > CACHE_TTL_SECONDS:
        return None
    return entry.get("data")


def _cache_set(key: str, data) -> None:
    _cache[key] = {"ts": time.time(), "data": data}
    if len(_cache) > CACHE_MAX_ENTRADAS:
        antigos = sorted(_cache, key=lambda k: _cache[k].get("ts", 0))
        for velho in antigos[: len(_cache) - CACHE_MAX_ENTRADAS]:
            if velho != key:
                _cache.pop(velho, None)
    if _cache_path:
        try:
            with open(_cache_path, "w", encoding="utf-8") as fh:
                json.dump(_cache, fh, ensure_ascii=False)
        except OSError:
            pass


def _headers_para(url: str) -> dict:
    idx = int(hashlib.md5(url.encode("utf-8", "ignore")).hexdigest()[:4], 16) % len(USER_AGENTS)
    headers = dict(HEADERS)
    headers["User-Agent"] = USER_AGENTS[idx]
    rede = urlparse(url).netloc
    if rede:
        headers["Referer"] = f"https://{rede}/"
    return headers


def parse_price(text: str) -> float | None:
    match = PRICE_RE.search(text or "")
    if not match:
        return None
    raw = match.group(1).replace(".", "").replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    if value < 1000 or value > 3_000_000:
        return None
    return value


def fetch(url: str, timeout: int = 12, use_cache: bool = True) -> str | None:
    if use_cache:
        cached = _cache_get("GET:" + url)
        if cached is not None:
            return cached
    html = None
    for tentativa in range(FETCH_TENTATIVAS):
        if tentativa:
            time.sleep(FETCH_BACKOFF * tentativa)
        try:
            resp = _session.get(
                url, headers=_headers_para(url), timeout=timeout, allow_redirects=True
            )
        except requests.RequestException:
            continue
        if resp.status_code == 200 and resp.text:
            if "charset" not in (resp.headers.get("Content-Type") or "").lower():
                resp.encoding = resp.apparent_encoding
            html = resp.text
            break
        if resp.status_code in (404, 410):
            break
    if html is None:
        return None
    if use_cache:
        _cache_set("GET:" + url, html)
    return html


def fetch_all(urls: list[str], timeout: int = 12, max_workers: int = 3) -> list[str | None]:
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(urls))) as pool:
        return list(pool.map(lambda u: fetch(u, timeout=timeout), urls))


def extrair_detalhes(texto: str) -> dict:
    """Extrai ano, km, cambio e combustivel de um titulo de anuncio."""
    base = (texto or "").lower()
    detalhes: dict = {"ano": None, "km": None, "cambio": None, "combustivel": None}

    anos = [int(a) for a in ANO_RE.findall(base)]
    anos = [a for a in anos if 2005 <= a <= 2026]
    if anos:
        detalhes["ano"] = max(anos)

    for bruto in KM_RE.findall(base):
        valor = int(bruto.replace(".", ""))
        if 100 <= valor <= 999_999:
            detalhes["km"] = valor
            break

    if "cvt" in base:
        detalhes["cambio"] = "CVT"
    elif "robotizado" in base or "automatizado" in base:
        detalhes["cambio"] = "Robotizado"
    elif "automatico" in base or "auto 4" in base or "tiptronic" in base or "dsg" in base:
        detalhes["cambio"] = "Automatico"
    elif "manual" in base:
        detalhes["cambio"] = "Manual"

    if "eletrico" in base or "elétrico" in base or "battery" in base:
        detalhes["combustivel"] = "Eletrico"
    elif "hibrido" in base or "híbrido" in base or "hybrid" in base:
        detalhes["combustivel"] = "Hibrido"
    elif "diesel" in base:
        detalhes["combustivel"] = "Diesel"
    elif "flex" in base:
        detalhes["combustivel"] = "Flex"
    elif "gasolina" in base or "gas" in base:
        detalhes["combustivel"] = "Gasolina"
    elif "alcool" in base or "etanol" in base:
        detalhes["combustivel"] = "Alcool"

    return detalhes


def _completar_detalhes(oferta: dict) -> dict:
    detalhes = extrair_detalhes(f"{oferta.get('titulo', '')} {oferta.get('url', '')}")
    for chave, valor in detalhes.items():
        if oferta.get(chave) is None and valor is not None:
            oferta[chave] = valor
    return oferta


def extract_offers(html: str, source: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    offers: list[dict] = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            for node in _walk_jsonld(item):
                name = str(node.get("name") or "")
                price = None
                offers_node = node.get("offers")
                if isinstance(offers_node, dict):
                    price = _to_number(offers_node.get("price"))
                elif isinstance(offers_node, list):
                    for off in offers_node:
                        price = _to_number(off.get("price")) if isinstance(off, dict) else None
                        if price:
                            break
                if name and price:
                    offers.append(
                        {
                            "titulo": name,
                            "preco": price,
                            "url": base_url,
                            "fonte": source,
                            "cidade": "Fortaleza - CE",
                        }
                    )

    if not offers:
        offers.extend(_extrair_por_atributos(soup, source, base_url))

    if not offers:
        offers.extend(_extrair_de_json_embutido(soup, source, base_url))

    if not offers:
        for anchor in soup.find_all("a", href=True):
            texto = " ".join(anchor.get_text(" ", strip=True).split())
            preco = parse_price(texto)
            if not preco or len(texto) < 15:
                continue
            url = urljoin(base_url, anchor["href"])
            if urlparse(url).netloc != urlparse(base_url).netloc:
                continue
            offers.append(
                {
                    "titulo": texto[:160],
                    "preco": preco,
                    "url": url,
                    "fonte": source,
                    "cidade": "Fortaleza - CE",
                }
            )

    dedup: dict[tuple, dict] = {}
    for offer in offers:
        offer = _completar_detalhes(offer)
        key = (offer["titulo"].lower(), offer["preco"])
        dedup.setdefault(key, offer)
    return list(dedup.values())[:MAX_OFERTAS_POR_PAGINA]


def _extrair_por_atributos(soup: BeautifulSoup, source: str, base_url: str) -> list[dict]:
    ofertas: list[dict] = []
    for no in soup.select("[data-price], [itemprop='price'], meta[itemprop='price'], [data-testid*='price']"):
        bruto = no.get("data-price") or no.get("content") or no.get("value") or ""
        preco = None
        try:
            candidato = float(str(bruto).replace(".", "").replace(",", "."))
            if 1000 <= candidato <= 3_000_000:
                preco = candidato
        except (TypeError, ValueError):
            preco = parse_price(str(bruto))
        if not preco:
            continue
        pai = no.find_parent(["a", "article", "li", "div"]) or no
        titulo = " ".join(pai.get_text(" ", strip=True).split())[:160]
        if len(titulo) < 10:
            continue
        url = base_url
        ancora = pai.find("a", href=True) or (no.find("a", href=True) if hasattr(no, "find") else None)
        if ancora:
            url = urljoin(base_url, ancora["href"])
        ofertas.append(
            {"titulo": titulo, "preco": preco, "url": url, "fonte": source, "cidade": "Fortaleza - CE"}
        )
        if len(ofertas) >= MAX_OFERTAS_POR_PAGINA:
            break
    return ofertas


def _extrair_de_json_embutido(soup: BeautifulSoup, source: str, base_url: str) -> list[dict]:
    ofertas: list[dict] = []
    for script in soup.find_all("script"):
        texto = (script.string or "").strip()
        if not texto or len(texto) < 40 or not texto.startswith(("{", "[")):
            continue
        try:
            dados = json.loads(texto)
        except (json.JSONDecodeError, TypeError):
            continue
        for no in _varrer_nos_com_preco(dados):
            preco = no["_preco"]
            titulo = str(
                no.get("titulo") or no.get("nome") or no.get("title") or no.get("modelo") or ""
            ).strip()
            if not titulo or len(titulo) < 8:
                continue
            ofertas.append(
                {
                    "titulo": titulo[:160],
                    "preco": preco,
                    "url": base_url,
                    "fonte": source,
                    "cidade": "Fortaleza - CE",
                }
            )
            if len(ofertas) >= MAX_OFERTAS_POR_PAGINA:
                return ofertas
    return ofertas


def _varrer_nos_com_preco(dados, profundidade: int = 0):
    if profundidade > 7:
        return
    if isinstance(dados, dict):
        preco = None
        for chave in ("price", "preco", "valor", "value", "amount"):
            if chave in dados:
                preco = _to_number(dados[chave])
                if preco:
                    break
        if preco:
            nome = None
            for chave in ("name", "titulo", "title", "label", "modelo", "vehicle"):
                if isinstance(dados.get(chave), str) and dados.get(chave).strip():
                    nome = dados[chave]
                    break
            if nome:
                yield {"_preco": preco, "titulo": nome}
        for valor in dados.values():
            yield from _varrer_nos_com_preco(valor, profundidade + 1)
    elif isinstance(dados, list):
        for item in dados:
            yield from _varrer_nos_com_preco(item, profundidade + 1)


def _walk_jsonld(node: dict):
    if isinstance(node, dict):
        if node.get("@type") in ("Product", "Car", "OfferCatalog") or "offers" in node:
            yield node
        graph = node.get("@graph")
        if isinstance(graph, list):
            for child in graph:
                yield from _walk_jsonld(child)
        for key in ("itemListElement", "item", "mainEntity"):
            child = node.get(key)
            if isinstance(child, list):
                for sub in child:
                    yield from _walk_jsonld(sub)
            elif isinstance(child, dict):
                yield from _walk_jsonld(child)


def _to_number(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(str(value).replace(",", "."))
    except ValueError:
        return None
    return number if 1000 <= number <= 3_000_000 else None
