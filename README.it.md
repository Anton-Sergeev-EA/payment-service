# payment-service

[Русский](README.md) · [English](README.en.md) · [中文](README.zh.md) · [हिन्दी](README.hi.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · **Italiano**

Prototipo backend per gli stati dei pagamenti. Progetto complementare del portfolio; al momento non si amplia la funzionalità. I test usano un fornitore simulato e non dimostrano integrazione reale, certificazione o esercizio in produzione.

## Installazione e test

CI verifica Python 3.11 e 3.12. Il Dockerfile usa Python 3.14; la costruzione dell’immagine è una verifica separata. SQLite conserva operazioni, eventi e ricevute. Impostare DATABASE_PATH su un percorso scrivibile prima di importare l’applicazione. Ogni test usa un database isolato.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p testdata
DATABASE_PATH="$PWD/testdata/bootstrap.sqlite" .venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

## Dimostrazione Docker

Compose usa un’immagine esterna provider-simulator: occorre accesso al registro e i test unitari non ne garantiscono la disponibilità. Il volume candidate-data conserva SQLite dopo i riavvii; eliminarlo elimina i dati. PROVIDER_URL configura il fornitore. CALLBACK_URL appartiene al simulatore e punta all’endpoint delle ricevute.

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

## API e stati

GET /health indica che il processo risponde, non verifica dipendenze o pagamenti completati. GET /metrics restituisce contatori JSON, non il formato Prometheus. POST /operations crea un’operazione: operationId obbligatorio, amount positivo con al massimo due decimali, currency RUB. POST /operations/{id}/submit salva l’intenzione: primo invio 202, ripetizioni o stati finali 200. GET /operations/{id} legge lo stato; GET /operations/{id}/events legge la cronologia. POST /receipts riceve providerPaymentId, operationId, result (COMPLETED o REJECTED), message e occurredAt.

CREATED → PROCESSING → COMPLETED / REJECTED. La prima ricevuta valida determina lo stato finale; duplicati o ricevute tardive opposte vengono ignorati. Un providerPaymentId associato incompatibile produce 409. Validazione, operazioni mancanti e conflitti hanno percorsi specifici; non ogni corpo malformato garantisce 400.

## Ripristino e limiti

L’intenzione locale viene salvata prima della chiamata esterna. Il client invia Idempotency-Key e X-Correlation-ID usando operationId; alcuni errori temporanei attivano fino a cinque tentativi con attesa esponenziale e jitter. Il recupero iniziale e periodico cerca operazioni PROCESSING. I log JSON includono operation_id, provider_payment_id e attempt quando applicabile. I test API, concorrenza e recupero non provano la tolleranza ai guasti di qualsiasi fornitore reale.

Al massimo un pagamento esterno richiede idempotenza persistente del fornitore; SQLite da solo non la garantisce. Prima dell’uso reale servono autenticazione, verifica dell’autenticità dei callback, revisione di sicurezza e procedure operative. Nessun pagamento reale o certificazione dichiarati. Le traduzioni README non modificano risposte o log dell’applicazione.

## Esempio di operazione

```sh
curl -X POST http://localhost:8080/operations \
  -H 'Content-Type: application/json' \
  -d '{"operationId":"demo-1","amount":"100.00","currency":"RUB","description":"Demo"}'
curl -X POST http://localhost:8080/operations/demo-1/submit
curl http://localhost:8080/operations/demo-1
curl http://localhost:8080/operations/demo-1/events
```

[Per esempi dettagliati e struttura consultare il README russo.](README.md)
