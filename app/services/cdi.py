from __future__ import annotations

DIAS_UTEIS_ANO = 252
DIAS_UTEIS_MES = 21

IR_TABELA = (
    (180, 22.5),
    (360, 20.0),
    (720, 17.5),
    (float("inf"), 15.0),
)


def aliquota_ir(dias_uteis: int) -> float:
    for limite, aliquota in IR_TABELA:
        if dias_uteis <= limite:
            return aliquota
    return 15.0


def calcular(
    valor: float,
    meses: int,
    pct_cdi: float = 100.0,
    cdi_aa: float = 13.65,
) -> dict:
    if valor <= 0:
        raise ValueError("O valor aplicado deve ser maior que zero.")
    if meses <= 0:
        raise ValueError("O prazo em meses deve ser maior que zero.")
    if pct_cdi <= 0:
        raise ValueError("O percentual do CDI deve ser maior que zero.")
    if cdi_aa < 0:
        raise ValueError("A taxa do CDI não pode ser negativa.")

    dias_uteis = round(meses * DIAS_UTEIS_ANO / 12)

    taxa_dia = (1 + cdi_aa / 100) ** (1 / DIAS_UTEIS_ANO) - 1
    taxa_dia_aplicada = taxa_dia * (pct_cdi / 100)

    fator = (1 + taxa_dia_aplicada) ** dias_uteis
    bruto = valor * fator
    rendimento_bruto = bruto - valor

    aliquota = aliquota_ir(dias_uteis)
    ir = rendimento_bruto * aliquota / 100
    rendimento_liquido = rendimento_bruto - ir
    total_final = valor + rendimento_liquido

    tabela = []
    for mes in range(1, meses + 1):
        dias_acum = round(mes * DIAS_UTEIS_ANO / 12)
        bruto_mes = valor * (1 + taxa_dia_aplicada) ** dias_acum
        tabela.append(
            {
                "mes": mes,
                "dias_uteis": dias_acum,
                "bruto": round(bruto_mes, 2),
                "rendimento_bruto": round(bruto_mes - valor, 2),
            }
        )

    dias_corridos = meses * 30
    return {
        "valor": valor,
        "meses": meses,
        "pct_cdi": pct_cdi,
        "cdi_aa": cdi_aa,
        "dias_uteis": dias_uteis,
        "taxa_dia_pct": taxa_dia_aplicada * 100,
        "fator": fator,
        "rendimento_bruto": rendimento_bruto,
        "aliquota_ir": aliquota,
        "ir": ir,
        "rendimento_liquido": rendimento_liquido,
        "total_final": total_final,
        "rendimento_mensal_medio": rendimento_liquido / meses,
        "rentabilidade_pct": (total_final / valor - 1) * 100,
        "iof_relevante": dias_corridos <= 30,
        "tabela": tabela,
    }
