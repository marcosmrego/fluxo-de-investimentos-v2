# Dashboard Independente — Plano de Implementação

> **Objetivo:** Substituir o Investidor10 por um dashboard web próprio, interativo,
> usando os dados que já temos no banco Postgres e os módulos de análise existentes.

**Stack:** Streamlit + Plotly + PostgreSQL + módulos Python existentes
**Tema:** CLEAN (claro) — fundo branco, cards #F6F8FA, accent #0969DA (preferência do Professor)

---

## Diagnóstico: O que já temos

| Recurso | Status | Detalhe |
|---------|--------|---------|
| Posições da carteira | ✅ Pronto | 29 ativos com preço médio, qtd, custo |
| Cotações diárias | ✅ Pronto | 3985 registros históricos |
| Proventos | ✅ Pronto | 225 registros com data, valor, tipo |
| Rentabilidade diária | ✅ Pronto | 129 dias com valor total, custo, lucro |
| Indicadores fundamentalistas | ✅ Pronto | P/L, P/VP, ROE, ROIC, margens, DY, CAGR |
| Notas de negociação (XP) | ✅ Pronto | Pipeline automático de importação |
| Alertas | ✅ Pronto | 56 alertas configurados |
| Análise fundamentalista | ✅ Pronto | Módulo com rankings e gráficos |
| Análise setorial | ✅ Pronto | Distribuição por setor |
| Análise tributária | ✅ Pronto | Módulo IR |
| Renda passiva | ✅ Pronto | Módulo de projeção |
| Benchmarking | ✅ Pronto | Comparação IBOV/IFIX/CDI |
| Risco | ✅ Pronto | Módulo de risco |
| Alocação IR | ✅ Pronto | Módulo de alocação |

## O que o Investidor10 tem e NÓS NÃO temos

| Funcionalidade | Prioridade | Esforço |
|----------------|-----------|---------|
| Interface web interativa | 🔴 P0 | Médio |
| Gráfico de evolução do patrimônio | 🔴 P0 | Baixo |
| Rentabilidade ponderada (TWR) | 🔴 P0 | Baixo |
| Tabela de posições com % carteira | 🔴 P0 | Baixo |
| Rebalanceamento (% ideal vs real) | 🟡 P1 | Médio |
| Metas financeiras com projeções | 🟡 P1 | Alto |
| Preço-alvo com alertas | 🟢 P2 | Médio |
| Preço-teto Bazin / Graham | 🟢 P2 | Baixo |
| Buy & Hold Score | 🟢 P2 | Médio |
| IRPF / DARFs | 🟢 P2 | Alto |

---

## Arquitetura

```
fluxo-de-investimentos-v2/
├── dashboard/
│   ├── app.py                  # Streamlit app principal (ponto de entrada)
│   ├── pages/
│   │   ├── 01_resumo.py        # Visão geral / KPIs
│   │   ├── 02_posicoes.py      # Tabela de ativos com filtros
│   │   ├── 03_proventos.py     # Histórico de dividendos
│   │   ├── 04_rentabilidade.py # Evolução + TWR
│   │   ├── 05_patrimonio.py    # Gráfico de evolução + diversificação
│   │   ├── 06_analise.py       # Dados fundamentalistas
│   │   ├── 07_rebalanceamento.py # % ideal vs real
│   │   └── 08_metas.py         # Metas financeiras (P1)
│   ├── components/
│   │   ├── cards.py            # KPI cards reutilizáveis
│   │   ├── charts.py           # Gráficos Plotly padronizados
│   │   ├── tables.py           # Tabelas formatadas
│   │   └── theme.py            # Design tokens (tema CLEAN)
│   └── data/
│       ├── queries.py          # Queries SQL reutilizáveis
│       └── metrics.py          # Cálculos (TWR, Bazin, Graham)
├── scripts/                    # Já existente — módulos de análise
└── PLANO_DASHBOARD.md          # Este arquivo
```

## Tema Visual (Design Tokens)

```css
--bg-primary:    #FAFBFC   (fundo da página)
--bg-card:       #FFFFFF   (fundo dos cards)
--border:        #D0D7DE   (bordas)
--text-primary:  #1F2328   (texto principal)
--text-muted:    #656D76   (texto secundário)
--accent:        #0969DA   (azul — links, ações)
--positive:      #1A7F37   (verde — ganho)
--negative:      #CF222E   (vermelho — perda)
--warning:       #9A6700   (amarelo — alerta)
```

---

## Fase 1 — Fundação (P0)

### Tarefa 1.1: Setup do projeto Streamlit

**Arquivos:**
- Criar: `dashboard/requirements.txt`
- Criar: `dashboard/app.py`
- Criar: `dashboard/components/theme.py`

**Dependências:** streamlit, plotly, pandas, psycopg2-binary

**Objetivo:** App Streamlit multi-página funcionando com tema CLEAN aplicado.

### Tarefa 1.2: Camada de dados

**Arquivos:**
- Criar: `dashboard/data/queries.py`
- Criar: `dashboard/data/metrics.py`

**Queries SQL a implementar:**
- `get_posicoes()` — posições atuais com cotação do dia
- `get_cotacoes_hist(ticker, dias)` — série histórica
- `get_proventos(ano, mes)` — proventos com filtros
- `get_rentabilidade_diaria()` — evolução diária
- `get_indicadores()` — dados fundamentalistas

**Cálculos:**
- TWR (Time-Weighted Return)
- Rentabilidade acumulada
- % na carteira por ativo

### Tarefa 1.3: Página Resumo

**Arquivo:** `dashboard/pages/01_resumo.py`

**Conteúdo:**
- Cards KPI: Patrimônio total, Rentabilidade (TWR), Proventos (mês/ano), Nº ativos
- Mini-gráfico de evolução do patrimônio (últimos 30d)
- Top 5 maiores posições
- Últimos proventos recebidos

### Tarefa 1.4: Página Posições

**Arquivo:** `dashboard/pages/02_posicoes.py`

**Conteúdo:**
- Tabela interativa: Ticker, Nome, Qtd, Preço Médio, Preço Atual, Variação, Saldo, % Carteira, Lucro/Prejuízo
- Filtros: tipo (ação/FII/ETF), setor
- Ordenação por qualquer coluna
- Color coding: verde (lucro), vermelho (prejuízo)

### Tarefa 1.5: Página Rentabilidade + Patrimônio

**Arquivos:**
- `dashboard/pages/04_rentabilidade.py`
- `dashboard/pages/05_patrimonio.py`

**Conteúdo:**
- Gráfico de linha: evolução do patrimônio (Plotly)
- Gráfico de linha: rentabilidade acumulada %
- Gráfico de pizza: diversificação por tipo (ações/FIIs/ETF)
- Gráfico de pizza: diversificação por setor
- Métricas: TWR, retorno no ano, retorno 12m

### Tarefa 1.6: Página Proventos

**Arquivo:** `dashboard/pages/03_proventos.py`

**Conteúdo:**
- Gráfico de barras: proventos mensais (últimos 12 meses)
- Tabela de proventos com filtros (ano, mês, ticker, tipo)
- Total recebido no ano, média mensal, yield on cost

### Tarefa 1.7: Página Análise

**Arquivo:** `dashboard/pages/06_analise.py`

**Conteúdo:**
- Tabela de indicadores fundamentalistas (P/L, P/VP, ROE, DY, Margem Líquida, Dívida/PL)
- Gráfico comparativo ROE x P/VP
- Ranking por DY
- Fórmula de Bazin (preço-teto)
- Fórmula de Graham (preço justo)

---

## Fase 2 — Avançado (P1)

### Tarefa 2.1: Rebalanceamento

**Arquivo:** `dashboard/pages/07_rebalanceamento.py`

- Definir % ideal por tipo de ativo
- Comparar % atual vs ideal
- Calcular quanto comprar/vender de cada ativo
- Gráfico de barras comparativo

### Tarefa 2.2: Metas Financeiras

**Arquivo:** `dashboard/pages/08_metas.py`

- Meta de patrimônio total (valor alvo + prazo)
- Meta de proventos mensais
- Projeção com juros compostos
- Barra de progresso

---

## Fase 3 — Refinamento (P2)

### Tarefa 3.1: Alertas e Preço-alvo

- Definir preço-alvo por ativo
- Notificação Telegram quando atingir
- Tabela de preços-alvo configurados

### Tarefa 3.2: Buy & Hold Score

- Checklist automatizado:
  - Dívida/PL < 1.0
  - ROE > 15%
  - CAGR Lucros 5a > 10%
  - Margem Líquida > 10%
  - Payout consistente
- Score 0-100 por ativo

### Tarefa 3.3: Deploy e Agendamento

- Rodar na VPS (onde já está o banco)
- Atualizar dados automaticamente (cron)
- Acesso HTTPS (Cloudflare Tunnel ou Nginx)

---

## Estimativa de Esforço

| Fase | Tarefas | Tempo estimado |
|------|---------|---------------|
| Fase 1 (P0) | 7 tarefas | ~3-4 horas |
| Fase 2 (P1) | 2 tarefas | ~2-3 horas |
| Fase 3 (P2) | 3 tarefas | ~3-4 horas |
| **Total** | **12 tarefas** | **~8-11 horas** |

---

## Próximo passo

Começar pela Fase 1 com:
1. Setup do Streamlit + tema CLEAN
2. Camada de queries SQL
3. Páginas: Resumo → Posições → Proventos → Rentabilidade → Análise
