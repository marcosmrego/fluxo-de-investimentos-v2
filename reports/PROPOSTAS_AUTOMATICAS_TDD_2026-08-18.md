# Evidência TDD — propostas automáticas de tese

## Jornada

Como investidor, quero abrir uma posição e receber a ficha previamente preenchida com os fundamentos do sistema, para revisar evidências em vez de redigir a análise do zero.

## RED e GREEN

- RED: importação de `generate_fundamental_proposal` falhou antes da implementação.
- GREEN direcionado: 38 testes aprovados.
- GREEN completo: 76 testes aprovados, 1 aviso externo.
- Validação PostgreSQL real: BBAS3 e CMIG4 geraram propostas de confiança alta com dados de 01/08/2026; SPXB11 declarou fundamentos ausentes e confiança baixa.

## Garantias

| Garantia | Resultado |
|---|---|
| Proposta usa somente métricas estruturadas disponíveis | PASS |
| Números exibidos possuem data de evidência | PASS |
| Ausência de fundamentos reduz confiança e aparece como lacuna | PASS |
| Texto não contém instrução de compra ou venda | PASS |
| Formulário recebe resumo, horizonte, riscos e gatilhos automaticamente | PASS |
| Falha da proposta mantém o rascunho básico como fallback | PASS |

## Arquitetura

Esta é a camada determinística e reproduzível. Uma futura camada de IA poderá enriquecer contexto e narrativa, mas deverá citar esses inputs, preservar a data e nunca substituir números ou publicar sem revisão explícita.
