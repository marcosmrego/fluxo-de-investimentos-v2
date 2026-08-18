# Evidência TDD — propostas automáticas de tese

## Jornada

Como investidor, quero abrir uma posição e receber a ficha previamente preenchida com os fundamentos do sistema, para revisar evidências em vez de redigir a análise do zero.

## RED e GREEN

- RED: importação de `generate_fundamental_proposal` falhou antes da implementação.
- GREEN direcionado: 38 testes aprovados.
- GREEN completo: 78 testes aprovados, 1 aviso externo.
- Validação PostgreSQL real após revisão: BBAS3 e HGLG11 receberam confiança moderada porque os dados têm 17 dias; lacunas foram listadas por classe. SPXB11 declarou análise fundamental não suportada para ETF e confiança baixa.

## Garantias

| Garantia | Resultado |
|---|---|
| Proposta usa somente métricas estruturadas disponíveis | PASS |
| Números exibidos possuem data de evidência | PASS |
| Ausência de fundamentos reduz confiança e aparece como lacuna | PASS |
| Texto não contém instrução de compra ou venda | PASS |
| Formulário recebe resumo, horizonte, riscos e gatilhos automaticamente | PASS |
| Falha da proposta mantém o rascunho básico como fallback | PASS |
| Confiança considera cobertura, classe do ativo e idade dos dados | PASS |
| Respostas atrasadas não podem preencher o formulário de outro ticker | PASS |

## Arquitetura

Esta é a camada determinística e reproduzível. Uma futura camada de IA poderá enriquecer contexto e narrativa, mas deverá citar esses inputs, preservar a data e nunca substituir números ou publicar sem revisão explícita.
