# payment-service

[Русский](README.md) · **English** · [中文](README.zh.md) · [हिन्दी](README.hi.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Italiano](README.it.md)

Payment-state backend prototype. An additional portfolio project; functionality is not being expanded. Tests use simulated provider behavior and do not establish real payment integration, certification or production operation.

## Setup and tests

CI tests Python 3.11 and 3.12. The Dockerfile uses Python 3.14; this is a separate image-build check. SQLite stores operations, events and receipts. Set DATABASE_PATH to a writable location before importing the application. Each test uses an isolated database.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p testdata
DATABASE_PATH="$PWD/testdata/bootstrap.sqlite" .venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

## Docker demonstration

Compose uses an external provider-simulator image. Pulling it requires registry access; availability is not guaranteed by the unit tests. The candidate-data volume persists SQLite across restarts; removing the volume removes that data. PROVIDER_URL configures the service provider address. CALLBACK_URL belongs to the simulator and points to the service receipt endpoint.

```sh
git clone https://github.com/Anton-Sergeev-EA/payment-service.git
cd payment-service
docker compose up --build
```

```sh
curl http://localhost:8080/health
curl http://localhost:8080/metrics
docker compose logs -f payment-service
```

## API and states

GET /health returns a process response, not a dependency-readiness or payment-completion check. GET /metrics returns JSON counters, not Prometheus exposition. POST /operations creates an operation; operationId is required, amount must be positive with at most two decimal places, currency is RUB. POST /operations/{id}/submit records submission intent: first submission returns 202, repeats or final states return 200. GET /operations/{id} reads state; GET /operations/{id}/events reads transition history. POST /receipts accepts callbacks with providerPaymentId, operationId, result (COMPLETED or REJECTED), message and occurredAt.

CREATED → PROCESSING → COMPLETED / REJECTED. The first valid receipt determines the final state; duplicate or opposite late receipts are ignored, while a conflicting linked providerPaymentId produces 409. Validation, missing operations and conflicts have dedicated API paths; not every malformed payload is guaranteed to return 400.

## Recovery and limitations

The local submission intent is saved before the provider call. The provider client sends Idempotency-Key and X-Correlation-ID using operationId, with up to five attempts and exponential backoff plus jitter for selected transient errors. Recovery scans PROCESSING operations on startup and periodically. JSON logs include operation_id, provider_payment_id and attempt where applicable. Tests cover API, concurrency and recovery; they do not prove fault tolerance for arbitrary real providers.

At most one external payment requires durable provider-side idempotency; SQLite alone cannot guarantee it. Authentication, callback authenticity verification, security review and operational procedures are required before real use. No real payments or payment-system certification are claimed. Application responses and log text are not localized by these README files.

## Example operation

```sh
curl -X POST http://localhost:8080/operations \
  -H 'Content-Type: application/json' \
  -d '{"operationId":"demo-1","amount":"100.00","currency":"RUB","description":"Demo"}'
curl -X POST http://localhost:8080/operations/demo-1/submit
curl http://localhost:8080/operations/demo-1
curl http://localhost:8080/operations/demo-1/events
```

[For detailed examples and project structure, see the Russian README.](README.md)
