# Evidência TDD — suporte multimoeda

## Jornada

Como investidor, quero manter ativos internacionais em sua moeda de origem e
consolidá-los em BRL, para que o patrimônio não some dólares como reais.

## Garantias

| Garantia | Teste | Tipo | Resultado |
|---|---|---|---|
| O símbolo Yahoo é definido pela moeda do ativo | `test_yahoo_symbol_uses_b3_suffix` | Unitário | PASS |
| OHLC em USD é convertido para BRL e preserva preço original e câmbio | `test_usd_quotes_are_normalized_to_brl_and_keep_original_values` | Unitário | PASS |
| Ativos BRL permanecem com taxa 1 | `test_brl_quotes_do_not_require_exchange_rates` | Unitário | PASS |
| A migração adiciona moeda, valores originais e taxa de câmbio com defaults compatíveis | `test_currency_migration_preserves_brl_defaults_and_native_values` | Estrutural | PASS |

## Evidência RED/GREEN

- RED: 4 falhas — assinatura sem moeda, conversor ausente e migração ausente.
- GREEN relevante: `python -m pytest tests/test_atualizar_cotacoes.py tests/test_currency_schema.py -q` — 6 aprovados.
- A suíte completa será registrada no fechamento desta execução.

## Limite conhecido

O câmbio histórico de aquisição do Realty Income não foi informado. O custo em
BRL usa provisoriamente o câmbio atual, preservando o custo original de US$ 6,14
para correção futura.
