# Evidência TDD — fundação de auditoria

Data: 19/08/2026

## Escopo

Primeira fase segura da recuperação integral de confiança: catálogo/manifesto de backup, schema auditável aditivo, contrato de evidências e staging. Nenhuma migration foi aplicada e nenhum banco externo foi acessado.

## RED

- Migrations ausentes: 5 testes falharam.
- Pacote de evidências ausente: 3 erros de importação.
- Invariantes de construção/transição: falha esperada ao contornar validação.
- Catálogo/manifesto ausentes: erro de importação.
- CLI ausente e depois exposição de segredo em erro de conexão: falhas esperadas.
- DSN em argumentos e corridas de arquivo/TOCTOU: 4 falhas esperadas.
- Contrato de lifecycle/hash/identidade: 3 falhas e 1 skip de integração.
- Corridas de symlink e troca de identidade: falhas `DID NOT RAISE` antes do endurecimento.

## GREEN

- Comando: `python -m pytest -q --basetemp .tmp/pytest-audit-final3 -p no:cacheprovider`
- Resultado: **144 passed, 1 skipped, 1 warning**.
- `git diff --check`: aprovado.
- Revisão final: aprovada, sem achados críticos, altos ou médios importantes.

O skip é `tests/test_audit_postgres_integration.py`: exige `AUDIT_TEST_DATABASE_URL` apontando para um banco descartável cujo nome contenha `audit_test`. A proteção recusa execução em outro banco.

## Garantias

| Garantia | Evidência | Resultado |
|---|---|---|
| Migrations criam somente `investimentos_audit` | testes estáticos de migration | PASS |
| Identidade de instrumento trata bolsa nula sem duplicidade | migration + testes | PASS |
| Hashes plaintext/ciphertext têm semântica explícita | migration, manifesto e store | PASS |
| Evidências publicadas e decisões são imutáveis | triggers + teste PostgreSQL opt-in | PASS estático / runtime pendente |
| Lifecycle de importação/revisão não aceita timestamps contraditórios | checks + testes | PASS |
| Manifestos JSON e hashes são determinísticos | testes unitários | PASS |
| Backup manifest usa o mesmo descritor para tamanho/identidade/hash | testes de TOCTOU | PASS |
| Symlinks, troca de identidade e arquivos instáveis falham fechado | testes de corrida | PASS |
| CLI não recebe DSN secreto em argv e não imprime erro do driver | testes de segurança | PASS |
| Store aceita somente ciphertext não vazio e atestação confiável de plaintext | testes unitários | PASS |
| Staging permite apenas transições explicitamente válidas | testes unitários | PASS |

## Limitações e gates

- As migrations ainda precisam ser aplicadas duas vezes em PostgreSQL descartável e ter triggers/constraints exercitados antes de qualquer ambiente real.
- Gestão de chaves e criptografia/decriptação são uma fronteira externa ainda não implementada; o store recebe somente bytes já criptografados.
- A raiz do store deve ser gravável apenas pelo mesmo domínio de confiança, especialmente no Windows.
- O CLI cria catálogo e manifestos de arquivos existentes; não executa `pg_dump`.
- Nenhuma tabela legada foi modificada, migrada ou promovida.
