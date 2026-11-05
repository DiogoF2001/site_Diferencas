# Tarefa 1 — Esqueleto e infraestrutura

> Escrito em retrospetiva, a partir do git log e da descrição do PR [#1](https://github.com/DiogoF2001/site_Diferencas/pull/1). O que estas fontes não dizem está assinalado como "não registado".

## Objetivo

Criar o projeto Django em `portal/`, a pilha Docker Compose de desenvolvimento e de produção, a CI e o Dependabot, sem ainda haver funcionalidades.

## Decisões técnicas

| Escolha | Alternativas | Porquê |
|---|---|---|
| Worker só com a biblioteca padrão (comando `runworker`) | Celery | O Celery exigiria Redis, um serviço fora da stack |
| `django.contrib.auth` e `admin` só na tarefa 2 | Instalá-los já | Entram com o utilizador personalizado, e assim a tarefa 1 não cria tabelas |
| `whitenoise` para os estáticos | Volume partilhado com o Caddy | Serve-os a partir da imagem, sem volume partilhado |
| `psycopg[binary]` | Variante compilada | Evita compilar no build |
| Backup com `pg_dump` encriptado com `age` | Não registado | O servidor só tem a chave pública |
| Tudo fixado: pacotes com hashes (`pip-tools`), imagens com tag e digest, ações por SHA | Não registado | Não registado |

Dependências: Django 5.2.19 (BSD), psycopg 3.3.8 (LGPL), gunicorn 26.2.0 (MIT), whitenoise 6.12.0 (MIT), pytest, pytest-django e ruff (MIT, BSD, MIT), pip-audit (Apache-2.0, a confirmar), pip-tools (BSD) e `age` (BSD, só no `backup`).

## Decisões de negócio

Não houve regras de negócio novas. O PR lista como aprovada pelo utilizador uma decisão de infraestrutura que mudou o plano: **dois utilizadores da base de dados**, em que o dono das tabelas corre as migrações e os backups e a `app` e o `worker` usam outro, sem posse de tabelas. Sem isto, a regra de "só acrescentar" da tarefa 8 podia ser contornada. Daí vem o serviço pontual `migrate` (perfil `ops`). A tarefa 2 alargou esta separação para quatro utilizadores.

## Ficheiros criados ou alterados

Commit `a6a4348`:

- **`portal/`:** `config/` (settings, urls, wsgi, asgi), `core/` (`apps`, `urls`, `views`, `worker`, comando `runworker`, testes de saúde, settings e worker), `manage.py`, `pyproject.toml`, `requirements/`.
- **`deploy/`:** `docker-compose.yml`, `docker-compose.dev.yml`, `Dockerfile`, `Caddyfile`, `.env.example`, `backup/` e `db/init-roles.sh`.
- **`.github/`:** `workflows/ci.yml` e `dependabot.yml`.
- **Documentos:** `CLAUDE.md`, `README.md`, `docs/plano.md`, `docs/plano.html`, `docs/roadmap.md`, além de `.gitignore` e `.dockerignore`.

## Como funciona

A configuração vem de variáveis de ambiente, e sem `DJANGO_SECRET_KEY` a aplicação não arranca. O idioma é `pt-pt` e o fuso `Europe/Lisbon`. `/healthz/` verifica a base de dados e responde 200 ou 503, sem detalhes internos.

Em produção, o Caddy serve HTTPS e passa para a `app` (Gunicorn). O `worker` corre o `runworker`, com um registo de tarefas periódicas (ainda vazio) e um heartbeat. O `backup` faz um `pg_dump` diário encriptado. Em desenvolvimento, `docker-compose.dev.yml` monta `portal/` e recarrega a `app` e o `worker`, sem precisar de `.env`.

A CI corre lint, testes com Postgres, `check --deploy` e `pip-audit` em cada PR.

## Comandos de verificação e resultados

Dentro do Docker, a partir de imagens construídas sem cache:

- **Testes e análise:** 13 testes passaram; ruff sem erros; `check --deploy --fail-level WARNING` sem avisos; `pip-audit` sem vulnerabilidades.
- **CI do PR:** `lint`, `test`, `deploy-check` e `pip-audit` verdes.

Com a stack de produção em `localhost` e um `.env` descartável:

- **HTTPS:** certificado local e HSTS, redireção de HTTP com 308. Com um `Host` desconhecido, o Caddy responde 200 vazio sem chegar ao Django; pedido diretamente à `app`, o Django responde 400.
- **Base de dados em baixo:** `/healthz/` responde 503 e recupera quando ela volta.
- **Utilizadores:** o da app insere, mas não cria, altera nem apaga tabelas.
- **Backups:** reposto numa base temporária com os dados certos; outra chave não o abre; a retenção apaga só as cópias antigas; um backup falhado não deixa ficheiros parciais nem apaga cópias, e o serviço fica `unhealthy`.
- **Desenvolvimento:** o recarregamento automático funciona na `app` e no `worker`.

## Problemas encontrados e como foram resolvidos

Não registado: o PR não descreve problemas durante o trabalho.

## Pendentes para tarefas seguintes

Da descrição do PR. Os dois primeiros foram resolvidos na [tarefa 2](tarefa-02-nucleo.md).

- ~~WhiteNoise só fica exercitado com os estáticos do backoffice.~~
- ~~A imagem de produção ainda não compila os `.mo`.~~
- Confirmar a licença do `pip-audit`, que não vinha nos metadados consultados.
- O pedido real ao Let's Encrypt só se pode testar com um domínio real.
- O Dependabot só foi validado como YAML. Do lado do utilizador: ativar os alertas de segurança nas definições do repositório.
