# payment-service

[Русский](README.md) · [English](README.en.md) · [中文](README.zh.md) · [हिन्दी](README.hi.md) · **Español** · [Français](README.fr.md) · [Deutsch](README.de.md) · [Italiano](README.it.md)

Prototipo backend de estados de pago. Proyecto complementario del portafolio; no se amplía su funcionalidad. Las pruebas usan un proveedor simulado y no demuestran integración real, certificación ni operación en producción.

## Instalación y pruebas

CI prueba Python 3.11 y 3.12. El Dockerfile usa Python 3.14; construir la imagen es una comprobación independiente. SQLite guarda operaciones, eventos y recibos. Configure DATABASE_PATH en una ubicación escribible antes de importar la aplicación. Cada prueba usa una base aislada.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p testdata
DATABASE_PATH="$PWD/testdata/bootstrap.sqlite" .venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

## Demostración Docker

Compose usa una imagen externa provider-simulator que requiere acceso al registro; las pruebas unitarias no garantizan su disponibilidad. El volumen candidate-data conserva SQLite tras reinicios; eliminarlo elimina los datos. PROVIDER_URL configura el proveedor. CALLBACK_URL pertenece al simulador y apunta al endpoint de recibos.

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

## API y estados

GET /health responde desde el proceso; no comprueba dependencias ni pagos completados. GET /metrics devuelve contadores JSON, no formato Prometheus. POST /operations crea una operación: operationId obligatorio, amount positivo con hasta dos decimales, currency RUB. POST /operations/{id}/submit guarda la intención: primer envío 202, repeticiones o estados finales 200. GET /operations/{id} consulta el estado; GET /operations/{id}/events consulta el historial. POST /receipts recibe providerPaymentId, operationId, result (COMPLETED o REJECTED), message y occurredAt.

CREATED → PROCESSING → COMPLETED / REJECTED. El primer recibo válido determina el estado final; duplicados o recibos tardíos opuestos se ignoran. Un providerPaymentId asociado incompatible produce 409. Hay rutas específicas para validación, operaciones inexistentes y conflictos; no todo cuerpo inválido garantiza un 400.

## Recuperación y límites

La intención local se guarda antes de llamar al proveedor. El cliente envía Idempotency-Key y X-Correlation-ID con operationId; realiza hasta cinco intentos con espera exponencial y jitter ante determinados fallos transitorios. La recuperación inicial y periódica busca operaciones PROCESSING. Los registros JSON incluyen operation_id, provider_payment_id y attempt cuando corresponde. Las pruebas de API, concurrencia y recuperación no prueban tolerancia a fallos de cualquier proveedor real.

Como máximo un pago externo requiere idempotencia persistente del proveedor; SQLite por sí solo no lo garantiza. Antes de uso real se requieren autenticación, verificación de callbacks, revisión de seguridad y procedimientos operativos. No se afirman pagos reales ni certificación. Estas traducciones no cambian respuestas ni registros de la aplicación.

## Ejemplo de operación

```sh
curl -X POST http://localhost:8080/operations \
  -H 'Content-Type: application/json' \
  -d '{"operationId":"demo-1","amount":"100.00","currency":"RUB","description":"Demo"}'
curl -X POST http://localhost:8080/operations/demo-1/submit
curl http://localhost:8080/operations/demo-1
curl http://localhost:8080/operations/demo-1/events
```

[Para ejemplos detallados y estructura, consulte el README ruso.](README.md)
