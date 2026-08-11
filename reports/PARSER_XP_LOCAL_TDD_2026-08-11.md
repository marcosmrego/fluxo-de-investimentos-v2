# Evidência TDD — parser local e recuperação da carteira

## Jornadas

- Importar notas XP sem transmitir documentos financeiros a terceiros.
- Rejeitar operações inconsistentes ou instrumentos desconhecidos antes da escrita.
- Reexecutar o backlog sem duplicar notas existentes.
- Executar o importador periodicamente sem jobs concorrentes.

## RED

- O módulo `scripts.xp_note_parser` não existia.
- O processador ainda tentou acessar `parserxp.expansao-ai.com.br`.
- A senha da nota estava fixa no código.
- Senha ausente gerava um argumento `None` no subprocesso.
- O layout real omitia a linha de cabeçalho da tabela extraída.
- Os três instrumentos novos não possuíam resolução de ticker.

Os testes foram executados em cada etapa e falharam especificamente nesses
comportamentos antes das respectivas implementações.

## GREEN

Comando final: `python -m pytest -q -p no:cacheprovider`

Resultado: 23 testes aprovados. O parser cobre cabeçalho, números brasileiros,
compras, vendas, reconciliação, documentos inválidos, tabela sem cabeçalho,
senha opcional, duplicatas e tickers oficiais verificados.

## Validação operacional

- Ambiente isolado criado em `.venv-automation` no volume do Hermes.
- Três notas novas foram importadas em transações individuais.
- Dez notas anteriores foram reconhecidas como duplicatas no backlog de 30 dias.
- Novas posições: `SPCX34`, `ROXO34`; `SPXB11` recebeu novo aporte.
- Cron ativo: minuto 17 de cada hora, com trava `flock`.
- Checkout local e checkout do Hermes sincronizados com `origin/main`.

## Limitações

- Não existe fixture com PDF real no Git por conter dados financeiros pessoais.
- O teste real ocorreu somente no servidor, e os PDFs temporários foram removidos.
- A suíte emite um aviso não bloqueante de compatibilidade futura entre TestClient e httpx.
