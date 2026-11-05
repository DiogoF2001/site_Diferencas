# Tarefa 2 — Núcleo: utilizadores, polos e filiações

> Escrito em retrospetiva, a partir do git log e da descrição do PR [#4](https://github.com/DiogoF2001/site_Diferencas/pull/4). O que estas fontes não dizem está assinalado como "não registado".

## Objetivo

Criar o modelo de dados comum (utilizador com login por e-mail, `Location`, `Membership`, `Mentorship`), o comando que cria o admin e um backoffice só para o admin. Fechar também os pontos da revisão da tarefa 1.

## Decisões técnicas

| Escolha | Alternativas | Porquê |
|---|---|---|
| `is_staff` é uma propriedade que devolve `is_superuser` | Coluna própria | O backoffice é só para o admin, por isso não é uma opção separada |
| Regras na base de dados sempre que possível (`CheckConstraint`, `ExclusionConstraint` com `btree_gist`); as que cruzam tabelas ficam em `clean()` | Só em `clean()` | Valem também fora dos formulários |
| `ModelAdmin` próprio, sem campo nem vista para definir a palavra-passe de outra pessoa, e sem apagar contas | `UserAdmin` do Django | Cumpre as regras de segurança do `CLAUDE.md` |
| `ensure_admin` corre no serviço `create-admin`, o único que recebe estas credenciais | Não registado | Limita onde os segredos do admin aparecem |
| `gettext` só no build da imagem de produção | Mantê-lo na imagem | Corre o `compilemessages` e não fica na imagem final |
| `deploy/tests/check-production.sh` | Só `pytest` | Testa o que o `pytest` não alcança: contentores reais e cada utilizador da base de dados a ligar-se pela rede |

Sem dependências novas.

## Decisões de negócio

Aprovadas pelo utilizador, segundo o PR, e registadas no plano:

- O Admin é uma conta técnica, sem filiações. Quem também trabalhe como profissional usa outra conta, com outro e-mail.
- Na tabela da secção 4, o Admin passa a submeter pedidos e a adicionar participantes "em nome de outra pessoa".
- `end_date` é o último dia com acesso, na hora de Lisboa.
- Só contam como "Ocupado" as reservas aprovadas, as atribuições exclusivas e os bloqueios.

## Ficheiros criados ou alterados

Commit `7e71a97`:

- **`portal/core/`:** `models.py`, `admin.py`, `migrations/0001_initial.py`, comando `ensure_admin`, testes (`test_users`, `test_memberships`, `test_mentorships`, `test_backoffice`, `test_ensure_admin`, `conftest.py`).
- **Resto de `portal/`:** `config/settings.py`, `config/urls.py`, `conftest.py`, `locale/pt_PT/LC_MESSAGES/django.po`, `pyproject.toml`.
- **`deploy/`:** `tests/check-production.sh`, `db/init-roles.sh`, `Dockerfile`, os dois Compose, `.env.example`.
- **Outros:** `.github/workflows/ci.yml`, `.gitignore`, `CLAUDE.md`, `README.md`, `docs/plano.md`, `docs/plano.html`, `docs/roadmap.md`.

## Como funciona

- **`User`:** o e-mail é o login e é único sem distinguir maiúsculas: guarda-se em minúsculas, e uma `CheckConstraint` garante-o.
- **`Membership`:** pessoa + polo + papel, com subpapel e datas. Uma `ExclusionConstraint` impede o mesmo papel com datas sobrepostas para a mesma pessoa e polo. Uma estagiária precisa de data de fim. `active_on()` devolve as linhas em vigor numa data, por omissão a de hoje em Lisboa, com `end_date` incluído.
- **`Mentorship`:** orientadora → orientanda, por polo e com datas. `clean()` valida que ambas têm a filiação certa nessas datas.
- **`ensure_admin`:** idempotente, nunca repõe a palavra-passe, e recusa promover uma conta normal ou criar um segundo admin.
- **Base de dados de produção:** quatro utilizadores. `POSTGRES_USER` só na inicialização, `PORTAL_OWNER_USER` no `migrate` (não é superutilizador), `PORTAL_DB_USER` na app e no worker, e `PORTAL_BACKUP_USER` no backup (`pg_read_all_data`).

## Comandos de verificação e resultados

Localmente, no Docker:

- `pytest`: 91 passaram.
- `ruff check` e `ruff format --check`: sem erros.
- `check --deploy --fail-level WARNING`: sem avisos.
- `pip-audit`: sem vulnerabilidades conhecidas.
- `deploy/tests/check-production.sh`: 31 verificações passaram.
- CI do PR: `lint`, `test`, `deploy-check` e `pip-audit` verdes.

## Problemas encontrados e como foram resolvidos

Não registado: o PR não descreve problemas durante o trabalho. Da revisão da tarefa 1 saíram os quatro utilizadores da base de dados, o `compilemessages` na imagem e o teste do WhiteNoise.

## Pendentes para tarefas seguintes

- **O backoffice não deve ir para produção antes da tarefa 4**, que traz o 2FA e o limite de tentativas de login.
- **O `init-roles.sh` só corre num volume novo.** Uma base de dados que já exista não fica com os novos utilizadores.
- `BACKUP_DIR` é uma variável nova e opcional, que o script de verificação precisa para não usar a pasta real dos backups.
