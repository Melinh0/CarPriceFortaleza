from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
from urllib.parse import urlencode

from .base import extract_offers, fetch_all

TEMPO_PORTAL = 60
TEMPO_FETCH = 10
MAX_URLS_POR_PORTAL = 5


def _slug(texto: str) -> str:
    trans = str.maketrans("áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ", "aaaaeeioooucAAAAEEIOOOUC")
    return (texto or "").lower().translate(trans).replace(" ", "-")


class PortalScraper:
    nome = ""
    base_url = ""

    def _variantes(self, caminho: str) -> list[str]:
        """Caminhos extras (paginacao e ordenacao) para o mesmo caminho."""
        return [f"?pagina=2"]

    def build_urls(self, filtros: dict) -> list[str]:
        marca = _slug(filtros.get("marca") or "")
        modelo = _slug(filtros.get("modelo") or "")
        caminhos: list[str] = []
        if marca and modelo:
            caminhos.append(f"{marca}/{modelo}")
        if marca:
            caminhos.append(marca)
        base = self.base_url.rstrip("/")
        urls: list[str] = []
        for caminho in caminhos:
            urls.append(f"{base}/{caminho}")
            for extra in self._variantes(caminho):
                urls.append(f"{base}/{caminho}{extra}")
        urls.append(base)
        vistos: dict[str, None] = {}
        for url in urls:
            vistos.setdefault(url, None)
        return list(vistos)[:MAX_URLS_POR_PORTAL]

    def search(self, filtros: dict) -> list[dict]:
        urls = self.build_urls(filtros)
        htmls = fetch_all(urls, timeout=TEMPO_FETCH, max_workers=3)
        ofertas: list[dict] = []
        for url, html in zip(urls, htmls):
            if not html:
                continue
            capturadas = extract_offers(html, self.nome, url)
            for oferta in capturadas:
                oferta["ao_vivo"] = True
            ofertas.extend(capturadas)
        return ofertas


class ICarrosScraper(PortalScraper):
    nome = "iCarros"
    base_url = "https://www.icarros.com.br/catalogo/marcas"


class WebmotorsScraper(PortalScraper):
    nome = "Webmotors"
    base_url = "https://www.webmotors.com.br/carros/comprar"

    def _variantes(self, caminho: str) -> list[str]:
        return ["?pagina=2", "?ordenacao=preco-menor"]


class MobiautoScraper(PortalScraper):
    nome = "Mobiauto"
    base_url = "https://www.mobiauto.com.br/carros"


class SeminovosBHScraper(PortalScraper):
    nome = "Seminovos BH"
    base_url = "https://www.seminovosbh.com.br/carros"

    def _variantes(self, caminho: str) -> list[str]:
        return ["?pagina=2", "?ordem=menor-preco"]


class NapistaScraper(PortalScraper):
    nome = "Napista"
    base_url = "https://www.napista.com.br/busca"


class OLXScraper(PortalScraper):
    nome = "OLX"
    base_url = "https://www.olx.com.br/busca"

    def build_urls(self, filtros: dict) -> list[str]:
        marca = (filtros.get("marca") or "").strip()
        modelo = (filtros.get("modelo") or "").strip()
        consulta = f"{marca} {modelo}".strip()
        if not consulta:
            return [self.base_url]
        urls = [
            self.base_url + "?" + urlencode({"q": consulta}),
            self.base_url + "?" + urlencode({"q": consulta, "order": "price:asc"}),
            self.base_url,
        ]
        vistos: dict[str, None] = {}
        for url in urls:
            vistos.setdefault(url, None)
        return list(vistos)


class MercadoLivreScraper(PortalScraper):
    nome = "Mercado Livre"
    base_url = "https://lista.mercadolivre.com.br"

    def build_urls(self, filtros: dict) -> list[str]:
        marca = _slug(filtros.get("marca") or "")
        modelo = _slug(filtros.get("modelo") or "")
        caminho = "/".join(p for p in (marca, modelo) if p)
        base = self.base_url.rstrip("/")
        urls = [f"{base}/{caminho}"] if caminho else []
        urls.append(base)
        return urls


SCRAPERS = [
    WebmotorsScraper(),
    NapistaScraper(),
    SeminovosBHScraper(),
    ICarrosScraper(),
    MobiautoScraper(),
    OLXScraper(),
    MercadoLivreScraper(),
]


def buscar_em_portais(filtros: dict) -> list[dict]:
    ofertas: list[dict] = []
    pool = ThreadPoolExecutor(max_workers=len(SCRAPERS))
    futuros = {
        pool.submit(scraper.search, filtros): scraper for scraper in SCRAPERS
    }
    concluidos, _ = futures_wait(set(futuros), timeout=TEMPO_PORTAL)
    for futuro in concluidos:
        try:
            ofertas.extend(futuro.result() or [])
        except Exception:
            continue
    pool.shutdown(wait=False, cancel_futures=True)

    dedup: dict[tuple, dict] = {}
    for oferta in ofertas:
        chave = (
            (oferta.get("titulo") or "").lower(),
            oferta.get("preco"),
            oferta.get("url") or "",
        )
        dedup.setdefault(chave, oferta)
    return list(dedup.values())
