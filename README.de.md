# payment-service

[Русский](README.md) · [English](README.en.md) · [中文](README.zh.md) · [हिन्दी](README.hi.md) · [Español](README.es.md) · [Français](README.fr.md) · **Deutsch** · [Italiano](README.it.md)

Backend-Prototyp für Zahlungszustände. Ergänzendes Portfolio-Projekt; derzeit keine funktionale Erweiterung. Tests verwenden einen simulierten Anbieter und belegen weder echte Zahlungsintegration noch Zertifizierung oder Produktionsbetrieb.

## Installation und Tests

CI testet Python 3.11 und 3.12. Das Dockerfile nutzt Python 3.14; der Image-Build ist eine separate Prüfung. SQLite speichert Vorgänge, Ereignisse und Belege. DATABASE_PATH vor dem Anwendungsimport auf einen beschreibbaren Pfad setzen. Jeder Test verwendet eine isolierte Datenbank.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p testdata
DATABASE_PATH="$PWD/testdata/bootstrap.sqlite" .venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

## Docker-Demonstration

Compose nutzt ein externes provider-simulator-Image. Registry-Zugriff ist erforderlich; Unit-Tests garantieren keine Verfügbarkeit. Das Volume candidate-data erhält SQLite nach Neustarts; seine Löschung entfernt die Daten. PROVIDER_URL legt den Anbieter fest. CALLBACK_URL gehört zum Simulator und verweist auf den Beleg-Endpunkt.

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

## API und Zustände

GET /health prüft die Antwort des Prozesses, nicht Abhängigkeiten oder abgeschlossene Zahlungen. GET /metrics liefert JSON-Zähler, kein Prometheus-Format. POST /operations erstellt einen Vorgang: operationId erforderlich, amount positiv mit höchstens zwei Nachkommastellen, currency RUB. POST /operations/{id}/submit speichert die Absicht: erster Aufruf 202, Wiederholungen oder Endzustände 200. GET /operations/{id} liest den Zustand; GET /operations/{id}/events liest den Verlauf. POST /receipts empfängt providerPaymentId, operationId, result (COMPLETED oder REJECTED), message und occurredAt.

CREATED → PROCESSING → COMPLETED / REJECTED. Der erste gültige Beleg bestimmt den Endzustand; Duplikate oder verspätete Gegenbelege werden ignoriert. Ein widersprüchlicher verknüpfter providerPaymentId führt zu 409. Validierung, fehlende Vorgänge und Konflikte werden gesondert behandelt; nicht jeder fehlerhafte Request garantiert 400.

## Wiederherstellung und Grenzen

Die lokale Absicht wird vor dem Anbieteraufruf gespeichert. Der Client sendet Idempotency-Key und X-Correlation-ID mit operationId; bei ausgewählten vorübergehenden Fehlern erfolgen bis zu fünf Versuche mit exponentieller Wartezeit und Jitter. Wiederherstellung beim Start und periodisch prüft PROCESSING-Vorgänge. JSON-Logs enthalten gegebenenfalls operation_id, provider_payment_id und attempt. API-, Nebenläufigkeits- und Wiederherstellungstests belegen keine Ausfallsicherheit beliebiger realer Anbieter.

Höchstens eine externe Zahlung setzt dauerhafte Idempotenz beim Anbieter voraus; SQLite allein garantiert dies nicht. Vor realem Einsatz sind Authentifizierung, Callback-Echtheitsprüfung, Sicherheitsprüfung und Betriebsverfahren nötig. Keine echten Zahlungen oder Zahlungssystem-Zertifizierung behauptet. README-Übersetzungen ändern keine Anwendungsantworten oder Logs.

## Beispielvorgang

```sh
curl -X POST http://localhost:8080/operations \
  -H 'Content-Type: application/json' \
  -d '{"operationId":"demo-1","amount":"100.00","currency":"RUB","description":"Demo"}'
curl -X POST http://localhost:8080/operations/demo-1/submit
curl http://localhost:8080/operations/demo-1
curl http://localhost:8080/operations/demo-1/events
```

[Ausführliche Beispiele und Struktur stehen im russischen README.](README.md)
