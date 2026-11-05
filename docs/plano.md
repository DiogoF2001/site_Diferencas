# Plano — Área reservada e serviço de gestão de salas

## 1. Resumo das decisões

#### Portal separado

Fica em `portal.diferencas.net`, com acesso por "Área reservada" no site público. Tem a mesma identidade visual, mas é uma aplicação independente.

#### Monólito modular

Contas, papéis e permissões formam um núcleo comum. Cada serviço (Salas agora, outros no futuro) é um módulo que se liga a esse núcleo.

#### Django + PostgreSQL

Começa no Django 5.2 LTS e migra para a 6.2 LTS em 2027. A interface usa HTMX e o EventCalendar (MIT).

#### Tudo em Docker

Usa Docker Compose, por isso pode correr num VPS, na cloud ou no centro. O sítio do alojamento decide-se mais tarde.

#### Papéis por polo

Cada pessoa tem uma só conta (a conta técnica do Admin é a exceção). Os papéis vêm de filiações (pessoa + polo + papel), e uma pessoa pode ter papéis diferentes em polos diferentes.

#### Sem serviços pagos

Não depende de Google nem de Microsoft. A única dependência externa é um servidor SMTP para os e-mails.

## 2. Arquitetura

- **Site público e portal separados.** Uma falha no site público não chega às contas nem às reservas, e cada um é atualizado ao seu ritmo.
- **Núcleo comum:** utilizadores, polos, filiações, papéis, permissões, orientações, notificações e auditoria. Todos os serviços futuros usam este núcleo e não criam contas próprias.
- **Módulos de serviço:** o primeiro é o de *Salas*. Cada módulo declara as suas permissões com um prefixo (`salas.*`, mais tarde por exemplo `documentos.*`), e essas permissões são atribuídas aos papéis que já existem.
- **Regra de ouro:** o código verifica *permissões num polo*, nunca nomes de grupos. Por exemplo, pergunta "tem `salas.aprovar` no polo P?" e não "é secretariado?".

## 3. Stack tecnológica

| Camada            | Escolha                             | Porquê                                                                                                                                                                            |
|-------------------|-------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Backend           | Django 5.2 LTS → 6.2 LTS (Python)   | Traz incluídos a autenticação, as sessões, a proteção CSRF, as migrações, o backoffice, os formulários e o e-mail. Cada versão LTS tem cerca de 3 anos de correções de segurança. |
| Base de dados     | PostgreSQL                          | Tem restrições de exclusão sobre intervalos de tempo, que garantem na própria base de dados que não há reservas duplicadas.                                                       |
| Interface         | Páginas geradas no servidor + HTMX  | Dá interatividade sem uma aplicação de frontend à parte, por isso há menos dependências e menos superfície de ataque.                                                             |
| Calendário        | EventCalendar (vkurko, licença MIT) | Tem vistas por sala ("resource") gratuitas. No FullCalendar estas vistas são pagas (Premium).                                                                                     |
| Tarefas agendadas | Serviço *worker* separado           | Trata de expirar pedidos, desativar estagiárias no fim do estágio, enviar e-mails e gerar as ocorrências das séries.                                                              |

### Porque não Next.js

- **Não traz o essencial.** Autenticação, convites, 2FA, backoffice, migrações e tarefas agendadas exigiriam 6 a 8 bibliotecas de terceiros, cada uma com o seu ciclo de versões.
- **Muda depressa.** Sai uma versão principal por ano e cada uma é suportada cerca de dois anos. Nas versões em Maintenance LTS, as atualizações podem trazer alterações incompatíveis.
- **Falhas recentes graves.** A CVE-2025-29927 (CVSS 9.1) permitia contornar a autorização feita no middleware. A CVE-2025-55182 (CVSS 10.0, dezembro de 2025) permitia executar código remotamente sem autenticação e foi explorada ativamente.
- **Mais dependências.** Assenta no ecossistema npm, que tem centenas de dependências indiretas e sofreu ataques à cadeia de fornecimento em 2025.
- **Mais difícil de passar a outra pessoa.** Um projeto Django segue convenções que qualquer programador Django reconhece. Um projeto Next.js depende das bibliotecas que cada equipa escolheu.

## 4. Modelo de acesso por polo

**Filiação = pessoa + polo + papel**, com datas de início e fim. A mesma pessoa pode ser Profissional num polo e Coordenação noutro, ou ter dois papéis no mesmo polo; nesse caso as permissões somam-se. O **Admin** é o único papel global.

### Papéis

- **Profissional**, com dois subpapéis: **Residente** e **Estagiária**. Têm as mesmas permissões no módulo de Salas; a separação existe para serviços futuros.
- **Secretariado:** gere a operação diária do polo.
- **Coordenação / Direção técnica:** tem acesso total ao polo e também aos relatórios.
- **Admin** (global, criado na instalação): tem tudo, incluindo a área técnica. É uma conta técnica, sem filiações, sem horário e sem horas próprias. Quem também trabalhe como profissional usa outra conta, com outro e-mail.

### Permissões (dentro do polo)

| Permissão | Profissional (Residente / Estagiária) | Secretariado | Coordenação | Admin |
|---|---|---|---|---|
| Ver ocupação (livre/ocupado) | ✓ | ✓ | ✓ | ✓ |
| Ver detalhes e histórico de todas as reservas | só as suas* | ✓ | ✓ | ✓ |
| Submeter pedidos de reserva | ✓ | marca diretamente | marca diretamente | em nome de outra pessoa |
| Adicionar participantes às suas reservas | ✓ | ✓ | ✓ | em nome de outra pessoa |
| Aprovar e recusar pedidos; alterar qualquer reserva | – | ✓ | ✓ | ✓ |
| Gerir salas, salas exclusivas, bloqueios e regras do polo | – | ✓ | ✓ | ✓ |
| Anular bloqueios automáticos (feriados) | – | ✓ | ✓ | ✓ |
| Criar contas e atribuir papéis no polo | – | até Secretariado | até Coordenação | tudo |
| Listagem de profissionais do polo (e papéis noutros polos) | – | – | ✓ | ✓ |
| Relatórios de ocupação e horas | as suas e as das orientandas | – | ✓ | ✓ |
| Área técnica | – | – | – | ✓ |

\* Inclui as reservas em que a pessoa é titular ou participante.

A área técnica inclui os logs técnicos, o estado do sistema, a configuração do SMTP e dos segredos, a criação de polos, as funcionalidades que se ligam e desligam e um modo "ver como utilizador" (só de leitura e registado).

**Polo inativo:** enquanto um polo estiver inativo, as filiações nesse polo não dão nenhuma permissão. O Admin mantém o acesso, para o poder gerir e reativar. As filiações não mudam, por isso reativar o polo repõe tudo.

### Regras de gestão de contas

- **Acesso a um polo:** uma pessoa só tem acesso a um polo depois de o secretariado ou a coordenação *desse* polo lhe criar uma filiação lá.
- **Até que papel se pode atribuir:** cada pessoa só atribui papéis até ao seu próprio nível no polo. O secretariado pode criar uma conta de secretariado do início ao fim, sem precisar do admin.
- **E-mail já registado:** cria-se apenas a nova filiação. Quem gere o polo B não vê as reservas nem a atividade dessa pessoa noutros polos.
- **Palavras-passe:** ninguém define a palavra-passe de outra pessoa. Só se pode enviar um link de recuperação para o e-mail dela.
- **Ações sobre a conta inteira:** desativar a conta toda ou repor o 2FA exige um papel igual ou superior ao dessa pessoa em *todos* os polos onde ela está. Caso contrário, só se pode removê-la do próprio polo.
- **Listagem da coordenação:** a coordenação tem uma lista dos profissionais do seu polo, com os papéis de cada um nesse polo. Opcionalmente, mostra também os papéis e polos de cada pessoa noutros polos, mas nunca a atividade lá. A lista pode ser exportada em CSV.

### Orientação

É uma relação entre uma **orientadora** (profissional) e uma **orientanda** (estagiária), definida por polo pelo secretariado ou pela coordenação, com datas de início e fim. A orientadora vê o horário e as horas da orientanda nesse polo. A relação fica disponível para serviços futuros, como avaliações e relatórios de estágio.

## 5. Contas e autenticação

- **Sem registo público.** As contas são criadas por convite: quem gere o polo cria a conta com o e-mail, e a pessoa recebe um link para definir a palavra-passe. O link só funciona uma vez e expira em 48 h.
- **Admin "hardcoded":** a conta existe sempre, mas é criada na instalação a partir de segredos do servidor. Nunca fica no código nem no repositório. Tem 2FA obrigatório e é usada só para configuração e emergências.
- **2FA:** obrigatório para Admin, Coordenação e Secretariado, e recomendado para Profissionais. Funciona com qualquer app TOTP gratuita (Aegis, 2FAS…) ou com passkeys.
- **Saída de pessoas:** as contas são desativadas e nunca apagadas, para manter o histórico. As filiações de estagiárias têm data de fim, e o acesso termina sozinho: a data de fim é o último dia com acesso, na hora de Lisboa.
- **E-mail:** usa qualquer servidor SMTP, de preferência o do alojamento de e-mail que o centro já tem. Não se monta servidor de e-mail próprio, porque os e-mails tenderiam a ir parar ao spam. Há também notificações dentro do portal.

## 6. Módulo de salas

- **Sala:** nome, polo e estado (ativa ou inativa). A sala não tem um tipo "exclusiva" ou "partilhada", e não se regista equipamento.
- **Salas exclusivas:** são *atribuições* com horário, por exemplo "Sala 3 é da Dra. X de segunda a quarta". Uma sala exclusiva a tempo inteiro é só uma atribuição que cobre todo o horário de funcionamento. Assim, uma sala pode ser exclusiva uns dias e partilhada nos outros. O titular não precisa de fazer pedidos dentro do seu bloco, e os outros veem a sala como "Ocupada".
- **Libertação de períodos:** fica prevista no modelo de dados, como uma exceção à atribuição, mas *desligada*. O admin pode ativá-la por polo.
- **Reservas duplicadas impossíveis:** uma restrição do PostgreSQL impede reservas aprovadas sobrepostas na mesma sala. Isto inclui as atribuições exclusivas e os bloqueios, e vale mesmo que duas pessoas aprovem ao mesmo tempo.
- **"Livre/ocupado" filtrado no servidor:** das reservas de outras pessoas, o servidor só envia início, fim e "ocupado". Esconder os detalhes só na interface não chegaria.
- **O que conta como "Ocupado":** só as reservas aprovadas, as atribuições exclusivas e os bloqueios. Os pedidos pendentes de outras pessoas não aparecem a quem é Profissional.
- **Sem dados de utentes:** as notas das reservas são só para notas logísticas. Isto mantém o serviço fora do regime de dados de saúde.

## 7. Fluxo de pedidos

Pendente→ Aprovado/ Recusado (com motivo)/ Cancelado/ Expirado

- **Fila por polo, por ordem de chegada, com ordem indicativa.** Cada pedido mostra há quanto tempo está à espera, mas o secretariado pode decidir por qualquer ordem. Todos os pedidos são aprovados explicitamente.
- **Pedidos sobrepostos:** quando um pedido é aprovado, os outros que se sobrepõem na mesma sala continuam na fila, mas "Aprovar nesta sala" fica bloqueado. O sistema mostra a reserva com que colidem e propõe duas saídas:
  - **Aprovar noutra sala**, com a lista das salas livres durante todo esse intervalo;
  - **Recusar**.
- **Aprovar noutra sala:** a reserva fica logo feita e o requerente é notificado. A partir daí, o requerente pode pedir para alterar a hora ou a sala, ou cancelar.
- **Pedidos de alteração:** entram na fila. A reserva atual mantém-se até haver decisão.
- **Marcação direta:** o secretariado e a coordenação podem marcar diretamente, sem passar pela fila. Mesmo assim, não conseguem criar conflitos.
- **Pedidos recorrentes:** a série é aprovada de uma vez. As ocorrências em conflito aparecem em lista, e cada uma pode ir para outra sala ou ser recusada. A aprovação parcial é permitida.
- **Cancelamento:** a sala fica livre, e os pedidos em fila para esse horário voltam a poder ser aprovados. Isto acontece sozinho, porque os conflitos são calculados no momento.
- **Expiração:** um pedido sem decisão expira automaticamente à hora de início.

**Cancelamento tardio.** Um cancelamento conta como tardio quando é feito a menos de 24 h do início. **Exceção:** se o secretariado ou a coordenação mudaram a hora ou a sala com menos de 48 h de antecedência, o cancelamento pelo requerente nunca conta como tardio. Os dois valores são configuráveis por polo.

## 8. Participantes e horas

- **Quem pode adicionar:** o titular (médico ou estagiária) pode adicionar membros do mesmo polo, logo no pedido ou depois de a reserva estar aprovada. Os participantes **entram logo**, recebem uma notificação e podem **sair** a qualquer momento.
- **Divisão do tempo:** cada participante tem um intervalo dentro da reserva, que por omissão é a reserva toda. Por exemplo, numa reserva das 9h às 12h, a estagiária A fica das 9h às 10h e a B das 10h às 12h. Os intervalos podem sobrepor-se, como numa consulta com dois médicos.
- **O que os participantes podem fazer:** veem os detalhes e o histórico da reserva, que também aparece no horário e no feed iCal deles. Não a podem editar.
- **Contagem de horas:** soma os intervalos de participação em reservas aprovadas que já passaram. Quem vê:
  - cada pessoa vê as suas horas;
  - o titular vê as horas dos participantes nas reservas dele;
  - a orientadora vê as horas das orientandas;
  - a coordenação vê as de todo o polo.

  Tudo pode ser exportado em CSV.

## 9. Vistas e relatórios

#### Grelha do polo Secretariado · Coordenação

Salas nas linhas, horas nas colunas, com nomes visíveis. Permite arrastar para mover reservas, mostra os pedidos pendentes sobrepostos e permite criar séries.

#### Grelha do polo Profissionais

A mesma grelha, com os blocos dos outros a cinzento como "Ocupado" e as reservas da própria pessoa em detalhe.

#### O meu horário Todos

Vista por dia e por semana, sem divisão por sala, com todas as reservas e pedidos da pessoa em todos os polos, cada um com a etiqueta do polo.

#### Encontrar sala livre

Pesquisa por dia, hora e duração no polo escolhido, com submissão do pedido logo a partir do resultado.

#### Fila de pedidos Secretariado · Coordenação

Pedidos ordenados por chegada, com o tempo de espera, os conflitos e as salas alternativas.

#### Feed iCal desejável

Um link privado e revogável, só com as reservas aprovadas. Funciona em qualquer app de calendário.

#### Relatórios Coordenação

Taxa de ocupação por sala e por período, horas por profissional e estagiária, tempo médio até à decisão, recusas e cancelamentos tardios.

#### Listagem de profissionais Coordenação

Os papéis de cada profissional no polo e, opcionalmente, noutros polos. Exportável em CSV.

## 10. Regras configuráveis por polo

Estes são os parâmetros de funcionamento das reservas. **Todos os valores são editáveis por polo** pelo secretariado e pela coordenação, numa página de configuração do portal, sem mexer no código. O admin define os valores por omissão que cada polo novo recebe.

| Regra                          | Valor por omissão                                                                                                                           |
|--------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| Horário de funcionamento       | seg–sex, 08:00–20:00 estimativa                                                                                                             |
| Blocos de tempo                | 15 min estimativa                                                                                                                           |
| Duração por pedido             | mínimo 30 min, máximo 4 h estimativa                                                                                                        |
| Antecedência mínima do pedido  | 24 h. Para menos do que isso, o secretariado marca diretamente estimativa                                                                   |
| Antecedência máxima            | 8 semanas para pedidos pontuais; recorrentes até ao fim do ano letivo estimativa                                                            |
| Pedido sem decisão             | expira à hora de início                                                                                                                     |
| Editar um pedido pendente      | mudar a hora ou a sala faz perder o lugar na fila; participantes e notas não                                                                |
| Editar uma reserva aprovada    | mudar a hora ou a sala cria um pedido de alteração; a reserva atual mantém-se até haver decisão                                             |
| Cancelamento tardio            | menos de 24 h antes do início                                                                                                               |
| Exceção ao tardio              | alteração feita pelo secretariado ou pela coordenação com menos de 48 h de antecedência                                                     |
| Feriados                       | nacionais e municipais bloqueados automaticamente; o secretariado pode anular o bloqueio de um dia concreto, e a anulação fica no histórico |
| Bloqueios manuais              | criados e removidos pelo secretariado ou pela coordenação; o sistema lista as reservas afetadas e notifica os titulares                     |
| Libertação de salas exclusivas | desligada (o admin pode ativá-la por polo)                                                                                                  |

## 11. Históricos e auditoria

Os registos são só de acrescentar. A aplicação não os edita nem apaga, e o utilizador da base de dados com que ela trabalha não tem permissão para alterar nem apagar nessas tabelas.

| Registo                             | Conteúdo                                                                                                                                                                                                       | Quem vê                                                                       |
|-------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| Histórico de cada pedido ou reserva | Cada evento (criação, edição, aprovação, recusa, mudança de sala ou hora, participantes, divisão de horas, cancelamento), com data e hora, utilizador, "em nome de" quando aplicável, e o valor antes e depois | O titular e os participantes; o secretariado e a coordenação do polo; o admin |
| Auditoria de contas                 | Convites, filiações, papéis, orientações, desativações, reposições de 2FA e logins falhados                                                                                                                    | A coordenação (membros do seu polo) e o admin                                 |
| Logs técnicos                       | Erros, desempenho e tarefas agendadas                                                                                                                                                                          | Só o admin                                                                    |

As datas e horas são guardadas em UTC e mostradas na hora de Lisboa.

## 12. Modelo de dados (entidades principais)

| Entidade                        | Campos principais                                                                      |
|---------------------------------|----------------------------------------------------------------------------------------|
| Utilizador                      | nome, e-mail (único), estado, 2FA                                                      |
| Polo                            | nome, morada, estado                                                                   |
| Filiação                        | utilizador, polo, papel, subpapel (Residente/Estagiária), início, fim                  |
| Orientação                      | orientadora, orientanda, polo, início, fim                                             |
| Sala                            | polo, nome, estado                                                                     |
| Atribuição exclusiva            | sala, profissional, dias e horas, início, fim; exceções (para a libertação, desligada) |
| Reserva                         | sala, titular, início, fim, estado, série, notas logísticas, criada por                |
| Série recorrente                | regra de repetição (formato iCalendar), exceções; gera as ocorrências                  |
| Pedido de alteração             | reserva, nova sala e/ou hora, estado                                                   |
| Participação                    | reserva, utilizador, intervalo dentro da reserva                                       |
| Bloqueio                        | polo, sala (ou todas), intervalo, origem (feriado ou manual), anulado por              |
| Regras do polo                  | todos os parâmetros da secção 10                                                       |
| Evento de histórico / auditoria | entidade, ação, utilizador, "em nome de", antes e depois, data e hora                  |

## 13. Alojamento

### Docker Compose

- **proxy:** Caddy, com HTTPS automático;
- **app:** Django com Gunicorn;
- **worker:** tarefas agendadas;
- **db:** PostgreSQL;
- **backup:** cópia diária encriptada da base de dados, guardada fora do servidor, com teste de reposição todos os meses.

Há também um serviço pontual, **migrate**, que só corre as migrações e depois termina. Usa o utilizador da base de dados dono das tabelas, que não é superutilizador; a app e o worker usam outro, sem posse de tabelas, para que as regras de "só acrescentar" da secção 11 não possam ser contornadas a partir da aplicação. O backup usa um utilizador só de leitura, e o superutilizador do PostgreSQL serve só para a inicialização.

Os segredos (incluindo os do admin) ficam num ficheiro de ambiente fora do repositório.

### Opções (decisão adiada)

| Opção                                               | Custo indicativo                                                  | Notas                                                                                                                   |
|-----------------------------------------------------|-------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| VPS na UE (por exemplo Hetzner, Alemanha/Finlândia) | ≈ €5–7/mês + backups                                              | Mais simples e mais barato. A atualização do sistema operativo fica do nosso lado.                                      |
| Azure (programa Microsoft for Nonprofits)           | €0 dentro do crédito anual de 2.000 USD, se a APPT21 for elegível | Infraestrutura gerida. A doação tem de ser renovada todos os anos, e o crédito não usado não passa para o ano seguinte. |
| Servidor no centro                                  | ~€200–300 de uma vez (mini-PC + UPS)                              | Usa um Cloudflare Tunnel para não abrir portas. Fica dependente da luz e da internet do centro.                         |

Contas, domínio e faturação devem ficar em nome da associação, para que o serviço não dependa de uma só pessoa.

## 14. RGPD e segurança

- Os dados tratados são dados de trabalhadores (nome, e-mail, horários). Não se guardam dados de utentes.
- O alojamento fica na UE, com um contrato de tratamento de dados com o fornecedor e uma entrada no registo de atividades de tratamento da associação.
- O prazo de conservação dos históricos e das contas desativadas deve ser definido com a direção.
- As permissões são verificadas no servidor em todos os pedidos. A interface nunca é a única barreira.
- Há limite de tentativas de login, sessões com expiração e cabeçalhos de segurança (CSP, HSTS).
- As atualizações de segurança do Django e das imagens Docker são aplicadas todos os meses.

## 15. Fases

1.  **Levantamento:** inventário das salas e dos polos, lista de profissionais e papéis, salas exclusivas atuais e validação das regras com o secretariado.
2.  **Protótipo clicável** com dados fictícios e as vistas de Profissional, Secretariado, Coordenação e Admin, para validar com o secretariado e com 2–3 profissionais.
3.  **MVP:** núcleo de contas, filiações e permissões; salas e atribuições exclusivas; pedidos, fila e aprovação; recorrências; bloqueios; histórico; "O meu horário".
4.  **Extras:** participantes e divisão de horas, relatórios da coordenação, feed iCal, notificações por e-mail e listagens em CSV.
5.  **Próximos serviços** sobre o mesmo núcleo, aproveitando os subpapéis e as orientações.

## 16. A confirmar com o centro

- Os valores marcados como estimativa na secção 10.
- A lista de polos que entram na primeira fase, e as salas de cada um.
- Que servidor SMTP usar (o alojamento de e-mail atual do centro).
- A elegibilidade da APPT21 para o Microsoft for Nonprofits, se se quiser considerar a Azure.
- Quem fica responsável pela manutenção depois da entrega.

## Fontes

- [Django — versões suportadas e calendário LTS](https://www.djangoproject.com/download/)
- [Next.js — Support Policy](https://nextjs.org/support-policy)
- [CVE-2025-29927 — Authorization Bypass in Next.js Middleware](https://db.gcve.eu/vuln/cve-2025-29927)
- [CVE-2025-55182 — RCE em React Server Components / Next.js](https://www.runzero.com/blog/vercel-next-js)
- [Microsoft — Renovação da doação Azure para associações](https://learn.microsoft.com/en-us/industry/nonprofit/microsoft-for-nonprofits/renew-azure-grant)
- [Comparação de preços de cloud (agosto de 2026)](https://kimmo.suominen.com/stuff/cpc-2026-08.txt)
