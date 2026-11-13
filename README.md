# VagaPulse

**Acompanhamento de candidaturas com uma API REST, fluxo de etapas e indicadores.**

O VagaPulse organiza processos seletivos em um só lugar. Registre vagas,
acompanhe cada etapa, filtre candidaturas e exporte os dados para CSV.

## Por que este projeto

O projeto reúne padrões comuns em aplicações de negócio — API REST, persistência
relacional, validação, consulta e análise — em um caso prático, com testes
automatizados e execução em Docker.

## Funcionalidades

- Cadastro e consulta de candidaturas.
- Busca por empresa ou cargo, filtro por etapa e paginação.
- Transições de etapa validadas (`saved` → `applied` → `interview` → `offer`);
  rejeições podem ser registradas a partir de qualquer etapa ativa.
- Indicadores agregados por etapa e exportação CSV.
- Documentação interativa em `/docs` e verificação de saúde em `/health`.
- SQLite persistente por padrão, sem necessidade de configurar um servidor de banco.

## Tecnologias

Python · FastAPI · SQLAlchemy · SQLite · Pytest · Docker Compose

## Executar localmente

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m uvicorn app:app --reload
```

Abra `http://localhost:8000/docs` para explorar e testar os endpoints.

## Executar com Docker

```bash
docker compose up --build
```

Os dados ficam em um volume Docker. A API fica disponível em
`http://localhost:8000`.

## Testes

```bash
pytest -q
```

Os testes cobrem cadastro e busca, validação de transições, métricas e exportação.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/applications` | Cadastra uma candidatura |
| `GET` | `/applications` | Lista, filtra e pagina |
| `GET` | `/applications/{id}` | Consulta uma candidatura |
| `PATCH` | `/applications/{id}/stage` | Atualiza a etapa do processo |
| `GET` | `/analytics` | Resume candidaturas por etapa |
| `GET` | `/applications/export.csv` | Exporta candidaturas |
| `GET` | `/health` | Verifica a API e o banco |

Exemplo de cadastro:

```json
{
  "company": "Acme",
  "role": "Software Engineer Intern",
  "source": "Careers page",
  "applied_on": "2026-10-01"
}
```

Os dados de exemplo são fictícios. Este projeto não coleta nem envia informações
para serviços externos.
