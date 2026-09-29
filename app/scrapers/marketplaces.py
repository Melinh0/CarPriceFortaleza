"""Scrapers de portais de anuncios de veiculos (iCarros, Webmotors, Mobiauto)."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait

from .base import extract_offers, fetch

TEMPO_PORTAL = 60
TEMPO_FETCH = 10


def _slug(texto: str) -> str:
    trans = str.maketrans("áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ", "aaaaeeioooucAAAAEEIOOOUC")
    return (texto or "").lower().translate(trans).replace(" ", "-")


class PortalScraper:
    nome = ""
    base_url = ""

    def build_urls(self, filtros: dict) -> list[str]:
        """Candidatos do mais especifico para o mais generico.

        Se o portal nao tiver a pagina exata do modelo, tenta a pagina da marca
        e por fim a listagem geral — assim a busca nunca fica sem resposta.
        """
        marca = _slug(filtros.get("marca") or "")
        modelo = _slug(filtros.get("modelo") or "")
        caminhos: list[str] = []
        if marca and modelo:
            caminhos.append(f"{marca}/{modelo}")
        if marca:
            caminhos.append(marca)
        base = self.base_url.rstrip("/")
        urls = [f"{base}/{caminho}" for caminho in caminhos]
        urls.append(base)
        vistos: dict[str, None] = {}
        for url in urls:
            vistos.setdefault(url, None)
        return list(vistos)

    def search(self, filtros: dict) -> list[dict]:
        ofertas: list[dict] = []
        for url in self.build_urls(filtros):
            html = fetch(url, timeout=TEMPO_FETCH)
            if not html:
                continue
            time.sleep(0.3)
            capturadas = extract_offers(html, self.nome, url)
            for oferta in capturadas:
                oferta["ao_vivo"] = True
            ofertas.extend(capturadas)
            if capturadas:
                break
        return ofertas


class ICarrosScraper(PortalScraper):
    nome = "iCarros"
    base_url = "https://www.icarros.com.br/catalogo/marcas"


class WebmotorsScraper(PortalScraper):
    nome = "Webmotors"
    base_url = "https://www.webmotors.com.br/carros/comprar"


class MobiautoScraper(PortalScraper):
    nome = "Mobiauto"
    base_url = "https://www.mobiauto.com.br/carros"


class SeminovosBHScraper(PortalScraper):
    nome = "Seminovos BH"
    base_url = "https://www.seminovosbh.com.br/carros"


class NapistaScraper(PortalScraper):
    nome = "Napista"
    base_url = "https://www.napista.com.br/busca"


SCRAPERS = [
    WebmotorsScraper(),
    NapistaScraper(),
    SeminovosBHScraper(),
    ICarrosScraper(),
    MobiautoScraper(),
]


def buscar_em_portais(filtros: dict) -> list[dict]:
    """Consulta todos os portais em paralelo; falha de um nao afeta os demais."""
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
    # nao espera scrapers presos: o tempo da busca e limitado
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
