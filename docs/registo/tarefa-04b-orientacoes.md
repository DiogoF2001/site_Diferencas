# Tarefa 4b — Orientações, filiações e auditoria no portal

## Objetivo

Acabar a gestão de pessoas no portal, sem precisar do backoffice: o secretariado e a coordenação gerem as orientações e alteram o papel ou as datas de uma filiação, e a coordenação consulta a auditoria de contas do seu polo. Inclui também um pedido do utilizador: na lista de membros, quem tem o 2FA por configurar mostra dois botões, "Enviar link do 2FA" e "Enviar link da palavra-passe", para quem também esqueceu a palavra-passe não ficar preso.

## Decisões técnicas

| Escolha | Alternativas | Porquê |
|---|---|---|
| As ações das orientações ficam em `core/mentorships.py`; a alteração de filiações em `core/accounts.py` | Regras nas vistas | Como na tarefa 4: cada ação verifica a permissão e regista o `AuditEvent`, seja qual for o caminho até ela. Há testes que as chamam diretamente |
| As regras de alteração de datas ficam num só método, `Period.check_change`, usado por filiações e orientações | Validação em cada formulário | A mesma regra para os dois modelos, e verificada também fora do formulário |
| A consulta da auditoria é um queryset, `core.audit.events_in(location)` | Filtrar no template | O filtro é a regra de privacidade, por isso fica no servidor e tem testes próprios |
| Os dois botões são duas vistas (`enviar-link/` e `enviar-link-2fa/`) | Um campo escondido no mesmo formulário | Cada URL faz uma só coisa, e o "Enviar link da palavra-passe" passa a enviar sempre o link da palavra-passe |
| A auditoria do backoffice passa a incluir as orientações (criar, alterar, apagar) | Só no portal | Plano, secção 11: as orientações fazem parte da auditoria de contas |
| Paginação de 50 eventos, com filtros por pessoa e por ação | Exportação em CSV | O roadmap só pede a consulta. O CSV pode vir depois, se o centro o pedir |

**Dependências novas:** nenhuma.

**Migração:** `core/migrations/0004_audit_mentorships.py` só acrescenta as novas escolhas de ação do `AuditEvent` (orientação criada, alterada, terminada e apagada). Não tem SQL e não é destrutiva.

## Decisões de negócio

**Pedidas pelo utilizador nesta tarefa:**

- **Dois botões para quem tem o 2FA por configurar:** "Enviar link do 2FA" envia o link de configuração do 2FA, que pede a palavra-passe atual. "Enviar link da palavra-passe" envia o link de recuperação (ou o convite), e esse fluxo já termina na configuração do 2FA. Assim, quem esqueceu a palavra-passe não fica preso. Quem não tem o 2FA por configurar continua a ver só o botão da palavra-passe.

**Interpretações e valores escolhidos por mim, a confirmar na revisão:**

| Regra implementada | Base |
|---|---|
| Alterar uma filiação exige o nível do ator no polo para o papel atual **e** para o papel novo. O secretariado não altera uma filiação de coordenação, nem para a baixar | Roadmap: "com o mesmo teto de papéis". Baixar o papel de alguém acima de nós seria uma forma de lhe tirar acesso |
| Mudar o papel (ou o subpapel) de uma filiação que já começou não reescreve o passado: a filiação antiga termina ontem e é criada uma nova a partir de hoje, com a data de fim pedida. Uma filiação que começa hoje ou mais tarde muda no próprio registo | As horas por profissional e por estagiária (tarefas 10 e 11) têm de continuar certas. Fica na auditoria como "filiação terminada" + "filiação criada", com `role_change` |
| Datas: a data de início de uma filiação ou orientação que já começou não muda; uma data de início nova não pode ser no passado; a data de fim não pode ser anterior a ontem (ontem é "termina já") | O passado fica como estava, como no "Remover do polo" |
| Só se alteram filiações e orientações ativas ou futuras. As terminadas ficam como estão | O histórico não se reescreve |
| Quem gere membros também pode alterar a própria filiação, até ao seu nível | Já podia acrescentar-se a si próprio uma filiação nova com o mesmo e-mail; não é um poder novo |
| Mudar para um papel de staff envia o link do 2FA, como ao atribuir o papel (pendente da tarefa 4). Mudar só as datas não envia nada. Se o envio falhar, o papel fica e aparece o aviso | Plano, secção 5, e o comportamento do backoffice |
| "Terminar orientação": uma orientação ativa termina ontem (a orientadora deixa de ver a orientanda logo); uma que começa hoje ou mais tarde é apagada. A auditoria guarda o antes | O mesmo critério do "Remover do polo" |
| Nas orientações, a conta do `AuditEvent` é a orientanda, e os detalhes guardam os e-mails das duas | A orientação expõe o horário e as horas da orientanda |
| A coordenação vê na auditoria: (1) todos os eventos ligados ao seu polo; (2) os eventos da conta inteira (logins falhados, palavra-passe, 2FA, desativação) de quem tem uma filiação ativa ou futura no polo. Não vê os eventos ligados a outros polos, nem os da conta inteira de antigos membros, nem os logins falhados de e-mails sem conta | Plano, secção 11 ("membros do seu polo") e secção 4 (nunca a atividade noutros polos). Escolhi a leitura mais restritiva |
| Nos eventos da conta inteira, a coordenação vê o nome de quem fez a ação, mesmo que seja de outro polo (por exemplo, quem desativou a conta) | É uma ação sobre a conta inteira, que afeta o polo |
| O secretariado vê o ecrã de orientações, mas não a auditoria | Permissões já registadas na tarefa 3 (`core.manage_mentorships` e `core.view_audit`) |

## Ficheiros criados ou alterados

**Criados**
- `portal/core/mentorships.py`: listar, criar, alterar e terminar orientações.
- `portal/core/views/mentorships.py`, `portal/core/views/audit.py`.
- `portal/core/templates/core/`: `mentorship_list.html`, `mentorship_form.html`, `membership_edit.html`, `audit_list.html`, `_audit_details.html`.
- `portal/core/migrations/0004_audit_mentorships.py`.
- Testes: `test_membership_edit.py`, `test_mentorship_screens.py`, `test_audit_view.py`.

**Alterados**
- `portal/core/accounts.py`: `change_membership`; `send_recovery_link` passa a enviar sempre o link da palavra-passe; novo `resend_two_factor_link` (com `NothingToSend`).
- `portal/core/permissions.py`: `can_change_membership`, constantes `MANAGE_MENTORSHIPS` e `VIEW_AUDIT`.
- `portal/core/models.py`: `Period.check_change`, novas ações do `AuditEvent`.
- `portal/core/audit.py`: `mentorship_snapshot`, `events_in`.
- `portal/core/forms.py`: `MembershipForm`, `MentorshipForm`, `MentorshipDatesForm`, `AuditFilterForm`.
- `portal/core/views/members.py`: alterar filiação, vista do link do 2FA, ligações na lista de membros.
- `portal/core/views/auth.py` e `home.html`: ligações para as orientações e a auditoria em cada polo.
- `portal/core/templates/core/member_list.html` e `_memberships.html`: os dois botões e a ligação "Alterar" em cada filiação.
- `portal/core/admin.py`: auditoria das orientações no backoffice.
- `portal/core/static/core/portal.css`, `portal/locale/pt_PT/LC_MESSAGES/django.po`.
- `portal/core/tests/test_two_factor_roles.py`: o botão do 2FA mudou de URL; testes dos dois botões.
- `docs/roadmap.md`, `docs/registo/README.md`.

## Como funciona

**Alterar uma filiação.** Na lista de membros, cada filiação ativa ou futura que o ator pode alterar tem a ligação "Alterar" (`/polos/<id>/filiacoes/<id>/alterar/`). O formulário só oferece os papéis até ao nível do ator. Se a filiação já começou, a data de início aparece desativada. `accounts.change_membership` verifica `can_change_membership` (nível para o papel atual e para o novo), recusa filiações terminadas e aplica `check_change`. Se o papel mudar numa filiação já começada, termina-a ontem e cria outra a partir de hoje, tudo numa transação: se a nova falhar (por exemplo, a pessoa já tem esse papel nessas datas), nada muda. Se o papel mudou, chama `offer_two_factor_link`.

**Orientações.** `/polos/<id>/orientacoes/` lista as orientações ativas e futuras do polo. "Adicionar orientação" só oferece como orientadoras os profissionais do polo e como orientandas as estagiárias do polo; o modelo confirma que as filiações existem nas datas pedidas. "Alterar datas" e "Terminar orientação" usam as mesmas regras de datas das filiações. Uma orientação de outro polo dá 404, e quem não tem `core.manage_mentorships` no polo recebe 403.

**Auditoria.** `/polos/<id>/auditoria/` exige `core.view_audit` (coordenação e Admin). Mostra `events_in(location)`, do mais recente para o mais antigo, 50 por página, com filtros por pessoa (só membros atuais e futuros do polo) e por ação. Os "antes" e "depois" aparecem por extenso ("Profissional (Estagiária), 01/01/2026 – 30/06/2026").

**Os dois botões.** Com o 2FA por configurar e palavra-passe definida (`needs_two_factor_link`), a linha mostra "Enviar link do 2FA" (`enviar-link-2fa/`, `resend_two_factor_link`) e "Enviar link da palavra-passe" (`enviar-link/`, `send_recovery_link`). Os dois verificam `can_send_recovery_link` e contam para o limite de 3 e-mails por hora. Se o 2FA já tiver sido configurado entretanto, o botão do 2FA não envia nada e avisa.

## Comandos de verificação e resultados

Corridos no Docker, a partir da raiz do repositório:

| Comando | Resultado |
|---|---|
| `docker compose -f deploy/docker-compose.dev.yml run --rm app pytest` | 636 passaram (578 antes desta tarefa) |
| `... run --rm --no-deps app ruff check .` | sem erros |
| `... run --rm --no-deps app ruff format --check .` | sem alterações |
| `... run --rm app python manage.py makemigrations --check --dry-run` | sem migrações em falta |
| `docker compose -f deploy/docker-compose.yml run --rm --no-deps app python manage.py check --deploy --fail-level WARNING` | sem avisos (com um `.env` descartável e uma chave aleatória, como na CI) |
| `deploy/tests/check-production.sh` | todas as verificações passaram |
| `... run --rm --no-deps app pip-audit ...` | sem vulnerabilidades conhecidas |

**Ecrãs:** não foram vistos num browser. Os testes renderizam todos os templates novos.

**Verificação por mutação:** parti 11 regras novas, uma a uma (por exemplo, verificar só o papel novo no teto, mostrar a auditoria da conta inteira de toda a gente, mudar o papel no próprio registo de uma filiação já começada, deixar a data de fim ir para antes de ontem, apagar em vez de terminar uma orientação ativa, tirar a verificação de permissão às orientações e ao link do 2FA, não enviar o link do 2FA ao mudar para staff). Duas sobreviveram à primeira: o teto do papel atual (só havia teste para subir o papel) e a permissão em `resend_two_factor_link` (a vista já a travava). Acrescentei testes, e as 11 passaram a ser apanhadas. O script não fica no repositório.

## Problemas encontrados e como foram resolvidos

- **Traduções "fuzzy":** o `makemessages` voltou a propor traduções erradas (por exemplo "Mentorship created" → "Filiação criada"). Foram todas revistas à mão.
- **`check --deploy` local:** com o `.env.example` tal como está, falha no `SECRET_KEY` curto. A CI gera uma chave aleatória; fiz o mesmo localmente.

## Pendentes para tarefas seguintes

- **Exportação em CSV da auditoria:** não pedida; fácil de acrescentar com o mesmo `_csv_cell` da listagem.
- **Tarefa 9:** a visibilidade da orientadora (horário e horas) já usa `mentees_of`, que o ecrã de orientações alimenta.
- **A confirmar com o centro:** se a coordenação deve ver também a auditoria da conta inteira de antigos membros do polo (hoje não vê).
