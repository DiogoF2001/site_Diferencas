# Tarefa 4 — Contas e autenticação

## Objetivo

Pôr pessoas a entrar no portal com segurança e dar ao secretariado e à coordenação as ferramentas para gerir quem tem acesso a cada polo: convites, recuperação de palavra-passe, 2FA, limite de tentativas, expiração de sessões, desativação de contas, gestão de membros, listagem da coordenação e auditoria de contas. É a primeira tarefa com ecrãs.

## Decisões técnicas

| Escolha | Alternativas | Porquê |
|---|---|---|
| **django-otp** (licença Unlicense) para o TOTP | `pyotp` com modelo próprio; django-two-factor-auth | Traz o modelo do dispositivo, a tolerância de relógio, a proteção contra reutilização de códigos e o atraso progressivo após códigos errados. O django-two-factor-auth traria mais dependências (formtools, phonenumbers) e ecrãs que não queremos |
| **qrcode** (BSD) para o QR em SVG | Pillow; QR gerado no browser | Python puro, SVG sem Pillow, e nada de JavaScript de terceiros |
| Limite de tentativas de login contado no `AuditEvent` | django-axes | Os logins falhados já têm de ficar na auditoria (plano, secção 11). Contar essas linhas evita uma dependência e uma segunda tabela. Por e-mail, para proteger cada conta. O limite por IP fica para a tarefa 14 (decisão da revisão), com o IP do `X-Forwarded-For` definido pelo Caddy |
| Convites e recuperação com o mesmo token de uso único (`PasswordResetTokenGenerator`, 48 h), com `is_active` no hash | Modelo `Invitation` | O token deixa de valer quando a palavra-passe é definida, quando a pessoa entra ou quando a conta é desativada. Não guarda nada na base de dados. Um "convite" é só um link de definição de palavra-passe para uma conta que nunca teve uma |
| O acesso por filiação é verificado no backend de autenticação (`user_can_authenticate`) | Worker que desativa contas; middleware próprio | O Django chama-o no login e em cada pedido, por isso a sessão de uma estagiária termina à meia-noite do último dia sem esperar pelo worker e sem mexer em `is_active` |
| Um middleware obriga ao segundo fator antes de qualquer página, incluindo o backoffice | Decorador em cada vista | Não depende de cada vista se lembrar. O backoffice tem ainda `has_permission` a exigir a sessão verificada, e o `/admin/login/` redireciona para o login do portal, que é o que tem o limite de tentativas |
| As regras ficam em `core/accounts.py` e `core/permissions.py`; as vistas só recolhem dados | Regras nas vistas | Cada ação verifica a sua permissão mesmo que seja chamada fora da vista. Há testes que o provam sem passar pelo formulário |
| `core.db.revoke_changes(tabela)` lê os privilégios concedidos e retira UPDATE/DELETE/TRUNCATE a quem os tiver, exceto ao dono | Nome do utilizador da app numa variável de ambiente do `migrate` | Não precisa de saber o nome do utilizador da app e não faz nada em desenvolvimento. Serve também para o `BookingEvent` da tarefa 8 |
| Modelo `AuditEvent` com `save()`/`delete()` e o queryset a recusar alterações | Só a restrição na base de dados | Um erro de programação falha logo em desenvolvimento e nos testes, onde o utilizador é o dono e a base de dados deixaria passar |
| Sessão de 8 h no máximo (`PORTAL_SESSION_HOURS`), que termina também ao fechar o browser | Tempo de inatividade deslizante | Cobre um dia de trabalho com um só login. É configurável |
| Limites por omissão: 5 logins falhados em 15 min por e-mail; 3 e-mails de convite/recuperação por conta e por hora | – | Valores habituais. Todos configuráveis por variáveis de ambiente |
| CSV com `;`, BOM UTF-8 e células começadas por `= + - @` prefixadas com `'` | Vírgula, sem BOM | É o que o Excel em português abre bem. O prefixo impede que um nome seja executado como fórmula |
| Templates simples com a identidade do protótipo, sem HTMX nem fontes externas | Esperar pela tarefa 9 | Os ecrãs de contas não precisam de interatividade. A fonte Atkinson cai para a do sistema, para não depender do Google Fonts |

**Dependências novas:** `django-otp` 1.7.5 (Unlicense) e `qrcode` 8.2 (BSD). Ambas sem serviços externos.

**Migração:** `core/migrations/0002_audit_event.py` cria a tabela e retira as alterações ao utilizador da app. Não é destrutiva. O `django_otp.plugins.otp_totp` traz as suas próprias migrações.

## Decisões de negócio

**Tomadas pelo utilizador nesta tarefa, e registadas no plano (secções 4 e 5):**

- **Login só com filiação ativa:** sem uma filiação ativa num polo ativo, o login é recusado (o Admin é a exceção). Quem só tem uma filiação futura define a palavra-passe pelo convite, mas só entra a partir da data de início.
- **Listagem da coordenação:** mostra todas as pessoas com filiação ativa ou futura no polo, não só quem tem o papel Profissional.
- **"Esqueci-me da palavra-passe" público:** fica preparado, mas desligado (`PORTAL_SELF_PASSWORD_RESET=0`). Por agora, só o secretariado e a coordenação enviam links.
- **Reativar uma conta:** possível, com a mesma regra de desativar.

**Decididas pelo utilizador na revisão do PR #6, e registadas no plano (secção 5) e no roadmap:**

- **Sem 2FA, o staff não entra só com a palavra-passe.** Quem tem 2FA obrigatório e não tem dispositivo configura-o logo a seguir a definir a palavra-passe, no fluxo do link de convite ou de recuperação (o token prova o acesso ao e-mail). Quem não o concluir precisa de um link novo. O Admin mantém o fluxo do `ensure_admin` e o `reset_2fa`.
- **Tarefa 4b**, antes da 5: ecrã de orientações (`core.manage_mentorships`), alterar o papel ou as datas de uma filiação no portal, e consulta da auditoria pela coordenação (`core.view_audit`).
- **Tarefa 14:** passkeys opcionais e limite de logins por IP, com o IP do `X-Forwarded-For` do Caddy.

**Decididas pelo utilizador no ajuste do PR #6 (acumulação de papéis), e registadas no plano (secção 5):**

- **Link ao atribuir o papel:** atribuir secretariado ou coordenação a alguém sem dispositivo envia o link de configuração do 2FA, que conta para o limite de envios e fica no `AuditEvent`. Até ao início do papel, o portal mostra um aviso.
- **Tolerância de 7 dias** (configurável) a partir do início do papel, para quem já entrou antes (`last_login` preenchido): entra com a palavra-passe, mas só acede ao ecrã de configuração do 2FA. Ao concluir, recebe um e-mail de confirmação, que fica no `AuditEvent`. Depois, precisa de um link novo.
- **Contas que nunca entraram:** só o link. O Admin fica como estava.

**Interpretações e valores escolhidos por mim, a confirmar na revisão:**

| Regra implementada | Base |
|---|---|
| "Remover do polo" termina hoje as filiações ativas (data de fim = ontem) e apaga as que ainda não começaram ou começaram hoje. A auditoria guarda o antes | Plano, secção 5 (a data de fim é o último dia com acesso). Uma filiação que começou hoje não pode acabar ontem |
| Adicionar um e-mail que já tem conta não envia e-mail nenhum | Plano, secção 4 ("cria-se apenas a nova filiação"). As notificações são da tarefa 13 |
| Uma conta desativada pode receber uma filiação nova, mas continua desativada até alguém com nível para isso a reativar | Evita que o secretariado de um polo reative, por esta via, uma conta que não pode gerir |
| O 2FA passa a ser obrigatório quando o papel de secretariado ou coordenação está ativo (contam as datas, mesmo num polo inativo) | Plano, secção 5. Mais 2FA nunca tira acesso a ninguém |
| Os profissionais podem ativar o 2FA, e quem o tem é sempre pedido o código | "Recomendado para Profissionais" (plano, secção 5) |
| Quem não sabe a palavra-passe vê sempre "E-mail ou palavra-passe incorretos". Só quem acerta na palavra-passe de uma conta sem acesso vê "Esta conta não tem acesso ao portal neste momento" | Não revela que contas existem |
| O envio de um link a uma conta que nunca definiu palavra-passe é um novo convite | Um convite expirado resolve-se com o mesmo botão |
| O "Esqueci-me" público, quando for ligado, só envia para contas que já têm palavra-passe (comportamento do Django) | As outras precisam de um convite novo, pedido ao secretariado |
| No fluxo do link, o passo do 2FA fica aberto 30 minutos, só na sessão do browser que usou o link, e acaba se for usado outro link ou a conta for desativada. No fim, a pessoa vai para o login, que pede a palavra-passe e o código | Revisão do PR #6. O passo não inicia sessão, tal como a página da palavra-passe |
| Também configura o 2FA no link quem só tem um papel de secretariado ou coordenação futuro | Sem isso, quem é convidado antes da data de início ficaria sem conseguir entrar nesse dia |
| Fora da tolerância, uma sessão sem dispositivo de quem passou a precisar de 2FA (papel que começou, 2FA reposto) termina, com a mensagem para pedir um link novo. Dentro da tolerância, a sessão só chega ao ecrã de configuração | Revisão do PR #6 e ajuste da acumulação de papéis |
| O link de configuração do 2FA pede a palavra-passe atual, e os erros contam como logins falhados (com o mesmo bloqueio). Depois segue para o mesmo passo `/conta/2fa/ativar/` do convite | O link prova o e-mail; a palavra-passe impede que quem só tenha acesso ao e-mail configure o 2FA no lugar da pessoa. Quem não se lembrar da palavra-passe pede um link de recuperação, que também configura o 2FA |
| O link de configuração do 2FA vale 48 h, como os outros, e não deixa de valer quando a pessoa entra noutro papel entretanto (ao contrário do link da palavra-passe). Acaba com uma palavra-passe nova, com a conta desativada, quando o papel deixa de existir ou quando já há dispositivo | Quem acumula papéis entra no portal com frequência; se cada login anulasse o link, este quase nunca funcionaria |
| A uma conta existente que nunca definiu a palavra-passe, o novo papel reenvia o convite em vez do link do 2FA | O convite já termina no passo do 2FA |
| Se o envio do link falhar (limite ou SMTP), a filiação não é criada e o formulário explica porquê. No backoffice, a filiação fica guardada e aparece um aviso | Igual ao convite no portal. No backoffice o Admin pode reenviar depois |
| O backoffice envia o link ao criar uma filiação de staff ou ao mudar o papel para staff; guardar sem mudar o papel não envia nada | Evita reenvios a cada gravação |
| A tolerância conta do início da filiação de staff ativa mais antiga: com início no dia D, entra nos dias D a D+6 e é recusado a partir de D+7 (o "dia 8") | "7 dias a partir do início do papel" |
| O e-mail de confirmação vai sempre que alguém, exceto o Admin, ativa o 2FA com a sessão iniciada (tolerância, papel futuro ou profissional que o queira). Não vai no passo do link, onde a pessoa já provou o acesso ao e-mail. Se o SMTP falhar, o 2FA fica ativo e o erro vai para os logs | O objetivo é avisar quando só foi usada a palavra-passe. Um servidor de e-mail em baixo não deve impedir ninguém de ativar o 2FA |
| O aviso do papel futuro aparece em todas as páginas a quem tem sessão iniciada, papel de staff futuro e nenhum dispositivo, com uma ligação para `/conta/2fa/configurar/` | "Até à data de início do papel, mostra no portal um aviso" |
| As ações feitas pelo Admin no backoffice (ativar/desativar contas, criar/alterar/apagar filiações) também ficam no `AuditEvent` | Plano, secção 11 |

## Ficheiros criados ou alterados

**Criados**
- `portal/core/accounts.py`: ações sobre contas (adicionar membro, remover do polo, desativar/reativar, repor 2FA, enviar links).
- `portal/core/audit.py`: `record()`, limite de logins e de e-mails, e o registo dos logins falhados.
- `portal/core/backends.py`: backend que exige filiação ativa.
- `portal/core/middleware.py`: obriga ao segundo fator.
- `portal/core/tokens.py`: token de uso único para convites e recuperação.
- `portal/core/forms.py`: login, novo membro e código 2FA.
- `portal/core/db.py`: `revoke_changes()` para as tabelas só de acrescentar.
- `portal/core/views/` (`auth.py`, `two_factor.py`, `members.py`; `health.py` é o antigo `views.py`).
- `portal/core/templates/core/`: base, login, palavra-passe, 2FA (incluindo o passo do link e a página de passo expirado), início, membros, listagem e os e-mails.
- `portal/core/static/core/` (`portal.css`, `logo.png` copiado do protótipo).
- `portal/core/management/commands/reset_2fa.py`.
- `portal/core/migrations/0002_audit_event.py`.
- Testes: `test_audit.py`, `test_login.py`, `test_two_factor.py`, `test_members.py`.

**Alterados**
- `portal/core/models.py`: `AuditEvent` e as bases só de acrescentar.
- `portal/core/permissions.py`: `has_portal_access`, `requires_two_factor`, `lacks_required_two_factor`, `enrols_two_factor_by_link`, `two_factor_grace_ends`, `may_log_in_without_two_factor`, `upcoming_two_factor_roles`, `members_of`, `can_send_recovery_link`.
- Ajuste da acumulação de papéis: `core/context_processors.py`, `core/migrations/0003_audit_two_factor_emails.py` (só as novas escolhas de ação, sem SQL), os templates `two_factor_link.html` e `email/two_factor_link_*` e `email/two_factor_enabled_*`, e `tests/test_two_factor_roles.py`. `PORTAL_TWO_FACTOR_GRACE_DAYS` foi acrescentada às definições, ao `docker-compose.yml` e ao `.env.example`.
- `portal/core/admin.py`: backoffice só com 2FA, auditoria das alterações, `AuditEvent` só de leitura, sem o admin dos dispositivos TOTP (mostraria os segredos).
- `portal/config/settings.py`, `portal/config/urls.py`, `portal/core/urls.py`, `portal/core/apps.py`.
- `portal/requirements/` (`base.in`, `base.txt`, `dev.txt`).
- `portal/locale/pt_PT/LC_MESSAGES/django.po`.
- Testes antigos: `test_backoffice.py` (o backoffice exige 2FA), `test_users.py` (o login exige filiação), `test_health.py` (novo caminho da vista), `helpers.py` (`login_verified`, variáveis SMTP de produção).
- `deploy/Dockerfile`, `deploy/docker-compose.yml`, `deploy/.env.example`: SMTP e regras das contas.
- `deploy/tests/check-production.sh`: privilégios da tabela de auditoria e login com 2FA de ponta a ponta.
- `CLAUDE.md`, `docs/plano.md`, `docs/plano.html`, `docs/roadmap.md`, `docs/registo/README.md`.

## Como funciona

**Entrar.** O login (`/conta/entrar/`) pede e-mail e palavra-passe. Antes de verificar a palavra-passe, conta os `AuditEvent` de login falhado para esse e-mail nos últimos 15 minutos; com 5 ou mais, recusa. Cada falha (incluindo para e-mails sem conta) fica no `AuditEvent` através do sinal `user_login_failed` do Django. O backend `MembershipBackend` só aceita a conta se `has_portal_access` for verdade: o Admin, ou uma filiação ativa hoje num polo ativo. O Django volta a fazer esta verificação em cada pedido, por isso uma sessão aberta termina quando a filiação acaba ou a conta é desativada.

**Segundo fator.** Depois da palavra-passe, o `TwoFactorMiddleware` manda quem tem um dispositivo para `/conta/2fa/verificar/`. Até lá, só essa página e o "Sair" respondem. Ao verificar, a sessão muda de chave. Os códigos errados ficam na auditoria e o django-otp atrasa as tentativas seguintes.

**Primeira configuração do 2FA.** O secretariado e a coordenação sem dispositivo não entram: o login recusa-os, depois de a palavra-passe estar certa, com a mensagem para pedirem um link novo (`lacks_required_two_factor`). Configuram o 2FA no fluxo do link: depois de definirem a palavra-passe em `/conta/definir/…/`, a página guarda na sessão a conta, um token ligado à nova palavra-passe e a hora, e segue para `/conta/2fa/ativar/`. Essa página mostra o QR e a chave, e só ativa o dispositivo com um primeiro código certo, dentro de 30 minutos e enquanto o token for válido. Os códigos errados ficam na auditoria e são atrasados pelo django-otp. Depois a pessoa entra normalmente, com a palavra-passe e o código. Se uma sessão iniciada perder o dispositivo (2FA reposto) ou ganhar um papel que o exige, o middleware termina-a, a menos que esteja na tolerância. O Admin e os profissionais configuram o 2FA em `/conta/2fa/configurar/`, já com a sessão iniciada.

**Acumulação de papéis.** Quando o secretariado, a coordenação ou o Admin dão um papel de staff a uma conta existente sem dispositivo, `send_two_factor_link` envia o link `/conta/2fa/link/…/`. O token desse link (`TwoFactorLinkTokenGenerator`) é diferente do da palavra-passe e não inclui o `last_login`. A página pede a palavra-passe atual e segue para o passo `/conta/2fa/ativar/`. Até ao início do papel, o context processor `two_factor_notice` põe um aviso no topo de cada página. Quando o papel começa, quem já tinha entrado antes e ainda não tem dispositivo entra com a palavra-passe durante `PORTAL_TWO_FACTOR_GRACE_DAYS` (`two_factor_grace_ends`, `may_log_in_without_two_factor`), e o middleware só o deixa no ecrã de configuração. Ao concluir, `send_two_factor_notice` envia o e-mail de confirmação e regista `two_factor_notice_sent`.

**Convidar e recuperar.** Em "Membros" → "Adicionar membro", o secretariado ou a coordenação escolhe o papel (só até ao seu nível no polo). Um e-mail novo cria a conta sem palavra-passe e envia o convite; um e-mail existente recebe só a filiação. Tudo corre numa transação: se o e-mail falhar, não fica conta nem filiação. O link leva a `/conta/definir/…/`, só funciona uma vez e expira em 48 h. "Enviar link da palavra-passe" manda um convite ou um link de recuperação, conforme a conta já tenha ou não palavra-passe, a quem tenha filiação ativa ou futura nesse polo, com o limite de 3 por hora por conta.

**Gerir membros.** A página de membros de um polo mostra só as filiações desse polo. Os botões aparecem conforme as regras do motor, que são verificadas outra vez no servidor: remover do polo (`can_remove_from_location`), desativar, reativar e repor o 2FA (`can_manage_account`), enviar link (`can_send_recovery_link`). Quem não está no polo dá 404; quem não tem permissão dá 403.

**Listagem da coordenação.** `/polos/<id>/profissionais/` lista quem tem filiação ativa ou futura no polo, com os papéis e as datas. "Mostrar os papéis noutros polos" acrescenta só os papéis e os polos. Exporta em CSV.

**Auditoria.** `AuditEvent` guarda a ação, quem a fez, a conta, o polo, o e-mail escrito (nos logins falhados) e o antes e depois. O modelo recusa alterações e apagamentos, e a migração retira UPDATE/DELETE/TRUNCATE ao utilizador da app. Não há vista de consulta para a coordenação (fica para depois); o Admin vê-a no backoffice, só de leitura.

**Emergência do Admin.** `manage.py reset_2fa <e-mail>` apaga os dispositivos da conta e regista-o sem autor.

## Comandos de verificação e resultados

Corridos no Docker, a partir da raiz do repositório:

| Comando | Resultado |
|---|---|
| `docker compose -f deploy/docker-compose.dev.yml run --rm app pytest` | 572 passaram (425 antes desta tarefa; 513 na primeira versão do PR, 537 depois da revisão) |
| `... run --rm --no-deps app ruff check .` | sem erros |
| `... run --rm --no-deps app ruff format --check .` | sem alterações |
| `... run --rm app python manage.py makemigrations --check --dry-run` | sem migrações em falta |
| `docker compose -f deploy/docker-compose.yml run --rm --no-deps app python manage.py check --deploy --fail-level WARNING` | sem avisos (com um `.env` descartável copiado do `.env.example`, como na CI) |
| `deploy/tests/check-production.sh` | todas as verificações passaram, incluindo as 4 novas da tabela de auditoria, o login do admin com configuração do 2FA e o convite de um membro do secretariado: palavra-passe, 2FA no link, recusa só com a palavra-passe a meio e login com código. Também a tolerância: quem já entrou e ganha hoje um papel de secretariado entra, só chega ao ecrã do 2FA, configura-o (o e-mail de confirmação falha, porque o SMTP é fictício, e o 2FA fica ativo) e depois abre o portal |
| `... run --rm --no-deps app pip-audit ...` | sem vulnerabilidades conhecidas |

**Ecrãs:** não foram vistos num browser. Os testes renderizam todos os templates, e o `check-production.sh` percorre o login e a configuração do 2FA na imagem de produção.

**Verificação por mutação do ajuste da acumulação de papéis:** 10 mutações às regras novas. Por exemplo, `<` por `<=` no fim da tolerância (o dia 8), retirar a condição do `last_login`, contar a tolerância do papel mais recente, não verificar a palavra-passe no link, não enviar a confirmação, não terminar a sessão depois da tolerância e enviar o link a cada gravação no backoffice. Os testes apanharam 8. As 2 que sobreviveram eram verificações redundantes (o dispositivo no hash do token e a palavra-passe utilizável no link), já garantidas por outras regras, e foram retiradas.

**Verificação por mutação:** parti 17 regras novas, uma a uma (por exemplo, tirar a exigência de filiação no backend, desligar o bloqueio de login, não prefixar as células do CSV, não mudar a chave da sessão depois do 2FA). Duas sobreviveram à primeira: o teto de papéis em `add_member` e a regra do link de recuperação, porque a vista já as travava antes (escolhas do formulário e 404). Acrescentei testes que chamam as funções diretamente, e as 17 passaram a ser apanhadas. O script não fica no repositório.

## Problemas encontrados e como foram resolvidos

- **A imagem de produção deixou de construir:** as definições passaram a exigir o SMTP fora do modo de desenvolvimento, e o `collectstatic` do Dockerfile corre com `DEBUG=0`. Acrescentei valores descartáveis no mesmo passo, como já se fazia para a base de dados.
- **Testes antigos do backoffice:** entravam sem 2FA. Passaram a usar `login_verified`, e os do login do backoffice foram substituídos por testes do redirecionamento para o login do portal e da exigência do 2FA.
- **Traduções "fuzzy":** o `makemessages` propôs traduções erradas para textos novos parecidos com antigos (por exemplo "Members" → "filiação"). Foram todas revistas à mão. "ativa"/"desativada" para contas usam um contexto próprio, para não colidir com "ativo" do polo.
- **Primeira configuração do 2FA (revisão do PR #6):** na primeira versão, quem descobrisse a palavra-passe de alguém do staff sem 2FA podia configurá-lo no lugar dessa pessoa. Agora a configuração exige o token do link, ou seja, acesso ao e-mail.
- **Middleware e mensagens:** para mostrar a mensagem depois de terminar a sessão, o `TwoFactorMiddleware` passou para depois do `MessageMiddleware`.

## Pendentes para tarefas seguintes

- **Tarefa 4b** (acrescentada ao roadmap na revisão): ecrã de orientações, alterar uma filiação no portal e consulta da auditoria pela coordenação.
- **Tarefa 14:** passkeys opcionais e limite de logins por IP.
- **Papel de staff que começa mais tarde:** resolvido no ajuste da acumulação de papéis, com o link automático, o aviso e a tolerância de 7 dias.
- **Tarefa 4b:** ao alterar o papel de uma filiação no portal, chamar `accounts.send_two_factor_link`, como no backoffice.
- **Tarefa 8:** usar `core.db.revoke_changes("salas_bookingevent")` na migração do `BookingEvent` e acrescentar as verificações ao `check-production.sh`, como aqui.
- **Tarefa 13:** o envio dos e-mails é síncrono, no pedido. Quando houver notificações, pode passar para o worker.
- **Tarefa 14:** CSP. Os templates não têm JavaScript nem estilos inline (o QR é SVG inline), por isso uma CSP restrita deve encaixar.
- **A confirmar com o centro:** o servidor SMTP, os limites (5 tentativas/15 min, 3 e-mails/hora) e a duração da sessão (8 h).
