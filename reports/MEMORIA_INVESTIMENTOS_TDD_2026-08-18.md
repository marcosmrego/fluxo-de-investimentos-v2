# Evidência TDD — inventário inicial da memória de investimentos

## Fonte

Estratégia: `plans/estrategia-core-inteligencia-investimentos.md`.

## Jornada

Como investidor, quero inventariar todas as posições abertas e distinguir teses contemporâneas, reconstruídas e desconhecidas, para começar a memória da carteira sem inventar justificativas históricas.

## RED

Comando: `pytest -q tests\test_investment_memory.py`

Resultado antes da implementação: erro de coleta `ModuleNotFoundError: No module named 'dashboard.investment_memory'`. O teste referenciou o novo domínio ainda inexistente.

## GREEN

Comandos executados:

- `pytest -q tests\test_investment_memory.py` — 5 testes aprovados.
- `pytest -q` — 45 testes aprovados, 1 aviso externo de depreciação.

## Garantias

| Garantia | Teste | Tipo | Resultado |
|---|---|---|---|
| Toda posição aberta aparece no inventário e posição encerrada é excluída | `test_inventory_includes_every_open_position_and_marks_unknown_origins` | unitário | PASS |
| Ausência de tese vira lacuna explícita, nunca tese presumida | `test_inventory_includes_every_open_position_and_marks_unknown_origins` | unitário | PASS |
| Tese contemporânea e tese atual reconstruída permanecem distinguíveis | `test_inventory_distinguishes_contemporary_from_reconstructed_theses` | unitário | PASS |
| Tese contemporânea exige instante da decisão | `test_contemporary_thesis_requires_decision_timestamp` | unitário | PASS |
| Duas teses correntes para o mesmo ticker são rejeitadas | `test_inventory_rejects_duplicate_current_theses_for_the_same_ticker` | unitário | PASS |
| Classificação de origem desconhecida pelo domínio é rejeitada | `test_inventory_rejects_unknown_thesis_origin_instead_of_guessing` | unitário | PASS |

## Cobertura e lacunas

O ambiente não possui o plugin `pytest-cov`; por isso o comando de cobertura foi rejeitado e nenhum percentual foi inventado. Os cinco caminhos públicos introduzidos estão exercitados, incluindo sucesso, ausência e erros. Persistência, API e interface ainda não fazem parte deste incremento.

## Checkpoints

- RED: `2a62c16 test: definir memoria inicial da carteira`.
- GREEN: registrado no commit subsequente da implementação.
