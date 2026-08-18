# Evidência TDD — revisão e publicação de teses

## Jornada

Como investidor, quero revisar um rascunho e publicar sua primeira versão, para transformar sugestões da carteira em teses humanas acompanháveis.

## RED

`pytest -q tests\test_investment_memory.py tests\test_api.py tests\test_dashboard_theses.py`

Resultado: `ImportError` para `validate_thesis_publication`, ainda inexistente.

## GREEN

- Testes direcionados: 33 aprovados.
- Suíte completa: 70 aprovados, 1 aviso externo de depreciação.
- `git diff --check`: aprovado.

## Garantias

| Garantia | Evidência | Resultado |
|---|---|---|
| Publicação exige origem humana válida, resumo, horizonte, riscos e gatilhos | testes `test_*thesis_publication*` | PASS |
| Tese contemporânea exige data da decisão e limite temporal | `test_contemporary_publication_requires_decision_timestamp` e domínio existente | PASS |
| Endpoint autenticado publica somente rascunho existente | `test_publish_thesis_endpoint_validates_and_persists_review` e `UPDATE ... WHERE status = 'RASCUNHO'` | PASS |
| Tela possui formulário de revisão e envia POST JSON | `test_theses_tab_has_review_dialog_and_publishes_versioned_thesis` | PASS |
| Nenhum rascunho é publicado automaticamente | fluxo exige submissão explícita do formulário | PASS |

## Limites

- Este incremento publica a versão 1; edição de uma tese já publicada e cadeia de substituição serão um incremento posterior.
- CMIN3 ainda não consta nas posições importadas e não foi criada artificialmente.
- O formulário é de uso pessoal e permanece protegido pela autenticação existente do dashboard.
