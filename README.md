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

Antes de iniciar o dashboard, configure credenciais exclusivas em `.env`:

```bash
DASHBOARD_USERNAME=investidor
DASHBOARD_PASSWORD=uma_senha_longa_e_aleatoria
```

O dashboard usa autenticação HTTP Basic. Em produção, publique-o somente por
HTTPS; sem TLS, usuário e senha podem ser interceptados na rede. O endpoint
`/health` permanece público para o health check do container.

```bash
# Dashboard local
uvicorn dashboard.main:app --host 127.0.0.1 --port 3000

# Imagem de produção (execute a partir da raiz do repositório)
docker build -t fluxo-investimentos .
docker run --env-file .env -p 127.0.0.1:3000:3000 fluxo-investimentos
```

O container roda com usuário sem privilégios e valida `/health`
periodicamente. O `dashboard/Dockerfile` também deve ser construído usando a
raiz como contexto: `docker build -f dashboard/Dockerfile .`.

```bash
# Relatório executivo completo
python scripts/relatorio_executivo.py

# Backfill de dados históricos
python scripts/backfill_historico.py
```

### Importação automática das notas XP

O importador lê os PDFs do Gmail e faz extração local; documentos financeiros
não são enviados a serviços externos. Instale as dependências isoladas com:

```bash
uv venv .venv-automation
uv pip install --python .venv-automation/bin/python -r requirements-automation.txt
.venv-automation/bin/python scripts/buscar_notas_gmail.py --dias 7
```

Variáveis obrigatórias: `XP_NOTAS_PASSWORD`, banco PostgreSQL e os arquivos
OAuth do Gmail. O job de produção roda no minuto 17 de cada hora através de
`/etc/cron.d/investimentos-import`, protegido por `flock`. Consulte os logs com
`journalctl -t investimentos-import`.

O processo é fail-closed: PDF inválido, operação não reconciliada ou ticker não
resolvido aborta a nota inteira antes do commit.

## Licença

Privado — Uso pessoal.
