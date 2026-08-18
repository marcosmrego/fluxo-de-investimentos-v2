# Evidência TDD — motor diário de teses

## Jornada

Como investidor, quero verificar diariamente as teses publicadas e receber revisão apenas quando houver gatilho material ou vencimento periódico.

## RED e GREEN

- RED: módulo `dashboard.thesis_monitoring` inexistente.
- GREEN focado: 8 testes aprovados.
- GREEN completo: 86 testes aprovados, 1 aviso externo.
- PostgreSQL: migration aplicada; primeiro baseline real criado para BBAS3.
- Idempotência: segunda execução em 18/08/2026 avaliou zero teses.

## Garantias

| Garantia | Resultado |
|---|---|
| Primeiro snapshot válido cria baseline | PASS |
| Preço ausente ou dados vencidos não criam baseline confiável | PASS |
| Comparação usa baseline fixo da tese | PASS |
| Mudanças materiais de preço e fundamentos recomendam revisão | PASS |
| Periodicidade varia por classe | PASS |
| Pequenas oscilações não geram ruído | PASS |
| Uma tese recebe no máximo um registro por dia | PASS |
| Datas usam America/Sao_Paulo | PASS |
