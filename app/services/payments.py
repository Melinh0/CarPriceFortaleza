from __future__ import annotations

METODOS = [
    {
        "id": "a-vista",
        "nome": "Pagamento à vista",
        "resumo": "Você paga o valor total do carro de uma só vez, sem juros.",
        "como_funciona": [
            "Negocie o preço final e peça o desconto por pagamento à vista.",
            "Confira se o desconto é válido para PIX, transferência ou cheque.",
            "Faça o sinal/entrada e o restante no ato da entrega, com recibo.",
            "Exija recibo e nota fiscal/fatura com o valor exato.",
        ],
        "vantagens": [
            "Sem juros e sem dívida ativa no CPF.",
            "Costuma render desconto adicional de 3% a 8% no preço.",
            "Compra mais rápida: sai da concessionária no mesmo dia.",
        ],
        "cuidados": [
            "Valores altos em PIX podem sofrer análise do banco (Origem dos Recursos).",
            "Não leve dinheiro vivo: use transferência com comprovante.",
            "Confirme se o desconto à vista é maior que o custo do financiamento.",
        ],
        "documentos": [
            "RG/CPF ou CNH",
            "Comprovante de residência recente",
            "Comprovante de renda (opcional à vista)",
            "Dados bancários para transferência",
        ],
    },
    {
        "id": "financiamento",
        "nome": "Financiamento bancário",
        "resumo": "O banco paga a concessionária e você devolve em parcelas, com o carro como garantia.",
        "como_funciona": [
            "Escolha o carro e defina a entrada (normalmente 20% a 30% do valor).",
            "A concessionária envia a proposta ao banco (Santander, Itaú, Bradesco, BV etc.).",
            "Você apresenta documentos e passa por análise de crédito.",
            "Aprovado: assina o contrato, paga a entrada e retira o carro.",
            "As parcelas são debitadas em conta; o veículo fica alienado ao banco até quitar.",
        ],
        "vantagens": [
            "Mantém o capital de giro: paga em 12 a 60 meses.",
            "Taxas de concessionária costumam ser competitivas (promocionais).",
            "Quitação antecipada gera economia de juros (confira multa).",
        ],
        "cuidados": [
            "Compare o CET (Custo Efetivo Total), não só a taxa de juros.",
            "IOF incide no financiamento; cheque o valor no contrato.",
            "Parcela ideal: até 25% da sua renda mensal.",
            "Evite estender o prazo demais: os juros superam o valor do carro.",
        ],
        "documentos": [
            "RG/CPF ou CNH",
            "Comprovante de residência",
            "3 últimos contracheques ou declaração de IR",
            "Extrato bancário dos últimos 3 meses",
        ],
    },
    {
        "id": "consorcio",
        "nome": "Consórcio",
        "resumo": "Grupo de compradores que paga mensalidades e recebe o carro por sorteio ou antecipação.",
        "como_funciona": [
            "Escolha a carta de crédito (ex.: R$ 120.000) e a administração (Banco do Brasil, Bradesco etc.).",
            "Pague as mensalidades fixas (parcela + taxa de administração + fundo reserva).",
            "Recebe o carro quando sorteado ou use a compra antecipada (PEAC).",
            "Pode dar lance de até 100% do valor para antecipar o sorteio.",
        ],
        "vantagens": [
            "Sem juros de banco: só taxa de administração.",
            "Boa alternativa para quem está juntando dinheiro.",
            "Modalidade de veículo novo ou usado.",
        ],
        "cuidados": [
            "Não é garantia de data: o sorteio é aleatório.",
            "Lance e atraso encarecem o custo final.",
            "Compare a taxa de administração entre administradoras.",
        ],
        "documentos": [
            "RG/CPF",
            "Comprovante de residência",
            "Comprovante de renda",
        ],
    },
    {
        "id": "troca",
        "nome": "Troca do usado (seminovo como parte do pagamento)",
        "resumo": "Você usa seu carro atual como parte do pagamento e complementa a diferença.",
        "como_funciona": [
            "Leve o carro à concessionária para vistoria e avaliação.",
            "Receba a proposta de lance (valor do seu usado) em desconto.",
            "Pague a diferença à vista ou financie só o valor restante.",
            "A transferência do usado é feita na mesma negociação.",
        ],
        "vantagens": [
            "Reduz o valor financiado e a parcela.",
            "Praticidade: resolve compra e venda em um lugar.",
            "Seminovos de concessionária têm garantia e revisão.",
        ],
        "cuidados": [
            "Avalie seu carro em 2 ou 3 lugares antes (Webmotors, iCarros, loja).",
            "Lance de concessionária costuma ser menor que venda direta.",
            "Confira se o desconto está no contrato, não só na conversa.",
        ],
        "documentos": [
            "Documentos do carro (CRLV, nota fiscal)",
            "RG/CPF dos dois lados",
            "Comprovante de residência",
        ],
    },
    {
        "id": "leasing",
        "nome": "Leasing / locação com opção de compra",
        "resumo": "Você 'aluga' o carro por um prazo e decide se compra ao final.",
        "como_funciona": [
            "Contrata o uso do veículo por 24 a 60 meses com parcelas fixas.",
            "Ao final, escolhe comprar o carro pelo valor residual, devolver ou trocar.",
            "O carro é da locadora durante o contrato; mantenha em dia as revisões.",
        ],
        "vantagens": [
            "Parcela menor que o financiamento tradicional.",
            "Flexibilidade para trocar de carro no fim do prazo.",
            "Ideal para uso empresarial (pode abater custos no CNPJ).",
        ],
        "cuidados": [
            "Valor residual pode ser alto: simule a compra final.",
            "Km excedente e danos geram multas.",
            "Leia as cláusulas de manutenção obrigatória.",
        ],
        "documentos": [
            "RG/CPF ou CNPJ",
            "Comprovante de renda/faturamento",
            "Comprovante de residência",
        ],
    },
]

GUIA_COMPRA = [
    {
        "titulo": "1. Defina o orçamento real",
        "descricao": "Considere preço à vista, financiamento, IPVA, seguro, manutenção e combustível. Regra prática: parcela do financiamento <= 25% da renda mensal.",
    },
    {
        "titulo": "2. Compare preços antes de ir",
        "descricao": "Use este sistema para levantar preços de anúncios, comentários de donos e a faixa de mercado do modelo escolhido.",
    },
    {
        "titulo": "3. Agende o test drive",
        "descricao": "Ligue para a concessionária de Fortaleza, confirme o estoque e marque um test drive. Ande em ruas ruins para ouvir suspensão e freios.",
    },
    {
        "titulo": "4. Peça a proposta por escrito",
        "descricao": "Com desconto à vista, valor do usado na troca, taxa do financiamento, CET, prazo, acessórios inclusos e prazo de entrega.",
    },
    {
        "titulo": "5. Documentação para pessoa física",
        "descricao": "RG/CPF, comprovante de residência, comprovante de renda, extrato bancário e, se trocar, documentos do carro usado (CRLV).",
    },
    {
        "titulo": "6. Analise crédito e assine o contrato",
        "descricao": "No financiamento, confira CET, IOF, parcelas, taxa de juros ao mês/ano e condições de quitação antecipada antes de assinar.",
    },
    {
        "titulo": "7. Pagamento e entrega",
        "descricao": "Faça o sinal com recibo, pague o restante por transferência e só retire o carro com recibo, nota fiscal e chave reserva.",
    },
    {
        "titulo": "8. Emplacamento e transferência",
        "descricao": "A concessionária costuma cuidar do emplacamento (CRV assinado, IPVA e taxa de transferência). Confira o CRLV em seu nome em até 30 dias.",
    },
]

DICAS_NEGOCIACAO = [
    "Leve a concorrência: cite preços de outras concessionárias da mesma marca em Fortaleza.",
    "Negocie o total, não a parcela: vendedores trabalham com margem na parcela.",
    "Peça os itens inclusos por escrito (piso, filme, capota, garantia estendida).",
    "Compre no fim do mês/semestre: metas de venda abrem espaço para desconto.",
    "Confira chassi, pintura, km e histórico do carro novo (lacre, transportadora).",
    "Nunca pague nada sem recibo assinado com valor, modelo e placa/chassi.",
]


def simulate_financing(preco: float, entrada: float, taxa_aa: float, meses: int) -> dict:
    if preco <= 0:
        raise ValueError("O preço do carro deve ser maior que zero.")
    if meses <= 0:
        raise ValueError("O prazo em meses deve ser maior que zero.")
    if entrada < 0:
        raise ValueError("A entrada não pode ser negativa.")
    if entrada >= preco:
        return {
            "preco": preco,
            "entrada": entrada,
            "financiado": 0.0,
            "taxa_aa": taxa_aa,
            "taxa_mes": 0.0,
            "meses": meses,
            "parcela": 0.0,
            "total_pago": preco,
            "juros": 0.0,
            "entrada_pct": (entrada / preco) * 100,
        }

    financiado = preco - entrada
    taxa_mes = (1 + taxa_aa / 100) ** (1 / 12) - 1

    if taxa_aa <= 0:
        parcela = financiado / meses
    else:
        parcela = financiado * taxa_mes / (1 - (1 + taxa_mes) ** (-meses))

    total_pago = entrada + parcela * meses
    juros = total_pago - preco

    return {
        "preco": preco,
        "entrada": entrada,
        "financiado": financiado,
        "taxa_aa": taxa_aa,
        "taxa_mes": taxa_mes * 100,
        "meses": meses,
        "parcela": parcela,
        "total_pago": total_pago,
        "juros": juros,
        "entrada_pct": (entrada / preco) * 100,
    }
