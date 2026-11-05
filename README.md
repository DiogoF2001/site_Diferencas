# Site e serviços Diferenças

Novo site do CDI Diferenças e portal (área reservada) para os profissionais do centro. O primeiro serviço do portal é a gestão de salas.

- Plano aprovado: [`docs/plano.md`](docs/plano.md) (versão visual em [`docs/plano.html`](docs/plano.html))
- Tarefas por ordem: [`docs/roadmap.md`](docs/roadmap.md)
- Regras para o Claude Code: [`CLAUDE.md`](CLAUDE.md), incluindo todos os comandos do dia a dia

## Arranque local

Só precisas do Docker com o Compose. O ambiente de desenvolvimento não usa `.env`, e os valores em `deploy/docker-compose.dev.yml` são fictícios.

```bash
docker compose -f deploy/docker-compose.dev.yml up --build
```

Depois abre <http://127.0.0.1:8000/healthz/>, que deve responder `{"status": "ok"}`. O código em `portal/` é recarregado automaticamente na `app` e no `worker`.

Se o teu UID não for 1000, define-o antes de arrancar:

```bash
export HOST_UID=$(id -u) HOST_GID=$(id -g)
```

Para correr os testes:

```bash
docker compose -f deploy/docker-compose.dev.yml run --rm app pytest
```

## Instalação em produção

1. Copia `deploy/.env.example` para `deploy/.env` e substitui todos os valores. O ficheiro indica como gerar a chave do Django e as chaves do `age`. Guarda a chave privada do `age` fora do servidor: sem ela, os backups não se conseguem ler.
2. Cria a pasta dos backups, com o dono indicado em `BACKUP_UID` e `BACKUP_GID`: `mkdir deploy/backups`.
3. Arranca os serviços e corre as migrações:

```bash
docker compose -f deploy/docker-compose.yml up -d --build --wait
```

```bash
docker compose -f deploy/docker-compose.yml --profile ops run --rm migrate
```

O domínio tem de apontar para o servidor, com as portas 80 e 443 abertas, para o Caddy obter o certificado.

Nesta fase, os backups ficam só em `deploy/backups/`. A cópia para fora do servidor e o teste de reposição chegam na tarefa 14 do roadmap.
