# CLAUDE.md — Site e serviços Diferenças

Repositório do novo site do CDI Diferenças e do **portal** (área reservada) para profissionais. O primeiro serviço do portal é a **gestão de salas**.

## Fonte de verdade

- `docs/plano.md` é o plano aprovado (a versão visual está em `docs/plano.html`). As decisões de produto, permissões e regras estão lá.
- `docs/roadmap.md` tem as tarefas por ordem, cada uma com critérios de aceitação.
- Se uma tarefa exigir uma decisão que não está no plano, **pergunta antes de implementar**. Não inventes regras de negócio.
- Se uma decisão mudar, atualiza `docs/plano.md` no mesmo PR, mas só depois de o utilizador aprovar a mudança.

## Forma de trabalhar

1. Uma tarefa do roadmap por branch (`feat/<nº>-<nome-curto>`) e um PR por tarefa.
2. Não esperas pela aprovação do plano. O controlo passa a ser a revisão do PR.
3. As decisões técnicas são tuas: arquitetura interna, bibliotecas já aprovadas, nomes, estrutura e testes.
4. Só paras para perguntar quando faltar uma regra de negócio que não está no plano, ou quando a decisão for irreversível ou tocar na segurança: permissões, dados pessoais, credenciais, migrações destrutivas. Perguntas numa linha, com a tua recomendação.
5. Cada regra de permissão tem testes **positivos e negativos**. Por exemplo: "secretariado do polo A não vê detalhes no polo B".
6. Antes de abrir o PR, corre os testes, o lint e o `check --deploy`. Os comandos estão na secção "Comandos".
7. Mensagens de commit em inglês, no imperativo e curtas.
8. O PR de cada tarefa tem uma descrição curta e uma ligação para o ficheiro de registo dessa tarefa.
9. Nas mensagens para o utilizador, um resumo de no máximo 5 linhas no fim de cada tarefa: o que foi feito, o estado da CI e o que precisa dele.
10. Todo o detalhe fica em `docs/registo/`: um ficheiro por tarefa (`tarefa-NN-nome.md`), escrito à medida que trabalhas e não só no fim, e indexado no `README.md` dessa pasta, que indica as secções obrigatórias.

## Estrutura do repositório

```
portal/      Aplicação Django (área reservada): core/ é o núcleo, salas/ o módulo de salas
site/        Site público (a definir; não mexer sem pedido)
prototipo/   Protótipo clicável estático (HTML, dados fictícios)
docs/        Plano, roadmap e registo das tarefas (docs/registo/)
deploy/      Docker Compose, Caddyfile, scripts de backup
```

## Stack (não mudar sem aprovação)

- Python 3.12+, **Django 5.2 LTS** (migração para a 6.2 LTS quando sair, em abril de 2027).
- **PostgreSQL**. As reservas sobrepostas são impedidas por `ExclusionConstraint` (`django.contrib.postgres`, com `btree_gist`).
- Interface: templates Django + **HTMX**. Calendário: **EventCalendar (vkurko, licença MIT)**. Não usar o FullCalendar Premium.
- Tarefas agendadas: um serviço `worker` separado.
- Testes: `pytest` + `pytest-django`. Lint e formatação: `ruff`.
- Docker Compose com os serviços: `proxy` (Caddy), `app` (Gunicorn), `worker`, `db`, `backup`, mais o serviço pontual `migrate` (perfil `ops`), que só corre as migrações.
- Cada dependência nova precisa de justificação no PR. Só licenças livres, e nada que dependa de serviços pagos (Google, Microsoft, SaaS).

## Idioma

- Código, identificadores, nomes de modelos e commits: **inglês**.
- Todo o texto visível ao utilizador: **português de Portugal**, através do i18n do Django (`gettext`). Usa "utilizador", "ecrã", "ficheiro", "palavra-passe", "registar", "telemóvel". Nunca uses variantes do Brasil.
- Fuso horário: guardar em UTC e mostrar em `Europe/Lisbon`.

## Glossário (domínio → código)

| Domínio | Código |
|---|---|
| Polo | `Location` |
| Filiação (pessoa + polo + papel) | `Membership` |
| Papel / subpapel | `Role` (`professional`, `secretariat`, `coordination`) / `Subrole` (`resident`, `intern`) |
| Admin (global) | `is_superuser`, conta técnica sem `Membership` |
| Orientação (orientadora → orientanda) | `Mentorship` (`mentor`, `mentee`) |
| Sala | `Room` |
| Atribuição exclusiva | `RoomAssignment` |
| Reserva / pedido | `Booking` (estados: `pending`, `approved`, `refused`, `cancelled`, `expired`) |
| Série recorrente | `BookingSeries` (RRULE) |
| Pedido de alteração | `ChangeRequest` |
| Participação | `Participation` |
| Bloqueio (feriado/manual) | `Closure` |
| Regras do polo | `LocationSettings` |
| Histórico da reserva | `BookingEvent` |
| Auditoria de contas | `AuditEvent` |

## Regras de segurança (inegociáveis)

- **Permissões sempre por polo e sempre no servidor.** Usa uma única função central, `core.permissions.has_perm_in(user, "salas.approve", location)`. Nunca verifiques nomes de papéis no código das vistas. Cada módulo declara as suas permissões com prefixo (`salas.*`, `core.*`) no seu `permissions.py`.
- **Livre/ocupado:** os querysets e serializers das reservas de outras pessoas só devolvem início, fim e "ocupado". Esconder campos só no template não chega.
- **Gestão de contas:**
  - cada pessoa só atribui papéis até ao seu próprio nível no polo;
  - desativar a conta inteira ou repor o 2FA exige um nível ≥ ao da pessoa em todos os polos dela;
  - ninguém define a palavra-passe de outra pessoa (só se envia um link de recuperação).
- **Admin:** é criado por um management command a partir de variáveis de ambiente. Nunca fica no código.
- **Segredos:** só em `.env`, que está no `.gitignore`. O `.env.example` tem só nomes e valores fictícios.
- **Sem dados de utentes:** não crias campos para nomes, processos ou diagnósticos de utentes. As notas das reservas são logísticas.
- **Históricos (`BookingEvent`, `AuditEvent`) só de acrescentar:** não há vistas para editar ou apagar, e o utilizador da base de dados da app não tem `UPDATE`/`DELETE` nessas tabelas.
- O `manage.py check --deploy` tem de passar sem avisos na configuração de produção.

## Comandos

Corre tudo a partir da raiz do repositório e dentro do Docker. O ambiente de desenvolvimento não precisa de `.env`. Se o teu UID não for 1000, exporta antes `HOST_UID=$(id -u) HOST_GID=$(id -g)`.

```bash
# Desenvolvimento: arrancar (http://127.0.0.1:8000/healthz/, com recarregamento automático)
docker compose -f deploy/docker-compose.dev.yml up --build

# Testes
docker compose -f deploy/docker-compose.dev.yml run --rm app pytest

# Lint e formatação
docker compose -f deploy/docker-compose.dev.yml run --rm --no-deps app ruff check .
docker compose -f deploy/docker-compose.dev.yml run --rm --no-deps app ruff format --check .

# Migrações em desenvolvimento
docker compose -f deploy/docker-compose.dev.yml run --rm app python manage.py makemigrations
docker compose -f deploy/docker-compose.dev.yml run --rm app python manage.py migrate

# Admin em desenvolvimento (valores fictícios do docker-compose.dev.yml)
docker compose -f deploy/docker-compose.dev.yml run --rm app python manage.py ensure_admin

# Traduções: extrair para o .po, preencher os msgstr em português e compilar.
# Os testes compilam sozinhos; o runserver precisa deste último comando para mostrar as traduções.
docker compose -f deploy/docker-compose.dev.yml run --rm --no-deps app python manage.py makemessages -l pt_PT --no-location
docker compose -f deploy/docker-compose.dev.yml run --rm --no-deps app python manage.py compilemessages

# Auditoria de dependências
docker compose -f deploy/docker-compose.dev.yml run --rm --no-deps app pip-audit --require-hashes --disable-pip -r requirements/base.txt -r requirements/dev.txt

# Fixar dependências, depois de alterar base.in ou dev.in (por esta ordem)
docker compose -f deploy/docker-compose.dev.yml run --rm --no-deps -w /app/requirements app pip-compile --generate-hashes --allow-unsafe --strip-extras --output-file=base.txt base.in
docker compose -f deploy/docker-compose.dev.yml run --rm --no-deps -w /app/requirements app pip-compile --generate-hashes --allow-unsafe --strip-extras --output-file=dev.txt dev.in

# Configuração de produção (precisa de deploy/.env, copiado de deploy/.env.example)
docker compose -f deploy/docker-compose.yml run --rm --no-deps app python manage.py check --deploy --fail-level WARNING
docker compose -f deploy/docker-compose.yml up -d --build --wait
docker compose -f deploy/docker-compose.yml --profile ops run --rm migrate
docker compose -f deploy/docker-compose.yml --profile ops run --rm create-admin
docker compose -f deploy/docker-compose.yml exec backup /usr/local/bin/backup.sh once
# Emergência: o admin perdeu o 2FA (fica na auditoria de contas, sem autor)
docker compose -f deploy/docker-compose.yml exec app python manage.py reset_2fa admin@example.test

# Verificação em contentores reais: utilizadores da base de dados, backup, traduções, WhiteNoise e
# login no backoffice. Não precisa de .env e usa uma pilha própria, que apaga no fim.
deploy/tests/check-production.sh
```

- Usa sempre `--fail-level WARNING` no `check --deploy`. Sem esta opção, os avisos não fazem o comando falhar.
- O PostgreSQL de produção tem quatro utilizadores:
  - `POSTGRES_USER` é o superutilizador e serve só para a inicialização, no `init-roles.sh`. Nenhum outro serviço o recebe;
  - `PORTAL_OWNER_USER` é o dono das tabelas, não é superutilizador e é usado só pelo `migrate`;
  - `PORTAL_DB_USER` é usado pela `app`, pelo `worker` e pelo `create-admin`, e não é dono de nenhuma tabela;
  - `PORTAL_BACKUP_USER` é usado pelo `backup` e só tem `pg_read_all_data`.
- O `init-roles.sh` só corre num volume novo. Mudar estes utilizadores numa base de dados existente exige fazer as alterações à mão.
- O `ensure_admin` só usa a palavra-passe do ambiente ao criar a conta. Para a repor numa emergência, usa o `changepassword` do Django. Para o 2FA, usa o `reset_2fa`.
- Em produção, o SMTP é obrigatório (`EMAIL_HOST`, `DEFAULT_FROM_EMAIL`). Em desenvolvimento, sem `EMAIL_HOST`, os e-mails aparecem na consola da `app`.
- As tabelas só de acrescentar retiram UPDATE/DELETE/TRUNCATE ao utilizador da app na própria migração, com `core.db.revoke_changes("<tabela>")`. O `check-production.sh` confirma-o com o utilizador real.
- O Dependabot não atualiza a imagem do Postgres em `.github/workflows/ci.yml`. A CI falha até essa linha ser atualizada à mão para a mesma versão.
