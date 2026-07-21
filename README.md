# Fluxo de Investimentos v2

Sistema automatizado de análise e gestão de carteira de investimentos.

## Estrutura

```
scripts/
├── db_utils.py                # Configuração do banco (via variáveis de ambiente)
├── relatorio_executivo.py     # Relatório principal com 7 módulos
├── relatorio_modulos/         # Módulos de análise
│   ├── modulo_alocacao_ir.py  # Alocação com IR estimado
│   ├── modulo_tributario.py   # Análise tributária
│   ├── modulo_alertas_inteligentes.py  # Alertas classificados
│   ├── modulo_setorial.py     # Análise setorial
│   ├── modulo_renda_passiva.py  # Renda passiva
│   ├── modulo_benchmarking.py # Benchmarking
│   ├── modulo_risco.py        # Risco e volatilidade
│   └── modulo_fundamentalista.py  # Indicadores fundamentalistas
├── check_tokens.py            # Watchdog de tokens Google
├── reauth_google.py           # Reautenticação OAuth
├── backfill_historico.py      # Backfill Yahoo Finance
├── buscar_notas_gmail.py      # Busca notas XP no Gmail
├── processar_nota_xp.py       # Parser de notas XP
├── coletar_proventos.py       # Coleta proventos via Yahoo Finance
├── fundamentus_scraper.py     # Scraper Fundamentus (v1)
├── fundamentus_scraper_v2.py  # Scraper Fundamentus (v2)
├── analise_alocacao.py        # Análise de alocação
├── analise_acoes_diaria.py    # Análise diária de ações
├── atualizar_carteira.py      # Atualização de carteira
├── gerar_agenda.py            # Agenda de compras
├── v2_analise.py              # Análise v2
└── agenda_compras.sh          # Shell script agenda
reports/                       # PDFs gerados (não commitados)
output/                        # Imagens de saída (não commitadas)
```

## Configuração

1. Clone o repositório
2. Copie `.env.example` para `.env` e preencha com suas credenciais
3. Configure as variáveis de ambiente:

```bash
export DB_HOST=seu_host
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=sua_senha
export DB_NAME=carteira_investimentos
```

## Requisitos

```bash
pip install psycopg2-binary reportlab matplotlib pandas numpy yfinance
```

## Uso

```bash
# Relatório executivo completo
python scripts/relatorio_executivo.py

# Backfill de dados históricos
python scripts/backfill_historico.py
```

## Licença

Privado — Uso pessoal.