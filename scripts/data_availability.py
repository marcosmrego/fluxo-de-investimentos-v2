"""Contratos de disponibilidade para metricas que exigem dados auditaveis."""


def unavailable_tax_result() -> dict:
    return {
        "disponivel": False,
        "status": "indisponivel_sem_livro_fiscal",
        "motivo": (
            "Apuracao tributaria indisponivel ate existir um livro fiscal "
            "baseado em alienacoes realizadas e prejuizos acumulados por regime."
        ),
    }


def unavailable_passive_income_result() -> dict:
    return {
        "disponivel": False,
        "status": "indisponivel_sem_posicao_na_data_com",
        "motivo": (
            "Renda passiva indisponivel ate existir a quantidade detida "
            "na data-com de cada evento."
        ),
        "proventos_por_mes": [],
        "proventos_por_ativo": [],
    }
