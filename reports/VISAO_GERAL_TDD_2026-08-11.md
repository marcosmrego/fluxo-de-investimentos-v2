# Evidência TDD — visão geral anual

## Jornada

Como investidor, quero comparar a evolução anual do patrimônio com a
diversificação atual na mesma linha, para entender tendência e composição sem
trocar de contexto.

## Garantias

| Garantia | Teste | Resultado |
|---|---|---|
| Evolução e diversificação compartilham a mesma grade | `test_overview_places_evolution_and_diversification_side_by_side` | PASS |
| A evolução consulta 365 dias, consolida o fechamento mensal e usa barras | `test_overview_evolution_is_annual_monthly_bar_chart` | PASS |
| A grade usa proporção 2:1 e mantém o empilhamento responsivo existente | `test_overview_charts_stack_on_smaller_screens` | PASS |

## Evidência

- RED: 3 falhas antes da implementação.
- GREEN relevante: 3 testes aprovados.
- GREEN completo: 34 testes aprovados, 1 aviso de depreciação externo.
