# Evidência TDD — parser XP fail-closed

Data: 19/08/2026

## Jornada

Como responsável pela carteira, quero que uma nota XP incompleta ou ambígua seja rejeitada, para que nenhuma posição seja atualizada a partir de operações perdidas ou tickers adivinhados.

## RED

- Primeiro ciclo: `python -m pytest tests/test_xp_note_parser.py -q` — 9 falhas e 17 testes aprovados.
- Revisão: foram encontrados caminhos adicionais de perda silenciosa.
- Segundo ciclo: mesmo comando — 5 falhas e 26 testes aprovados.
- Caso adicional de perda simultânea de C/V e descrição — 1 falha isolada.
- Correção de Marcopolo ON: 1 falha, pois o código retornava `POMO4` em vez de `POMO3`.

As falhas reproduziram ausência de C/V, linha financeira parcial, reconciliação opcional, mapeamentos ambíguos e classe incorreta de Marcopolo.

## GREEN

- `python -m pytest tests/test_xp_note_parser.py -q -p no:cacheprovider` — 32 testes aprovados.
- `python -m pytest -q --basetemp .tmp/pytest-parser-remediation -p no:cacheprovider` — 105 testes aprovados, 1 aviso não bloqueante.
- `git diff --check` — aprovado.

## Garantias

| Garantia | Evidência | Tipo | Resultado |
|---|---|---|---|
| Linhas plausíveis sem C/V não são ignoradas | `tests/test_xp_note_parser.py` | Unidade | PASS |
| Perdas parciais de campos em linhas financeiras abortam a nota | `tests/test_xp_note_parser.py` | Unidade | PASS |
| Importação de PDF exige resumo financeiro extraível | `tests/test_xp_note_parser.py` | Integração simulada | PASS |
| Total líquido extraído reconcilia com compras e vendas | `tests/test_xp_note_parser.py` | Unidade | PASS |
| Texto extraído é preservado para auditoria | `tests/test_xp_note_parser.py` | Unidade | PASS |
| Palavras genéricas não resolvem ticker | `tests/test_xp_note_parser.py` | Unidade | PASS |
| Descrições conhecidas resolvem CMIN3, MXRF11, BBAS3, ABCB4 e POMO3 corretamente | `tests/test_xp_note_parser.py` | Unidade | PASS |
| Descrição desconhecida permanece sem ticker e é bloqueada antes da escrita | `tests/test_xp_note_parser.py` | Unidade | PASS |

## Limitações

- O PDF real da nota `142478229` não estava disponível neste ambiente.
- O teste da fronteira PDF usa um documento `pdfplumber` simulado; ele prova o fail-closed e a ligação entre camadas, não a fidelidade do layout real.
- A reconciliação atual usa o total líquido. Operações completamente invisíveis à extração que se anulem exatamente continuam sendo um risco teórico; totais brutos e contagem de negócios devem ser incorporados em uma etapa posterior.
- O repositório não possui mecanismo seguro de substituição/replay de uma nota já processada. Reprocessar produção exige recuperar o anexo, validar em dry-run, criar backup e projetar reversão/replay transacional das posições.
- `pytest-cov` não está instalado; cobertura percentual não foi medida.
