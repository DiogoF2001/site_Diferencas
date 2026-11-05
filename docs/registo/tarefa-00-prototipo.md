# Tarefa 0 — Protótipo clicável

> Escrito em retrospetiva, a partir do git log e das descrições dos PR [#2](https://github.com/DiogoF2001/site_Diferencas/pull/2) e [#3](https://github.com/DiogoF2001/site_Diferencas/pull/3). O que estas fontes não dizem está assinalado como "não registado".

## Objetivo

Ter um protótipo em HTML estático, com dados fictícios, para validar com o secretariado e com 2–3 profissionais as vistas de Profissional, Secretariado, Coordenação e Admin.

## Decisões técnicas

| Escolha | Alternativas | Porquê |
|---|---|---|
| HTML, CSS e JS estáticos, sem passo de build; estado só em memória, com "Repor dados" | Não registado | Abre com um duplo clique no `index.html` |
| `@event-calendar/build@5.18.1` (MIT) por CDN, com versão fixa | Não registado | É a biblioteca prevista no plano, e o objetivo era validá-la já. Se a CDN falhar, a grelha mostra uma tabela com a mesma informação e um aviso |
| `@fontsource/atkinson-hyperlegible@5.3.0` (OFL) por CDN | Não registado | A fonte pedida, sem depender do Google |
| Topo carrega `prototipo/assets/logo.png`, com o texto "Diferenças" enquanto não existir | Não foi desenhado nenhum logótipo | O logótipo real chegou depois, no PR #3 |

## Decisões de negócio

Escolhas do protótipo que o PR #2 deixou **por validar**. O PR não indica que tenham sido confirmadas.

- **Horas do titular:** conta a reserva toda nas suas horas. O plano só fala em "intervalos de participação".
- **Bloqueio manual sobre reservas aprovadas:** lista as afetadas e notifica os titulares (simulado), mas não as cancela. O plano não diz o que lhes acontece.
- **Pedido para uma sala já ocupada:** o formulário não o aceita e sugere "Encontrar sala livre". Pedidos sobrepostos só entre si continuam a ser possíveis.
- **Pedidos pendentes dos outros:** não aparecem na grelha do profissional, porque ainda não ocupam a sala. Isto foi depois confirmado no plano, no PR #4 (ver a [tarefa 2](tarefa-02-nucleo.md)).

## Ficheiros criados ou alterados

- **PR #2** (`81d3361`): `prototipo/` (`index.html`, `app.js`, `data.js`, `store.js`, `styles.css`, `views-comum.js`, `views-gestao.js`, `views-staff.js`, `assets/.gitkeep`) e `docs/roadmap.md`.
- **PR #3** (`516651e`): `prototipo/assets/logo.png`.

## Como funciona

Uma página única sem servidor. Os seletores **Perfil** e **Polo** no topo escolhem a pessoa fictícia. `data.js` tem os dados de partida, `store.js` tem as regras e o estado em memória (incluindo uma imitação da verificação central de permissões), e os ficheiros `views-*` desenham os ecrãs. Cada ação mostra um aviso com a data, a hora e o utilizador.

Fora de âmbito: séries recorrentes, pedidos de alteração, sair de uma reserva como participante, feed iCal e notificações. Convites e links de recuperação são simulados.

## Comandos de verificação e resultados

Verificação manual; testes, lint e `check --deploy` não se aplicam, porque a tarefa não toca em `portal/`. O PR #2 não correu CI; o PR #3 passou nos quatro trabalhos.

- **Browser integrado, por `http://127.0.0.1`:** todos os ecrãs dos quatro perfis abrem sem erros, e os fluxos foram percorridos, incluindo as permissões negativas e o arrastar com o rato.
- **`file://`:** o Firefox em modo headless abriu o ficheiro e desenhou a grelha, com o calendário e a fonte. Os fluxos não foram repetidos por `file://`.
- **Telemóvel (375 px):** sem deslocamento horizontal da página. O logótipo fica com 169 × 36 px (180 × 38 px em computador, a 1100 px).
- **Acessibilidade:** auditoria de contraste por script sem falhas (os blocos às riscas ficam de fora), foco visível com Tab, blocos abertos com Enter e vista em tabela.
- **Não testado:** arrastar em ecrã táctil, leitores de ecrã reais e outros browsers. Os campos de data e hora seguem a língua do browser.

## Problemas encontrados e como foram resolvidos

- O browser integrado não carrega ficheiros relativos por `file://`. Os fluxos foram testados por `http://127.0.0.1` e o `file://` foi verificado em separado com o Firefox.
- O logótipo real ficou de fora do PR #2 e entrou no PR #3, sem mudar código.

## Pendentes para tarefas seguintes

- Validar com o secretariado e os profissionais; o que resultou dessa validação não está registado.
- Confirmar as escolhas da secção "Decisões de negócio" antes das tarefas 6, 5 e 10, que as implementam.
