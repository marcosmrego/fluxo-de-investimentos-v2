# Blueprint — Core de Inteligência para Decisões de Investimento

**Data:** 2026-08-18  
**Objetivo:** evoluir o sistema atual para uma memória de investimento pessoal, auditável e explicável, capaz de apoiar decisões antes, durante e depois de cada aporte.  
**Princípio de produto:** construir primeiro para uso próprio; conteúdo público, assinatura e monetização só entram depois que o core provar utilidade e confiabilidade.

## 1. Norte estratégico

O produto não deve responder apenas “quanto a carteira rendeu?”. Ele deve responder, com dados preservados no tempo:

1. O que eu sabia quando analisei ou comprei este ativo?
2. Qual era a tese, quais eram os riscos e quais cenários considerei?
3. Como a compra alteraria minha carteira antes de executá-la?
4. O que mudou desde a decisão?
5. A tese foi confirmada, invalidada ou continua inconclusiva?
6. Em quais tipos de decisão eu historicamente acerto ou erro?

### Proposta de valor inicial

> “Antes de comprar, registrar e comparar alternativas. Depois de comprar, acompanhar a tese e aprender com o resultado.”

### Resultado esperado em 12 meses

- Toda decisão relevante possui um snapshot imutável dos dados e da justificativa.
- A carteira possui performance, fluxos e proventos auditáveis.
- Uma nova compra pode ser simulada contra concentração, risco, liquidez e alocação-alvo.
- CMIN3 e outros ativos de interesse possuem tese versionada, cenários e eventos de revisão.
- Scores são reproduzíveis e explicáveis; nenhuma nota depende de texto gerado por IA.
- O sistema mede resultados contra benchmarks e contra as premissas originais.

### Estratégia de adoção: carteira inteira desde o início

CMIN3 será o primeiro caso com decisão e execução contemporâneas, mas não o único ativo do piloto. Todas as posições abertas entram desde o primeiro ciclo, com uma distinção obrigatória:

- **Tese contemporânea:** registrada antes ou no momento da decisão, com snapshot completo disponível naquela data.
- **Tese atual reconstruída:** fotografia da visão atual sobre uma posição antiga; não pode ser apresentada como justificativa original da compra.
- **Origem desconhecida:** quando não houver evidência suficiente, o sistema preserva explicitamente a lacuna em vez de inventar uma narrativa.

Assim, a carteira inteira recebe cobertura, qualidade, tese atual, riscos, horizonte e gatilhos de revisão desde cedo. Apenas decisões novas — começando pela compra de CMIN3 em 18/08/2026 — terão histórico integral desde a origem.

## 2. Diagnóstico do sistema atual

### Ativos já aproveitáveis

- PostgreSQL como base central.
- Pipeline local e fail-closed para notas de negociação da XP.
- Posições, operações, cotações, indicadores e proventos por cota.
- FastAPI e dashboard web próprio.
- Suporte inicial a múltiplas moedas.
- Indicador explicável de saúde da carteira.
- Migração já desenhada para fluxos de caixa, custódia diária, performance TWR e proventos recebidos.
- Testes para parser, segurança de dados, API, métricas e dashboard.

### Limitações que impedem decisões confiáveis

- Histórico de rentabilidade reconstruído com posições atuais; não é performance auditável.
- Proventos por cota não equivalem a caixa efetivamente recebido.
- Livro fiscal ainda não suporta apuração real.
- Cobertura e frescor dos dados podem deixar KPIs incompletos.
- Indicadores vêm de scrapers e ainda não têm contrato formal de procedência/qualidade.
- O plano antigo descreve Streamlit, mas a implementação real usa FastAPI + JavaScript.
- Não existem entidades formais para tese, decisão, cenário, snapshot ou revisão.
- O teste local atualmente falha na coleta por resolução de imports; o ambiente de testes precisa ser normalizado.
- A migração `scripts/migrate_auditable_history.sql` é um protótipo de modelagem, não uma migração pronta para aplicação: ainda não contempla conta, carteira, moeda, instrumento canônico, idempotência não nula ou linhagem de cálculo.

## 3. Arquitetura-alvo

```text
Fontes oficiais/corretora/mercado
             |
             v
     Ingestão + reconciliação
             |
             v
  Dados canônicos e temporais  ---> Qualidade, procedência e frescor
             |
             +-------------------------------+
             |                               |
             v                               v
  Performance da carteira          Inteligência por ativo
  fluxos, custódia, TWR             fundamentos, risco, valuation
             |                               |
             +---------------+---------------+
                             v
                   Motor de decisão
             tese + cenários + snapshot
                             |
                +------------+------------+
                v                         v
        Simulador de aporte         Revisão da tese
                |                         |
                +------------+------------+
                             v
                    Memória e aprendizado
                             |
                             v
                 IA para consulta e explicação
```

### Regra arquitetural central

O cérebro é composto por dados versionados, fórmulas, regras, evidências e histórico. A IA pode pesquisar, resumir, comparar e explicar, mas não altera fatos, scores ou decisões sem deixar fonte, versão e trilha de auditoria.

### Domínios recomendados

1. **Ledger:** operações, taxas, impostos, eventos corporativos e fluxos de caixa.
2. **Portfolio:** custódia temporal, custo, exposição, performance e benchmarks.
3. **Market Data:** instrumentos, cotações, câmbio, fundamentos, proventos e macro.
4. **Research:** teses, premissas, catalisadores, riscos, cenários e evidências.
5. **Decision:** intenção, alternativas, simulação, decisão executada e vínculo com operações.
6. **Evaluation:** revisões, desfecho, atribuição de resultado e padrões pessoais.

### Contrato temporal e de procedência

Para provar “o que era conhecido”, cada fato de mercado deve distinguir `effective_at` (quando o fato produz efeito econômico), `published_at` (quando a fonte o publicou), `observed_at` (quando o sistema pôde observá-lo), `ingested_at` (quando foi persistido) e `superseded_at` (quando uma correção o substituiu). Dados brutos são append-only e guardam fonte, licença/finalidade permitida, versão do coletor/parser, unidade, moeda e hash do conteúdo. Snapshots referenciam as versões usadas; não consultam retroativamente apenas “o último valor”.

Antes de armazenar documentos ou evidências, o sistema também deve possuir classificação de sensibilidade, retenção mínima, segregação de roles, gestão de segredos, backup e teste periódico de restauração. Uma fonte sem direito claro de redistribuição nunca pode alimentar diretamente um produto público.

## 4. Modelo mínimo da memória de investimento

As tabelas abaixo são conceituais; nomes e tipos finais devem ser definidos em ADR antes da migração.

| Entidade | Conteúdo essencial | Invariante |
|---|---|---|
| `research_thesis` | ativo, horizonte, estado, tese resumida, autor | possui versão atual, mas versões antigas não são sobrescritas |
| `thesis_version` | premissas, riscos, catalisadores, critérios de invalidação | imutável após publicação |
| `scenario` | pessimista/base/otimista, probabilidades, drivers, faixa de valor | probabilidades documentadas e metodologia identificada |
| `analysis_snapshot` | preço, fundamentos, macro, carteira, IDs/versões das fontes e qualidade dos dados | representa exatamente o conjunto observável pelo sistema no instante registrado |
| `decision` | comprar/não comprar/esperar/vender, valor, justificativa | referencia snapshot e versão da tese |
| `decision_alternative` | ativos ou uso de caixa comparados | preserva alternativas rejeitadas e motivo |
| `decision_execution` | vínculo entre intenção e operações efetivas | reconcilia quantidade, preço, taxas e data |
| `thesis_review` | evento, mudança, conclusão e próximo gatilho | nunca reescreve a tese original |
| `score_run` | versão do modelo, inputs, subnotas, nota e confiança | reproduzível a partir dos inputs armazenados |

O estado deve ser separado em três eixos: ciclo de vida (`RASCUNHO`, `ATIVA`, `ENCERRADA`), revisão (`EM_DIA`, `REVISAO_PENDENTE`, `EM_REVISAO`) e desfecho (`INCONCLUSIVO`, `CONFIRMADO`, `PARCIALMENTE_CONFIRMADO`, `INVALIDADO`).

## 5. Opportunity Score: quando e como introduzir

O score não deve ser a primeira entrega. Ele entra depois da base temporal e da qualidade dos dados.

### Estrutura inicial

| Pilar | Pergunta | Exemplos de insumos |
|---|---|---|
| Qualidade | O negócio é resiliente e rentável? | ROIC, margens, estabilidade, governança |
| Valuation | O preço remunera o risco? | múltiplos históricos/setoriais, DCF ou valor por cenários |
| Balanço | A estrutura financeira suporta o cenário adverso? | dívida, cobertura, liquidez, cronograma |
| Momentum operacional | Os fundamentos estão melhorando ou piorando? | receita, EBITDA, lucro, revisões |
| Risco | Qual é a dispersão dos resultados possíveis? | commodity, câmbio, concentração, volatilidade |
| Encaixe na carteira | Comprar melhora ou piora a carteira? | peso, correlação, setor, moeda, liquidez |

O sistema deve exibir nota por pilar, peso, dado usado, data, fonte, confiança e versão da fórmula. Um dado ausente reduz confiança; não deve virar zero silenciosamente. O score de oportunidade do ativo e o score de adequação à carteira devem permanecer separados.

## 6. Roadmap de construção

Cada etapa abaixo é um gate de capacidade. As unidades `A`, `B`, `C` etc. são PRs independentes; se uma unidade ainda não couber em uma PR, ela deve ser dividida antes da implementação, preservando seu critério de saída.

### Etapa 0 — Baseline executável, governança e início da memória da carteira

**Dependências:** nenhuma.  
**Objetivo:** fazer repositório, documentação e testes descreverem o mesmo sistema.

**Contexto frio:** a aplicação real é FastAPI + JavaScript; `PLANO_DASHBOARD.md` ainda descreve Streamlit. Em 2026-08-18, `pytest -q` falhou durante coleta porque `dashboard` e `scripts` não foram encontrados no path do ambiente local.

**Entregas:**

- **0A:** normalizar empacotamento/imports, fixar versão Python e criar comando único de teste a partir de clone limpo.
- **0B:** atualizar README, arquivar/substituir o plano antigo e registrar arquitetura/limitações reais.
- **0C:** criar CI e smoke test com PostgreSQL efêmero; nunca usar a base pessoal no CI.
- **0D:** ADR de migrations, IDs, conta, carteira, emissor, instrumento/listagem, moeda, unidade e temporalidade.
- **0E:** catálogo de fontes, licenças/finalidades, retenção, sensibilidade, SLA e política de correção.
- **0F:** contrato e registro manual da decisão CMIN3, com snapshot marcado `PARCIAL_NAO_AUDITADO`; não depende do ledger novo.
- **0H:** inventário de todas as posições abertas e classificação de cada uma como `TESE_CONTEMPORANEA`, `TESE_ATUAL_RECONSTRUIDA` ou `ORIGEM_DESCONHECIDA`.
- **0G:** threat model leve, roles, gestão de segredos e procedimento testado de backup/restore antes de guardar novas evidências sensíveis.

**Verificação:** `pytest -q`; compilação dos módulos Python; inicialização da API sem banco usando configuração de teste/mocks; `git diff --check`.

**Saída:** testes verdes a partir de um clone limpo, decisões arquiteturais registradas, compra de CMIN3 recuperável e inventário de toda a carteira classificado sem alegação de memória histórica inexistente.

**Rollback:** apenas documentação/configuração; reverter a PR.

### Etapa 1 — Ledger auditável e identidade canônica de instrumentos

**Dependências:** Etapa 0.  
**Objetivo:** estabelecer a verdade financeira antes de calcular inteligência.

**Contexto frio:** existe `migrate_auditable_history.sql`, mas o histórico atual não representa custódia passada; há risco de tickers órfãos e eventos corporativos não modelados.

**Entregas:**

- **1A:** inventariar o schema real e fechar ADR de identidade canônica, conta, carteira, moeda e temporalidade.
- **1B:** criar ingestão append-only e idempotente de operações XP sem trocar consumidores atuais.
- **1C:** criar replay de custódia para compras, vendas e taxas simples.
- **1D:** adicionar eventos corporativos em conjuntos pequenos e testáveis: desdobramento/grupamento; depois bonificação/subscrição; depois mudança de ticker.
- **1E:** produzir relatório de reconciliação e exceções explicadas.
- **1F:** trocar as leituras de posição para a projeção do ledger somente após o gate de reconciliação.

**Verificação:** testes de idempotência, replay, reconciliação e eventos corporativos; relatório JSON/SQL identifica universo, período, moeda, diferenças, tolerância e status `RECONCILED`, `EXPLAINED_EXCEPTION` ou `UNRESOLVED`. O cutover exige zero `UNRESOLVED` no universo escolhido e tolerância explícita por quantidade/moeda.

**Saída:** qualquer posição atual pode ser explicada por uma sequência de fatos imutáveis.

**Rollback:** migrações aditivas; manter leituras antigas até reconciliação completa.

### Etapa 2 — Performance, proventos e qualidade de dados

**Dependências:** Etapa 1.  
**Objetivo:** tornar confiáveis os KPIs que sustentam decisões e avaliações futuras.

**Entregas:**

- **2A:** definir taxonomia de fluxos externos/internos e suas regras de sinal.
- **2B:** materializar custódia e valuation diário com moeda/unidade explícitas.
- **2C:** implementar TWR por subperíodo com fixtures financeiras conhecidas.
- **2D:** calcular e reconciliar proventos recebidos com quantidade elegível e fonte preferencial da corretora.
- **2E:** adicionar benchmarks temporalmente alinhados e conversão cambial consistente.
- **2F:** criar contrato de cobertura, frescor, completude e reconciliação.
- **2G:** extrair SQL da API para uma fronteira de repositórios, introduzir feature flags reais e fazer cutover controlado dos endpoints/UI.

**Verificação:** casos sintéticos conhecidos para TWR; reconciliação de meses amostrados contra extratos; testes de moeda; contrato da API expondo confiança e data de corte.

**Saída:** dashboard de carteira confiável para patrimônio, retorno e renda passiva.

**Rollback:** cada cutover define endpoint, flag, consulta anterior e nova consulta; leituras antigas permanecem disponíveis com aviso explícito até a validação operacional.

### Etapa 3 — Teses, snapshots e diário de decisões da carteira inteira

**Dependências:** Etapa 0F para o diário manual; Etapa 2 apenas para vínculo automático e métricas confiáveis.  
**Objetivo:** entregar a primeira capacidade distintiva do produto.

**Entregas:**

- Criar esquema versionado de tese, cenários, snapshots, decisões, alternativas e revisões.
- Criar fluxo “Analisar ativo” validado primeiro com CMIN3 e aplicável a todas as posições abertas.
- Criar uma ficha mínima por posição: papel na carteira, tese atual, horizonte, riscos, catalisadores, critérios de saída/revisão, qualidade e origem da informação.
- Criar fila de saneamento para posições sem tese ou com dados insuficientes, priorizada por peso e risco na carteira.
- Registrar decisão `COMPRAR`, `ESPERAR`, `NÃO COMPRAR` ou `VENDER` e horizonte.
- Exigir riscos, catalisadores e critérios de invalidação antes de publicar uma tese.
- Permitir anexar evidências com fonte, data e trecho/resumo, preservando procedência.
- Exibir linha do tempo completa sem permitir edição destrutiva do passado.

**Verificação:** criar tese CMIN3, publicar versão, registrar decisão, alterar tese e provar que snapshot/decisão antigos permanecem iguais; gerar inventário de 100% das posições abertas, permitindo lacunas explícitas, e impedir que tese reconstruída seja exibida como contemporânea à compra.

**Saída:** o sistema responde “por que eu tomei esta decisão e com quais dados?”.

**Rollback:** tabelas e endpoints aditivos; desabilitar UI sem apagar histórico.

### Etapa 4 — Simulador de aporte e comparação de alternativas

**Dependências:** Etapas 2 e 3.  
**Objetivo:** apoiar a decisão antes da ordem ser enviada.

**Entregas:**

- Simular valor/quantidade e custos de uma compra.
- Mostrar carteira antes/depois: ativo, emissor, setor, classe, moeda e fatores de risco.
- Comparar CMIN3 com alternativas e com a opção de manter caixa.
- Definir limites pessoais e alocação-alvo versionados.
- Gerar checklist de decisão, sem enviar ordens à corretora.
- Vincular posteriormente a simulação à execução importada da nota.

**Verificação:** cenários determinísticos de aporte; soma dos pesos igual a 100%; decisão simulada reconcilia com execução real quando houver nota.

**Saída:** o sistema responde “o que esta compra muda e quais alternativas estou rejeitando?”.

**Rollback:** simulador somente leitura, sem impacto no ledger.

### Etapa 5 — Motor explicável de inteligência e Opportunity Score v1

**Dependências:** Etapas 2–4.  
**Objetivo:** priorizar investigação, não produzir recomendação automática.

**Entregas:**

- Definir metodologia versionada, pesos, normalização e tratamento de ausências.
- Separar `asset_opportunity_score` de `portfolio_fit_score`.
- Persistir cada execução com inputs e confiança.
- Criar decomposição visual e comparação histórica.
- Rodar shadow mode: score visível, mas sem orientar decisão por um período mínimo.
- Criar testes contra look-ahead bias e alterações retroativas de fonte.

**Verificação:** mesmo conjunto canônico de inputs produz o mesmo output dentro de tolerância decimal documentada; cada run guarda hash e ordem dos inputs, versão do código/modelo e regras de arredondamento; explicação de 100% da nota; backtest temporal usa `observed_at` para impedir dados futuros; revisão manual de amostra.

**Saída:** radar pessoal de 30–50 ativos com score explicável e nível de confiança.

**Rollback:** manter versões antigas da fórmula e retirar versão defeituosa da UI, sem apagar runs.

### Etapa 6 — Monitoramento de teses e revisões orientadas por eventos

**Dependências:** Etapas 3 e 5.  
**Objetivo:** reduzir esquecimento e viés de confirmação.

**Entregas:**

- **6A:** lembretes por data, dependentes apenas do diário de teses.
- **6B:** gatilhos por preço, resultado, dívida, dividendo e evento corporativo, dependentes de Market Data confiável.
- **6C:** gatilhos por valuation e score, dependentes da Etapa 5.
- Diff entre snapshot atual e snapshot da decisão.
- Alertas classificados por materialidade e qualidade da fonte.
- Fluxo de revisão: manter, reforçar, reduzir, invalidar ou encerrar.
- Registro explícito do que faria o investidor mudar de ideia.

**Verificação:** eventos sintéticos disparam apenas teses afetadas; alertas duplicados são idempotentes; revisão preserva histórico.

**Saída:** o sistema responde “o que mudou desde que comprei?”.

**Rollback:** desligar jobs/alertas; fatos e revisões permanecem armazenados.

### Etapa 7 — Avaliação das decisões e aprendizado pessoal

**Dependências:** Etapas 2, 3 e 6; precisa de tempo observado suficiente.  
**Objetivo:** medir processo e resultado sem confundir sorte com qualidade da decisão.

**Entregas:**

- Avaliar retorno total e relativo por horizonte predefinido.
- Classificar tese: confirmada, parcialmente confirmada, invalidada ou inconclusiva.
- Separar qualidade do processo do resultado financeiro.
- Agrupar resultados por setor, tipo de tese, horizonte, score, confiança e comportamento.
- Detectar padrões pessoais: entrar cedo, concentrar, vender cedo, ignorar invalidação.

**Verificação:** avaliação usa apenas snapshot disponível na decisão; benchmarks alinhados; decisões abertas não são tratadas como erro/acerto.

**Saída:** painel “meu histórico decisório” e revisão mensal/trimestral.

**Rollback:** relatórios derivados podem ser recalculados; fatos originais são imutáveis.

### Etapa 8 — Assistente conversacional com evidências

**Dependências:** Etapas 3–7.  
**Objetivo:** tornar o core consultável em linguagem natural sem entregar o controle à IA.

**Entregas:**

- Consultas como “por que comprei CMIN3?” e “o que mudou nesta semana?”.
- Respostas montadas sobre APIs/queries determinísticas e acompanhadas de fontes e datas.
- Política de não recomendação, limites de confiança e logs de consulta.
- Avaliações para alucinação, omissão de riscos e fidelidade aos snapshots.
- Nenhuma escrita no ledger ou decisão sem confirmação explícita.

**Verificação:** conjunto de perguntas douradas; toda afirmação quantitativa rastreia a um registro; testes adversariais de prompt injection em fontes externas.

**Saída:** analista pessoal explicável sobre a memória estruturada.

**Rollback:** desligar camada conversacional sem afetar nenhuma capacidade determinística.

## 7. Dependências e paralelismo

```text
Etapa 0
   +--> 0F CMIN3 + 0H Inventário da carteira --> 3A/6A
   |
   +--> Etapa 1 --> Etapa 2 --> Etapa 4 --> Etapa 5 --> 6C
                         |          |          |
                         +------> 3 completo --+--> Etapa 7 --> Etapa 8
                         |
                         +------------------------> 6B
```

Após a Etapa 2, o trabalho de experiência do diário de decisões pode avançar em paralelo ao refinamento da metodologia de dados, desde que não compartilhe migrações ou contratos ainda instáveis. A avaliação histórica real (Etapa 7) não deve ser acelerada com dados retroativos inventados.

## 8. Cadência recomendada

### Horizonte 0–30 dias — confiança e primeira memória

- Concluir 0A–0H e 1A–1C; só avançar além disso se os gates passarem.
- Classificar `migrate_auditable_history.sql` como protótipo não aplicável e substituí-la por migrações aditivas derivadas do ADR.
- Registrar manualmente a decisão CMIN3 com snapshot parcial antes da UI completa.
- Inventariar todas as posições abertas e registrar uma tese atual mínima, ou marcar explicitamente a ausência de informação.

**Meta:** recuperar a decisão de CMIN3 com snapshot, tese, riscos e critérios de revisão, além de obter cobertura classificada de 100% das posições abertas.

### Horizonte 31–90 dias — decisão assistida

- Concluir performance/proventos confiáveis.
- Entregar diário de decisões e simulador de aporte.
- Definir política pessoal de alocação e limites.
- Iniciar score v1 em shadow mode.

**Meta:** usar o sistema antes de 100% dos novos aportes relevantes.

### Horizonte 3–6 meses — acompanhamento e calibração

- Automatizar revisões por eventos.
- Acompanhar de 10 a 20 teses e radar de 30 a 50 ativos.
- Calibrar score sem trocar fórmula frequentemente.
- Iniciar avaliação do processo em janelas curtas, marcada como preliminar.

**Meta:** reduzir decisões sem tese registrada e alertas irrelevantes.

### Horizonte 6–12 meses — aprendizado e IA

- Consolidar avaliação das decisões.
- Implantar assistente conversacional baseado em evidências.
- Decidir, com uso real, se alguma camada deve virar produto público.

**Meta:** demonstrar que o sistema mudou pelo menos uma decisão ou evitou um erro de forma documentada.

## 9. Métricas de sucesso

### Confiabilidade

- 100% das posições dentro do universo e período declarados estão `RECONCILED` ou `EXPLAINED_EXCEPTION`; nenhuma `UNRESOLVED` participa de cutover silencioso.
- Todo KPI em produção exibe data de corte, cobertura e confiança, com contrato automatizado por endpoint.
- 0 reprocessamentos duplicando fatos financeiros.
- 100% dos scores reproduzíveis por versão.

### Adoção pessoal

- Percentual de aportes relevantes precedidos por simulação e decisão registrada.
- Percentual de posições com tese atual, origem classificada e critério de invalidação; lacunas explícitas contam como inventariadas, mas não como teses completas.
- Revisões vencidas e tempo até revisão após evento material.
- Número de alternativas efetivamente comparadas por decisão.

### Qualidade decisória

- Aderência ao processo, medida separadamente do retorno.
- Retorno total e relativo por tese/horizonte, somente quando maturado.
- Frequência de violações de limites pessoais.
- Erros identificados pelo post-mortem e correções de processo adotadas.

### Critério para monetização futura

Só avaliar produto público quando houver uso recorrente por pelo menos 3 meses, dados confiáveis segundo os gates deste plano, metodologia documentada e evidência de que a ferramenta melhora o processo. Antes de alertas personalizados, relatórios pagos ou scores públicos, realizar análise jurídica/regulatória específica sobre CVM, proteção de dados e direitos de uso/redistribuição das fontes.

## 10. Decisões que não devem ser tomadas agora

- Não escolher preço de assinatura ou estratégia de conteúdo antes de validar o core pessoal.
- Não prometer “preço justo” único para negócios cíclicos; usar cenários e intervalos.
- Não automatizar ordens de compra/venda.
- Não treinar modelo preditivo com histórico insuficiente.
- Não preencher lacunas com dados sintéticos sem rótulo explícito.
- Não transformar Opportunity Score em recomendação disfarçada.
- Não expandir para dezenas de fontes antes de medir qualidade e procedência das atuais.

## 11. Anti-padrões a evitar

- **Dashboard primeiro:** telas bonitas sobre dados não auditáveis.
- **Score mágico:** nota sem fórmula, fonte, versão ou confiança.
- **IA como banco de dados:** fatos financeiros vivendo apenas em texto gerado.
- **Look-ahead bias:** avaliar uma decisão com informação posterior fingindo que era conhecida.
- **Backfill criativo:** inventar posição, provento recebido ou justificativa passada.
- **Tese reescrita:** alterar a justificativa antiga para parecer correta depois do resultado.
- **Métrica sem unidade:** misturar percentual, múltiplo, moeda e valor por cota.
- **Fonte única frágil:** depender de scraper sem monitoramento, contrato e fallback.
- **Precisão falsa:** probabilidades e fair value com casas decimais sem sustentação.
- **Monetização prematura:** criar obrigações regulatórias e operacionais antes do valor pessoal estar provado.

## 12. Protocolo de mutação do plano

Este blueprint é versionado, não rígido.

1. Toda mudança registra motivo, evidência e impacto nas dependências.
2. Uma etapa pode ser dividida quando não couber em uma PR; seus critérios de saída permanecem.
3. Uma etapa só pode ser pulada se seu resultado já existir e houver evidência verificável.
4. Mudanças de schema ou metodologia exigem ADR e plano de migração/reprocessamento.
5. O roadmap é revisto mensalmente; as métricas e invariantes não mudam apenas para acomodar resultado ruim.
6. Funcionalidades públicas permanecem fora do caminho crítico até o gate de monetização.

## 13. Próxima decisão recomendada

Abrir a **Etapa 0** como próxima unidade de execução e escrever dois contratos complementares: o registro de decisão contemporânea usando CMIN3 e o inventário inicial de todas as posições abertas.

Para cada posição existente, registrar:

- ticker/instrumento e peso atual;
- data de entrada conhecida ou `DESCONHECIDA`;
- classificação da origem da tese;
- papel esperado na carteira;
- tese atual e horizonte;
- riscos, catalisadores e critérios de revisão;
- qualidade, cobertura e data dos dados;
- prioridade de saneamento por peso e risco.

Para CMIN3, adicionalmente registrar:

- data e preço observados;
- valor pretendido e horizonte;
- tese e premissas;
- riscos, catalisadores e critérios de invalidação;
- cenários pessimista/base/otimista;
- alternativas comparadas, inclusive manter caixa;
- impacto simulado na carteira;
- data/gatilho da próxima revisão;
- fontes e qualidade dos dados.

Esse contrato será o teste de aceitação da memória de investimento e evitará que a modelagem seja guiada apenas por tabelas genéricas.
