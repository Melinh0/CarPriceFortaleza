"""Comentarios e opinioes de usuarios sobre os modelos (web + base local)."""

from __future__ import annotations

import json
import os

from .websearch import pesquisar_comentarios

_BASE: dict | None = None


def _carregar_base(data_dir: str) -> dict:
    global _BASE
    if _BASE is None:
        path = os.path.join(data_dir, "opinions_fallback.json")
        with open(path, encoding="utf-8") as fh:
            _BASE = json.load(fh)
    return _BASE


def _resumo_para(base: dict, modelo: str) -> dict:
    modelos = base.get("modelos", {})
    if modelo in modelos:
        return modelos[modelo]
    alvo = (modelo or "").lower().strip()
    for chave, resumo in modelos.items():
        if chave.startswith("_"):
            continue
        if chave.lower().strip() == alvo:
            return resumo
    for chave, resumo in modelos.items():
        if chave.startswith("_"):
            continue
        if alvo and (alvo in chave.lower() or chave.lower() in alvo):
            return resumo
    return modelos["_default"]


def coletar_comentarios(filtros: dict, data_dir: str) -> dict:
    """Retorna comentarios agregados da base local + opinioes encontradas na web."""
    base = _carregar_base(data_dir)
    resumo = _resumo_para(base, filtros.get("modelo") or "")

    try:
        web = pesquisar_comentarios(filtros)
    except Exception:
        web = []

    return {
        "resumo_base": resumo,
        "comentarios_web": web,
        "origem": {
            "base_local": base.get("observacao", ""),
            "web": "Coleta ao vivo de paginas de opiniao e forums (pode falhar se o buscador bloquear).",
        },
    }
