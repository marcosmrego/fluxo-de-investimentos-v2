# Histórico do projeto — 18/08/2026

## Decisão de produto

O sistema passou a ser tratado como memória pessoal e motor de decisões para toda a carteira. CMIN3 foi definida como primeira decisão contemporânea, enquanto posições anteriores recebem origem desconhecida ou tese atual reconstruída, sem fabricação de justificativas históricas.

## Entregas do dia

- Blueprint estratégico do core de inteligência.
- Domínio de memória de investimentos e classificação de origem.
- Inventário persistente das 40 posições abertas.
- Aba **Teses e decisões**.
- Ficha de revisão e publicação da versão 1.
- Imutabilidade de conteúdo publicado no PostgreSQL.
- Propostas automáticas usando fundamentos estruturados.
- Confiança condicionada por classe, cobertura e idade dos dados.
- Motor diário determinístico de monitoramento.
- Histórico idempotente em `investimentos.monitoramentos_tese`.
- Job de cron programado após a atualização de cotações.

## Estado operacional ao encerrar

- 40 posições inventariadas.
- CMIN3 ainda não consta nas posições importadas.
- BBAS3 possui tese atual reconstruída publicada.
- Primeiro monitoramento real de BBAS3: `BASELINE_CRIADO` em 18/08/2026.
- Snapshot inicial: preço, variação diária, P/L, P/VP, ROE, ROIC, dívida/patrimônio, DY e idade dos dados.
- Segunda execução no mesmo dia: zero avaliações, confirmando idempotência.
- Migrações de teses, imutabilidade e monitoramento aplicadas ao PostgreSQL.

## Regras do monitor v1

- Execução após o fechamento em dias úteis.
- Dados com mais de 30 dias ou preço ausente: `DADOS_INSUFICIENTES`.
- Preço desde a tese: gatilho em ±15%.
- Variação diária: gatilho em ±5%.
- P/L, P/VP, dívida/patrimônio e DY: mudança relativa de 20%, somente com valores positivos comparáveis.
- ROE e ROIC: mudança de 3 pontos percentuais.
- Revisão periódica: FII/renda fixa 30 dias; ação/BDR/REIT 90; ETF 180.
- Pequenas mudanças ficam como `SEM_MUDANCA_MATERIAL`.

## Garantias verificadas

- 86 testes aprovados; 1 aviso externo de depreciação.
- `git diff --check` aprovado.
- Publicação PostgreSQL testada com rollback.
- Conteúdo publicado protegido por trigger.
- Job real executado e histórico confirmado.

## Limitações conscientes do monitor v1

- Gatilhos escritos em linguagem natural ainda não são convertidos automaticamente em regras estruturadas.
- Peso/concentração, proventos e eventos corporativos ainda não entram no motor.
- O job está descrito no arquivo de cron do repositório; a instalação desse arquivo no host acompanha o processo operacional de deploy.
- Revisar uma tese publicada e criar versão 2 ainda será implementado.
- A camada narrativa de IA ainda não existe; as propostas atuais são determinísticas e reproduzíveis.

## Próxima retomada

1. Confirmar importação de CMIN3 e vincular as 10 ações à decisão de 18/08/2026.
2. Exibir histórico e alertas do monitor na aba Teses e decisões.
3. Estruturar gatilhos personalizados, peso/concentração, proventos e eventos.
4. Implementar revisão com versão 2 e cadeia de substituição.
5. Adicionar narrativa de IA com evidências, sem alterar os cálculos determinísticos.
