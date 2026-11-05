# Tarefa 3 — Motor de permissões

## Objetivo

Criar o único sítio onde o portal decide quem pode fazer o quê: o registo de permissões por módulo, o mapeamento papel → permissões, a função central `has_perm_in`, os helpers de queryset, o teto de atribuição de papéis, as ações sobre a conta inteira e a visibilidade que vem das orientações. Ainda não há vistas: as tarefas seguintes usam isto.

## Decisões técnicas

| Escolha | Alternativas | Porquê |
|---|---|---|
| Permissões declaradas em Python, em `permissions.py` de cada módulo, descobertas com `autodiscover_modules` | Tabelas na base de dados; `Permission`/`Group` do Django | O mapeamento vem do plano e não se edita em produção. Fica versionado e revisto em PR. Os `Group` do Django não são por polo |
| App `salas` criada já, só com `permissions.py` | Declarar `salas.*` no `core` | O núcleo não pode conhecer os módulos. A app não tem modelos nem migrações até à tarefa 5 |
| Código de permissão desconhecido levanta `ImproperlyConfigured` | Devolver `False` | Um erro de escrita recusaria acesso em silêncio, e os testes não dariam por isso |
| Sem cache nas verificações | Cache por pedido | Uma ou duas consultas indexadas por verificação; nesta escala, o risco de dados antigos numa decisão de segurança pesa mais do que o ganho. A rever se uma vista precisar de muitas |
| `on_behalf_of` como argumento de `has_perm_in` | Função à parte | Mantém uma só função central. Sem o argumento, o admin não tem estas permissões, por isso esquecê-lo recusa em vez de autorizar |
| `people_with_visible_*` em `salas`, `mentees_of` no `core` | Tudo no `core` | As orientações são do núcleo; "horário" e "horas" são do módulo de salas |
| Testes de matriz com a tabela escrita à mão | Derivar a expectativa do registo | Um teste derivado do registo passaria sempre. Assim, se as declarações se afastarem do plano, os testes falham |

Sem dependências novas nem migrações.

## Decisões de negócio

**Tomada pelo utilizador nesta tarefa, e registada na secção 4 do plano:**

- **Polo inativo:** as filiações nesse polo não dão nenhuma permissão. O Admin mantém o acesso, para o poder gerir e reativar. Reativar o polo repõe tudo.

**Dadas pelo utilizador no pedido da tarefa:** hierarquia `professional < secretariat < coordination`; só contam as filiações ativas na data de Lisboa; o Admin age "em nome de outra pessoa".

**Interpretações do plano e do protótipo.** O plano não as escreve palavra por palavra. Todas recusam em caso de dúvida. **A confirmar na revisão do PR:**

| Regra implementada | Base |
|---|---|
| Só o Admin age "em nome de"; a pessoa nomeada tem de ter a permissão no polo nesse momento (conta ativa e filiação ativa) | Plano, secção 4 |
| Em `salas.book_directly`, o Admin marca em nome de qualquer membro ativo do polo; em `salas.submit_request`, só em nome de quem pode submeter pedidos (Profissional) | Protótipo: o admin tem marcação direta, com o titular a ser outra pessoa. Tabela do plano: o secretariado e a coordenação "marcam diretamente" |
| O Profissional não atribui papéis nem atua sobre contas, apesar de ter um nível | Tabela da secção 4 ("–") e protótipo |
| Remover alguém de um polo exige um nível ≥ ao mais alto que essa pessoa tem nesse polo, contando os papéis que ainda vão começar | Protótipo (`canManageMember`). Contar os futuros é acrescento: de outro modo, o secretariado podia remover uma coordenação que começa na próxima semana |
| Ninguém desativa a própria conta nem repõe o próprio 2FA, incluindo o Admin | Protótipo (`canActOnAccount`). O plano fala em "essa pessoa". Uma sessão roubada não pode retirar o 2FA |
| Uma pessoa sem filiações ativas só pode ser gerida pelo Admin | Protótipo. Evita que "todos os polos" seja verdade quando não há nenhum |
| Uma pessoa com filiação ativa num polo inativo só pode ser gerida pelo Admin | Consequência da decisão do polo inativo |
| A orientação só conta com a relação, a filiação de profissional da orientadora e a filiação de estagiária da orientanda ativas, e com as duas contas ativas | Plano, secção 4, mais "só contam as filiações ativas". A orientadora perde a visão quando o estágio termina, mesmo que a relação continue aberta |
| A coordenação e o Admin veem as horas de quem já saiu do polo; o secretariado vê os horários, mas só as suas próprias horas | Plano, secções 4 e 8 (a coordenação vê "as de todo o polo"; "cada pessoa vê as suas horas") |
| Só o Admin liga a libertação de salas (`salas.enable_room_release`) | Plano, secções 6 e 10 |

**Consequência a ter em conta:** como só contam as filiações ativas, uma filiação futura noutro polo não bloqueia as ações sobre a conta inteira. O secretariado do polo A pode desativar uma pessoa que começa como coordenação no polo B na próxima semana. Segue a regra pedida; se não for o desejado, muda numa linha.

## Ficheiros criados ou alterados

**Criados**
- `portal/core/permissions.py`: o motor.
- `portal/salas/` (`__init__.py`, `apps.py`, `permissions.py`, `tests/`): o módulo, as suas permissões e a visibilidade.
- `portal/core/tests/test_permissions.py`, `portal/core/tests/test_permission_matrix.py`.
- `portal/salas/tests/test_permission_matrix.py`, `portal/salas/tests/test_visibility.py`.
- `docs/registo/`: este registo, o índice e os registos das tarefas 0, 1 e 2.

**Alterados**
- `portal/core/apps.py`: descobre os `permissions.py` no arranque.
- `portal/config/settings.py`: instala a app `salas`.
- `portal/pyproject.toml`: acrescenta `salas` aos caminhos do `pytest`.
- `portal/core/tests/helpers.py`: funções para criar contas, filiações e orientações nos testes.
- `CLAUDE.md`: nova "Forma de trabalhar".
- `docs/plano.md`, `docs/plano.html`: polo inativo.
- `docs/roadmap.md`: tarefa 3 concluída.

## Como funciona

**Declarar.** Cada módulo chama `register_permissions("salas", {"approve": PermissionRule(roles=STAFF), ...})`. Uma `PermissionRule` diz que papéis têm a permissão e como o Admin a usa: `FULL` (diretamente, o caso normal) ou `ON_BEHALF` (só em nome de outra pessoa). `is_global=True` marca as permissões que não dependem de um polo; só o Admin as pode ter.

**Perguntar.** `has_perm_in(user, perm, location)` decide assim:

1. Código desconhecido levanta um erro. Permissão de polo sem polo também.
2. Com `on_behalf_of`: tem de ser o Admin, numa permissão `ON_BEHALF`, e a pessoa nomeada não pode ser admin e tem de ter a permissão exigida nesse polo.
3. O Admin ativo tem as permissões `FULL`, em qualquer polo, ativo ou não.
4. Os outros: conta autenticada e ativa, polo ativo, e um dos papéis ativos hoje em Lisboa consta da regra. Os papéis somam-se dentro do polo e nunca passam para outro.

Uma linha de `Membership` numa conta de admin é ignorada: o `clean()` já a recusa nos formulários, mas o motor não depende disso.

**Listar.** `locations_with_perm(user, perm)` devolve os polos onde a mesma pergunta daria "sim", e `filter_by_perm(queryset, user, perm, location_field="location")` restringe qualquer queryset a esses polos. As tarefas seguintes devem usar isto em vez de filtrar à mão. Os testes da matriz verificam que as duas formas dão a mesma resposta.

**Teto de papéis.** `can_assign_role(actor, role, location)` exige `core.manage_members` no polo e que o nível do papel não passe o nível de quem atribui nesse polo: o mais alto dos seus papéis ativos, com `professional=1`, `secretariat=2`, `coordination=3`. `can_remove_from_location` aplica a mesma ideia a quem sai.

**Conta inteira.** `can_manage_account(actor, target)` vê os polos onde o alvo tem filiações ativas e exige, polo a polo, `core.manage_members` e um nível ≥ ao do alvo. Compara em cada polo, não o nível mais alto de cada um. O nível do alvo vem diretamente das filiações, para que uma conta desativada não passe a contar como nível 0.

**Orientações.** `mentees_of(user, location)` devolve as orientandas nesse polo. Em `salas`, `people_with_visible_schedule` e `people_with_visible_hours` devolvem as pessoas cujo horário ou horas alguém pode ver: as próprias, as orientandas, ou todas as do polo se tiver `salas.view_all_bookings` ou `salas.view_reports`.

**Permissões**

| Código | Linha da tabela do plano | Papéis | Admin |
|---|---|---|---|
| `salas.view_availability` | Ver ocupação | todos | direto |
| `salas.view_all_bookings` | Ver detalhes e histórico de todas | secretariado, coordenação | direto |
| `salas.submit_request` | Submeter pedidos | profissional | em nome de |
| `salas.book_directly` | Marca diretamente | secretariado, coordenação | em nome de |
| `salas.add_participants` | Adicionar participantes | todos | em nome de |
| `salas.approve` | Aprovar e recusar | secretariado, coordenação | direto |
| `salas.change_any_booking` | Alterar qualquer reserva | secretariado, coordenação | direto |
| `salas.manage_location` | Gerir salas, exclusivas, bloqueios e regras | secretariado, coordenação | direto |
| `salas.override_holidays` | Anular feriados | secretariado, coordenação | direto |
| `salas.view_reports` | Relatórios | coordenação | direto |
| `salas.enable_room_release` | Secções 6 e 10 | nenhum | direto |
| `core.manage_members` | Criar contas e atribuir papéis | secretariado, coordenação | direto |
| `core.manage_mentorships` | Secção 4, Orientação | secretariado, coordenação | direto |
| `core.view_professionals` | Listagem de profissionais | coordenação | direto |
| `core.view_audit` | Secção 11, auditoria de contas | coordenação | direto |
| `core.technical_area` | Área técnica (global) | nenhum | direto |

## Comandos de verificação e resultados

Corridos no Docker, a partir da raiz do repositório:

| Comando | Resultado |
|---|---|
| `docker compose -f deploy/docker-compose.dev.yml run --rm app pytest` | 419 passaram (91 antes desta tarefa) |
| `... run --rm --no-deps app ruff check .` | sem erros |
| `... run --rm --no-deps app ruff format --check .` | sem alterações |
| `... run --rm app python manage.py makemigrations --check --dry-run` | sem migrações em falta |
| `docker compose -f deploy/docker-compose.yml run --rm --no-deps app python manage.py check --deploy --fail-level WARNING` | sem avisos |
| `deploy/tests/check-production.sh` | todas as verificações passaram |
| `... run --rm --no-deps app pip-audit ...` | sem vulnerabilidades conhecidas |

**Verificação por mutação:** como os testes passaram à primeira, parti 23 regras do motor uma a uma (por exemplo, tirar o `active_on()` ou o teto) para confirmar que cada uma faz falhar pelo menos um teste. O script não fica no repositório. Ao fim do reforço descrito abaixo, as 23 são apanhadas. Só cobre as regras escolhidas, não é uma medida de cobertura completa.

**CI:** ver o PR.

## Problemas encontrados e como foram resolvidos

- **Dois testes não protegiam a regra que diziam proteger,** e a mutação mostrou-o:
  - "removal counts a role that has yet to start": o alvo só tinha o papel futuro, por isso a resposta era "não" por falta de filiações. Passou a ter também um papel ativo mais baixo.
  - O bloqueio de ações sobre a conta do admin: sem filiações, a resposta já era "não". Acrescentei um teste em que o admin tem uma filiação indevida.
- **Armadilhas tidas em conta no desenho, cada uma com teste:** "todos os polos" é verdade quando não há nenhum; a conta desativada parecia ter nível 0; comparar o nível mais alto global em vez de polo a polo; o nível de Profissional não dá direito a atribuir papéis; 23:30 UTC de 30 de junho já é 1 de julho em Lisboa.

## Pendentes para tarefas seguintes

- **Tarefa 4:** decoradores ou mixins para as vistas devolverem 403, a usar nos ecrãs de contas; `AuditEvent` nestas ações; `can_manage_account` é a regra a usar em desativar e repor o 2FA. O envio de links de recuperação ainda não tem regra de quem o pode fazer.
- **Tarefa 6 e 8:** "só as suas" (titular ou participante) é uma verificação sobre a reserva e depende do modelo `Booking`. Guardar "em nome de" no `BookingEvent` quando se usar `on_behalf_of`. O titular de uma marcação direta nunca pode ser o admin.
- **Tarefa 10:** o titular vê as horas dos participantes nas suas reservas, também ao nível da reserva.
- **Área técnica:** o modo "ver como utilizador" (só leitura e registado) ainda não existe.
- **Por decidir no futuro, se fizer falta:** o que acontece a reservas e pedidos de um polo que fica inativo. Hoje só está definido o efeito nas permissões.
