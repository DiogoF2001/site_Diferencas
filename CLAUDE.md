# CLAUDE.md — Site e serviços Diferenças

Repositório do novo site do CDI Diferenças e do **portal** (área reservada) para profissionais. O primeiro serviço do portal é a **gestão de salas**.

## Fonte de verdade

- `docs/plano.md` é o plano aprovado (a versão visual está em `docs/plano.html`). As decisões de produto, permissões e regras estão lá.
- `docs/roadmap.md` tem as tarefas por ordem, cada uma com critérios de aceitação.
- Se uma tarefa exigir uma decisão que não está no plano, **pergunta antes de implementar**. Não inventes regras de negócio.
- Se uma decisão mudar, atualiza `docs/plano.md` no mesmo PR, mas só depois de o utilizador aprovar a mudança.

## Forma de trabalhar

1. Uma tarefa do roadmap por branch (`feat/<nº>-<nome-curto>`) e um PR por tarefa.
2. Antes de escrever código, apresenta um plano curto e espera aprovação. O plano inclui: modelos e campos, ficheiros a criar ou alterar, permissões envolvidas e os testes que vais escrever.
3. Cada regra de permissão tem testes **positivos e negativos**. Por exemplo: "secretariado do polo A não vê detalhes no polo B".
4. Antes de abrir o PR, corre os testes, o lint e o `check --deploy`. Os comandos estão na secção "Comandos".
5. Mensagens de commit em inglês, no imperativo e curtas.

## Estrutura do repositório

```
portal/      Aplicação Django (área reservada)
site/        Site público (a definir; não mexer sem pedido)
prototipo/   Protótipo clicável estático (HTML, dados fictícios)
docs/        Plano e roadmap
deploy/      Docker Compose, Caddyfile, scripts de backup
```

## Stack (não mudar sem aprovação)

- Python 3.12+, **Django 5.2 LTS** (migração para a 6.2 LTS quando sair, em abril de 2027).
- **PostgreSQL**. As reservas sobrepostas são impedidas por `ExclusionConstraint` (`django.contrib.postgres`, com `btree_gist`).
- Interface: templates Django + **HTMX**. Calendário: **EventCalendar (vkurko, licença MIT)**. Não usar o FullCalendar Premium.
- Tarefas agendadas: um serviço `worker` separado.
- Testes: `pytest` + `pytest-django`. Lint e formatação: `ruff`.
- Docker Compose com os serviços: `proxy` (Caddy), `app` (Gunicorn), `worker`, `db`, `backup`.
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
| Admin (global) | `is_superuser` + papel técnico global |
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

- **Permissões sempre por polo e sempre no servidor.** Usa uma única função central (por exemplo `has_perm_in(user, "salas.approve", location)`). Nunca verifiques nomes de papéis no código das vistas. Cada módulo declara as suas permissões com prefixo (`salas.*`, `core.*`).
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

Esta secção é preenchida na tarefa 1 do roadmap: arrancar o ambiente, correr testes, lint, migrações e criar o admin.
