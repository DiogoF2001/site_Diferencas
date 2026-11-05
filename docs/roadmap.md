# Roadmap — Portal Diferenças

Cada tarefa é uma branch e um PR. A ordem é a recomendada. Os detalhes de cada regra estão em `docs/plano.md`.

## 0. Protótipo clicável (opcional, antes do MVP)
HTML estático em `prototipo/`, com dados fictícios, para validar com o secretariado e com 2–3 profissionais.
- [x] Vistas: Profissional, Secretariado, Coordenação e Admin, com um seletor de perfil no topo.
- [x] Grelha do polo (com detalhes para o staff; só "Ocupado" para os profissionais), "O meu horário", fila de pedidos com conflito e sugestão de outra sala, formulário de pedido.
- [x] Identidade visual do novo site (espaço para o logótipo real em `prototipo/assets/logo.png`, azuis e verde-lima, fonte Atkinson Hyperlegible).

## 1. Esqueleto e infraestrutura
- [x] Projeto Django 5.2 LTS em `portal/`, com a configuração lida de variáveis de ambiente, idioma `pt-pt` e fuso `Europe/Lisbon`.
- [x] `deploy/docker-compose.yml` com `proxy` (Caddy), `app` (Gunicorn), `worker`, `db` (PostgreSQL) e `backup` (pg_dump diário encriptado). Variante de desenvolvimento com hot reload.
- [x] `.env.example`, `.gitignore`, endpoint de healthcheck.
- [x] `pytest`, `pytest-django`, `ruff` configurados.
- [x] GitHub Actions: lint, testes com Postgres em serviço, `check --deploy` e `pip-audit` em cada PR.
- [x] Dependabot (pip, Docker, GitHub Actions).
- [x] Secção "Comandos" do `CLAUDE.md` e um README com o arranque local.

## 2. Núcleo: utilizadores, polos e filiações
- [x] Utilizador personalizado com login por e-mail (único).
- [x] `Location`, `Membership` (papel, subpapel, início, fim; vários papéis por polo), `Mentorship`.
- [x] Management command para criar o admin a partir do `.env` (idempotente).
- [x] Backoffice Django só para o admin.
- [x] Utilizadores da base de dados separados (dono sem superutilizador, app, backup só de leitura), `compilemessages` na imagem e WhiteNoise testado, em `deploy/tests/check-production.sh`.

## 3. Motor de permissões
- [x] Registo de permissões por módulo, mais o mapeamento papel → permissões.
- [x] Função central `has_perm_in(user, perm, location)` e helpers para querysets.
- [x] Teto de atribuição (até ao próprio nível) e regras das ações sobre a conta inteira (todos os polos da pessoa).
- [x] Testes em matriz: papel × permissão × mesmo polo / outro polo.

## 4. Contas e autenticação
- [x] Convites (link de uso único, 48 h) e recuperação de palavra-passe por e-mail (SMTP configurável).
- [x] 2FA TOTP, obrigatório para admin, coordenação e secretariado.
- [x] Limite de tentativas de login e expiração de sessões.
- [x] Desativação de contas (nunca apagar). O fim da filiação de estagiária retira o acesso automaticamente.
- [x] Gestão de membros do polo (criar, adicionar uma conta existente ao polo, remover do polo).
- [x] Listagem da coordenação: profissionais do polo com os papéis no polo e, opcionalmente, noutros polos (sem atividade). Exportação em CSV.
- [x] `AuditEvent` em todas estas ações; a migração que cria esta tabela retira UPDATE/DELETE ao utilizador da app, com um teste que o prova (em `deploy/tests/check-production.sh`, porque esse utilizador só existe na configuração de produção).

## 4b. Orientações, filiações e auditoria no portal
- [x] Ecrã de orientações para o secretariado e a coordenação (`core.manage_mentorships`), com `AuditEvent`.
- [x] Alterar o papel ou as datas de uma filiação no portal, com o mesmo teto de papéis e com `AuditEvent`.
- [x] Consulta da auditoria de contas pela coordenação (`core.view_audit`), só sobre os membros do seu polo.
- [x] Na lista de membros, quem tem o 2FA por configurar mostra dois botões: "Enviar link do 2FA" e "Enviar link da palavra-passe".

## 5. Salas, salas exclusivas, bloqueios e regras
- [ ] `Room`, `RoomAssignment` (blocos semanais com início e fim; libertação prevista mas desligada por flag).
- [ ] `Closure`: feriados nacionais e municipais gerados automaticamente por polo; bloqueios manuais; o secretariado pode anular um feriado, com registo.
- [ ] `LocationSettings` com todas as regras da secção 10 do plano, editáveis pelo secretariado e pela coordenação.
- [ ] `ExclusionConstraint` que impede sobreposições entre reservas aprovadas, atribuições e bloqueios na mesma sala.

## 6. Pedidos e fila
- [ ] Formulário de pedido, validado contra as regras do polo.
- [ ] Fila por polo, ordenada por chegada e com ordem indicativa, a mostrar o tempo de espera.
- [ ] Aprovar / recusar (com motivo) / aprovar noutra sala, com a lista das salas livres em todo o intervalo. Os pedidos sobrepostos ficam na fila, mas "Aprovar nesta sala" fica bloqueado.
- [ ] Marcação direta pelo secretariado e pela coordenação.
- [ ] `ChangeRequest`: o requerente pede para mudar a hora ou a sala; a reserva atual mantém-se até haver decisão.
- [ ] Cancelamento: tardio a menos de 24 h; nunca tardio se o staff mudou a hora ou a sala com menos de 48 h de antecedência (os dois valores são configuráveis).
- [ ] Worker: expira os pedidos pendentes à hora de início.

## 7. Recorrências
- [ ] `BookingSeries` com RRULE; geração das ocorrências dentro da antecedência máxima.
- [ ] Aprovação da série com lista de conflitos por ocorrência (outra sala / recusar); aprovação parcial.
- [ ] Editar "só esta" ou "esta e as seguintes".

## 8. Histórico das reservas
- [ ] `BookingEvent` só de acrescentar (permissões da base de dados incluídas), com "em nome de" e o valor antes e depois; a migração que cria esta tabela retira UPDATE/DELETE ao utilizador da app, com um teste que o prova (em `deploy/tests/check-production.sh`, porque esse utilizador só existe na configuração de produção).
- [ ] Cronologia visível ao titular, aos participantes, ao staff do polo e ao admin.

## 9. Vistas
- [ ] Grelha do polo (EventCalendar, vista por sala): detalhes para o staff, "Ocupado" para os outros, filtrado no servidor.
- [ ] "O meu horário": vista por dia e por semana, todos os polos, pendentes marcados à parte.
- [ ] "Encontrar sala livre" (dia, hora e duração), com submissão do pedido a partir do resultado.

## 10. Participantes e horas
- [ ] Adicionar membros do polo ao pedido ou à reserva; entram logo, com notificação, e podem sair.
- [ ] Intervalo por participante dentro da reserva (por omissão, a reserva toda).
- [ ] Contagem de horas: a própria pessoa, o titular, a orientadora e a coordenação; exportação em CSV.

## 11. Relatórios da coordenação
- [ ] Ocupação por sala e por período, horas por profissional e estagiária, tempo médio até à decisão, recusas e cancelamentos tardios. Exportação em CSV.

## 12. Feed iCal (desejável)
- [ ] Link privado e revogável por utilizador, só com as reservas aprovadas.

## 13. Notificações
- [ ] E-mail e notificações no portal: decisão do pedido, alteração pelo staff, adição como participante, bloqueio que afeta uma reserva.

## 14. Produção
- [ ] Endurecimento: CSP, HSTS, cookies seguros, `check --deploy` limpo.
- [ ] Backups encriptados fora do servidor e script de teste de reposição.
- [ ] `docs/runbook.md`: instalação, atualização, reposição de backup, rotação de segredos.
- [ ] Passkeys (WebAuthn) como alternativa opcional ao TOTP.
- [ ] Limite de logins por IP, além do limite por e-mail. O IP vem do `X-Forwarded-For` definido pelo Caddy, que é o único ponto de entrada.
