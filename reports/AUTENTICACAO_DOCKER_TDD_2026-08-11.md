# Evidência TDD — autenticação, API e Docker

## Jornadas

- Como proprietário, quero impedir acesso anônimo aos dados da carteira.
- Como operador, quero um health check público que não revele detalhes internos.
- Como operador, quero uma imagem que use os caminhos reais do projeto e não rode como root.

## RED

Comando: `python -m pytest tests/test_api.py -q -p no:cacheprovider`

Resultado inicial: 3 falhas e 2 aprovações. A API tentou consultar o banco sem
autenticação, credenciais inválidas abriram a interface e a aplicação iniciou
sem `DASHBOARD_PASSWORD`.

## GREEN

Comando: `python -m pytest -q -p no:cacheprovider`

Resultado: 10 testes aprovados. Os testes garantem rejeição de acesso anônimo e
credenciais inválidas, acesso com credenciais válidas, health check público com
erro sanitizado e falha de inicialização quando o segredo não está configurado.

## Limitações

O executável Docker não está instalado neste ambiente; portanto, os Dockerfiles
foram verificados estaticamente, mas a imagem não pôde ser construída aqui.
HTTP Basic exige HTTPS no proxy ou balanceador de produção.
