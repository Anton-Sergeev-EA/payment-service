# payment-service

[Русский](README.md) · [English](README.en.md) · [中文](README.zh.md) · **हिन्दी** · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Italiano](README.it.md)

भुगतान स्थिति का backend प्रोटोटाइप। यह अतिरिक्त पोर्टफोलियो परियोजना है; अभी सुविधाएँ नहीं बढ़ाई जा रही हैं। परीक्षण simulated provider का उपयोग करते हैं; वास्तविक भुगतान integration, certification या production संचालन सिद्ध नहीं होता।

## स्थापना और परीक्षण

CI में Python 3.11 और 3.12 जाँचे जाते हैं। Dockerfile Python 3.14 उपयोग करता है; image build अलग जाँच है। SQLite में operations, events और receipts रहते हैं। application import से पहले DATABASE_PATH लिखने योग्य स्थान पर सेट करें। हर परीक्षण का अलग डेटाबेस है।

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p testdata
DATABASE_PATH="$PWD/testdata/bootstrap.sqlite" .venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

## Docker प्रदर्शन

Compose बाहरी provider-simulator image उपयोग करता है; registry access आवश्यक है और unit tests उसकी उपलब्धता की गारंटी नहीं देते। candidate-data volume restart के बाद SQLite रखता है; volume हटाने पर डेटा हटता है। PROVIDER_URL provider का पता है। CALLBACK_URL simulator का configuration है और service के receipt endpoint की ओर जाता है।

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

## API और स्थितियाँ

GET /health केवल process response है, dependencies की readiness या भुगतान completion नहीं। GET /metrics JSON counters लौटाता है, Prometheus format नहीं। POST /operations operation बनाता है: operationId आवश्यक, amount धनात्मक और अधिकतम दो decimal places, currency RUB। POST /operations/{id}/submit intent सहेजता है: पहली बार 202, दोहराव या final state पर 200। GET /operations/{id} स्थिति, GET /operations/{id}/events history पढ़ता है। POST /receipts में providerPaymentId, operationId, result (COMPLETED या REJECTED), message और occurredAt आते हैं।

CREATED → PROCESSING → COMPLETED / REJECTED। पहली valid receipt final state तय करती है; duplicate या देर से विपरीत receipt ignore होती है। जुड़े providerPaymentId का conflict 409 देता है। Validation, missing operation और conflict के अलग API paths हैं; हर malformed payload पर 400 की गारंटी नहीं।

## पुनर्प्राप्ति और सीमाएँ

Provider call से पहले local intent सहेजा जाता है। Client operationId से Idempotency-Key और X-Correlation-ID भेजता है; चुनी गई transient errors पर exponential backoff और jitter के साथ अधिकतम पाँच attempts हैं। Startup और periodic recovery PROCESSING operations खोजते हैं। JSON logs में जहाँ लागू हो operation_id, provider_payment_id और attempt हैं। API, concurrency और recovery tests arbitrary real provider की fault tolerance सिद्ध नहीं करते।

एक external payment की सीमा के लिए provider की durable idempotency चाहिए; केवल SQLite इसे सुनिश्चित नहीं करता। वास्तविक उपयोग से पहले authentication, callback authenticity verification, security review और operational procedures आवश्यक हैं। वास्तविक payments या payment-system certification का दावा नहीं है। README translations application responses या logs का अनुवाद नहीं करतीं।

## Operation का उदाहरण

```sh
curl -X POST http://localhost:8080/operations \
  -H 'Content-Type: application/json' \
  -d '{"operationId":"demo-1","amount":"100.00","currency":"RUB","description":"Demo"}'
curl -X POST http://localhost:8080/operations/demo-1/submit
curl http://localhost:8080/operations/demo-1
curl http://localhost:8080/operations/demo-1/events
```

[विस्तृत उदाहरण और संरचना Russian README में हैं।](README.md)
