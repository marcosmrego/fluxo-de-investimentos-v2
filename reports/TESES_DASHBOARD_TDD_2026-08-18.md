# Evidência TDD — teses da carteira no dashboard

## Jornada

Como investidor, quero visualizar todas as posições reais em uma fila de teses, para revisar a carteira inteira e validar o processo sem esperar novas compras.

## RED

`pytest -q tests\test_investment_memory.py tests\test_api.py tests\test_dashboard_theses.py`

Resultado: erro de importação de `create_initial_thesis_draft`, ainda inexistente.

## GREEN

- Testes direcionados: 23 aprovados.
- Suíte completa: 58 aprovados, 1 aviso externo de depreciação.
- PostgreSQL real após migração transacional: 40 posições abertas, 40 rascunhos persistidos como `ORIGEM_DESCONHECIDA`; CMIN3 ainda ausente.

## Garantias

| Garantia | Evidência | Resultado |
|---|---|---|
| Toda posição aberta recebe um rascunho reconstruído | `test_initial_draft_uses_only_position_classification_and_stays_incomplete` | PASS |
| Rascunho não conta como tese publicada | mesmo teste | PASS |
| Endpoint autenticado expõe inventário e cobertura | `test_thesis_inventory_endpoint_returns_real_portfolio_coverage` | PASS |
| Dashboard possui aba Teses e decisões | `test_dashboard_has_theses_and_decisions_tab` | PASS |
| Aba carrega `/api/teses/inventario` e renderiza cobertura | `test_theses_tab_loads_real_inventory_endpoint_and_renders_coverage` | PASS |

## Limites conscientes

- Os rascunhos são persistidos e possuem campos separados para sugestão e tese revisada.
- Nenhum rascunho é apresentado como justificativa original ou recomendação.
- CMIN3 será vinculada como decisão contemporânea depois que a operação entrar e houver persistência versionada.
- Identidade continua consolidada por ticker até a ADR de instrumento, conta e carteira.

## Revisão adversarial

A primeira revisão rejeitou a geração efêmera de `TESE_ATUAL_RECONSTRUIDA`. A correção adicionou `migrations/20260818_investment_theses.sql`, semeou somente `ORIGEM_DESCONHECIDA` e fez o endpoint carregar registros estáveis. Sugestões não contam como teses publicadas.
