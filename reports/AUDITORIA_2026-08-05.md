# Auditoria técnica e de dados — 2026-08-05

## Escopo e método

Auditoria somente de leitura da base PostgreSQL `carteira_investimentos`, revisão estática do repositório e execução dos testes locais. Nenhum registro da base foi alterado.

## Parecer executivo

O pipeline possui uma base estrutural útil e os principais conjuntos não apresentam duplicidades ou valores negativos inválidos. Entretanto, o sistema ainda não é auditável para performance, renda passiva ou apuração tributária. Há três bloqueadores: histórico reconstruído com posições atuais, proventos unitários tratados como caixa recebido e cálculo tributário baseado em ganhos/perdas não realizados.

## Achados críticos

### C1 — Histórico de patrimônio e rentabilidade não representa a carteira histórica

`scripts/backfill_historico.py` combina cada cotação passada com a posição e o custo atuais. Assim, aplica retroativamente a carteira de hoje a todas as datas. Os 136 registros de `rentabilidade_diaria` (2026-01-19 a 2026-07-31) são aritmeticamente consistentes com essa fórmula, mas não representam a evolução real do patrimônio ou da rentabilidade.

Impacto: gráficos históricos, variação patrimonial e qualquer tentativa de TWR não podem ser usados para avaliar performance.

Correção: reconstruir quantidades e custo por data a partir das operações, registrar aportes/retiradas e calcular snapshots por subperíodo. Preservar o conjunto atual apenas como série simulada, com nome explícito.

### C2 — Proventos por cota são somados como valores recebidos

`scripts/coletar_proventos.py` grava diretamente o valor fornecido pelo Yahoo, que é dividendo por ação/cota. O dashboard e os relatórios somam `proventos.valor` como se fosse caixa recebido. A base contém 228 eventos, cuja soma unitária é R$ 91,65 (R$ 11,58 em 2026), e não o total efetivamente recebido.

Impacto: proventos do mês/ano, renda passiva, média mensal e projeções estão conceitualmente incorretos.

Correção: separar `valor_por_cota` de `valor_recebido`; calcular o valor recebido usando a quantidade detida na data-com, incluindo eventos corporativos e posição histórica. Quando houver comprovante da corretora, tratá-lo como fonte preferencial.

### C3 — Módulo tributário trata perdas não realizadas como compensáveis

`scripts/relatorio_modulos/modulo_tributario.py` compara posição atual com cotação atual, chama a diferença de prejuízo compensável e calcula imposto sobre uma venda hipotética integral. A base não mantém um livro fiscal mensal completo nem prejuízos realizados acumulados por regime.

Impacto: os campos “IR devido”, “prejuízo compensável” e “economia fiscal” podem induzir decisão fiscal incorreta.

Correção: retirar a linguagem de imposto devido/compensação do relatório atual e classificá-lo apenas como cenário hipotético. Implementar livro fiscal baseado em alienações realizadas, custos/taxas, mês, modalidade e regime antes de reativar apuração tributária.

### C4 — Segredo e fluxo de documento sensível no código

`scripts/processar_nota_xp.py` contém senha de nota em texto claro (`XP_NOTAS_SENHA`) e possui fallback que procura senha de banco dentro de outro script. O PDF da nota de corretagem é enviado a uma API externa.

Impacto: exposição de segredo e de documento financeiro pessoal; dependência de caminhos específicos do servidor.

Correção: remover o segredo do código, rotacioná-lo quando aplicável, usar variável de ambiente/vault e eliminar a extração de credencial de arquivos de código. Documentar consentimento, retenção, transporte e operador da API externa antes de enviar novas notas.

## Achados altos

### A1 — Cobertura incompleta da carteira

- 35 posições abertas.
- 6 posições sem cadastro em `ativos`: `GARE12`, `IRIM11`, `RZTR11`, `SNEL11`, `TRXF11` e `XPML11`.
- 7 posições sem qualquer cotação: as seis acima e `MCHF11`.
- 9 posições sem indicadores fundamentalistas.
- R$ 902,15 de custo estão em posições sem cotação.

O KPI atual informa valor de mercado de R$ 31.894,87 e custo de R$ 32.996,85, mas atribui implicitamente valor zero às sete posições sem cotação. Isso distorce patrimônio, lucro/prejuízo e pesos.

Correção: cadastrar automaticamente novos tickers dentro da mesma transação da nota, distinguir direitos de subscrição como `GARE12`, ampliar a coleta e bloquear/rotular KPIs quando a cobertura não for completa.

### A2 — Dados de mercado defasados em relação às operações

A última operação é de 2026-08-04, enquanto cotações e snapshots terminam em 2026-07-31; indicadores terminam em 2026-08-01. Em 2026-08-05, todos os 28 tickers cobertos da carteira estão com cinco dias corridos de defasagem.

Correção: executar coleta após o fechamento, registrar status de cada execução e definir SLA de frescor. O dashboard deve exibir e validar a data usada em cada KPI.

### A3 — Integridade referencial incompleta

Há unicidade adequada nos conjuntos principais, mas `posicoes`, `cotacoes` e `proventos` não possuem chave estrangeira para `ativos.ticker`. Isso permitiu as posições órfãs encontradas.

Correção: resolver os órfãos e depois adicionar FKs ou adotar uma dimensão canônica de instrumentos que comporte ativos, índices, direitos e ativos internacionais.

## Achados médios

### M1 — Plano e implementação divergiram

`PLANO_DASHBOARD.md` descreve Streamlit/Plotly e TWR como pronto/baixo esforço; o código atual é FastAPI com JavaScript e declara corretamente TWR indisponível. Atualizar o documento para refletir a arquitetura real e os bloqueios de dados.

### M2 — Testes insuficientes

Os 3 testes existentes passam e todo o Python compila, mas apenas funções matemáticas simples são testadas. Não há testes do parser, atualização de posições, queries do dashboard, idempotência, proventos, tributação ou reconciliação ponta a ponta.

### M3 — Estatísticas do PostgreSQL defasadas

As estimativas de linhas em `pg_stat_user_tables` estavam muito abaixo das contagens reais em várias tabelas. Executar `ANALYZE` após cargas relevantes e monitorar autovacuum/analyze.

## Evidências positivas

- Conexão com PostgreSQL 17.9 validada.
- 17 tabelas no schema `investimentos`.
- 4.238 cotações sem duplicidade por ticker/data e sem preços de fechamento não positivos.
- 228 proventos sem duplicidade pela chave atual e sem valores não positivos.
- 35 posições sem duplicidade, negativas ou preço médio inválido.
- 106 operações sem ticker ausente e com `quantidade × preço = valor`.
- Operações brutas reconciliam com `operacoes_consolidadas_nota`.
- 136 snapshots sem duplicidade e internamente consistentes com a fórmula armazenada.
- Testes locais: 3 aprovados; compilação Python e `git diff --check` sem erro.

## Ordem recomendada

1. Desativar/renomear imediatamente os indicadores fiscais e de proventos recebidos.
2. Remover e rotacionar segredos; revisar o envio de PDFs à API externa.
3. Corrigir cadastro/cotação das sete posições e sinalizar cobertura nos KPIs.
4. Modelar posição histórica, eventos de caixa e livro fiscal.
5. Reconstruir snapshots e implementar TWR somente após o item 4.
6. Criar testes de integração e atualizar a documentação operacional.

## Limitações desta auditoria

Não foram alterados dados, executados coletores externos nem processadas notas reais. Não houve conciliação contra extratos oficiais da corretora, informe de rendimentos, custódia da B3 ou declaração fiscal; portanto, saldos e custos foram avaliados por consistência interna, não por confirmação externa.
