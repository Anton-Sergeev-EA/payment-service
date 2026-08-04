# Payment-service.
Сервис для обработки платежей с гарантией идемпотентности и отказоустойчивости.
A payment processing service that guarantees idempotency and fault tolerance.

## Структура:
payment-service/
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pytest.ini
├── README.md
├── src/
│ ├── init.py
│ ├── main.py
│ ├── models.py
│ ├── database.py
│ ├── service.py
│ ├── provider.py
│ ├── scheduler.py
│ ├── metrics.py
│ └── logging_config.py
└── tests/
├── init.py
├── test_api.py
├── test_concurrency.py
└── test_recovery.py

## Быстрый старт.
Клонирование и запуск:
git clone https://github.com/YOUR_USERNAME/payment-service.git
cd payment-service
docker compose up --build

## Проверка работоспособности:
curl http://localhost:8080/health
Ожидаемый ответ:
json
{"status":"healthy"}

## Переменные окружения.
Переменная	    Значение по умолчанию	                 Описание
PROVIDER_URL	http://provider-simulator:8081	         Адрес внешнего провайдера
CALLBACK_URL	http://candidate-service:8080/receipts	 Адрес для callback-квитанций

## API сервис.
GET /health.
Проверка готовности сервиса.
Ответ: 200 OK
json
{"status":"healthy"}

GET /metrics.
Получение метрик сервиса.
Ответ: 200 OK
json
{
  "operations_total": 5,
  "operations_created": 5,
  "operations_processing": 2,
  "operations_completed": 3,
  "operations_rejected": 0,
  "retry_attempts": 1,
  "provider_errors": 0,
  "receipts_processed": 3,
  "receipts_ignored": 0,
  "recoveries": 1,
  "operations_processing_current": 0,
  "stuck_operations": 0
}

POST /operations.
Создание новой платёжной операции.
Тело запроса:
json
{
  "operationId": "operation-123",
  "amount": "1000.00",
  "currency": "RUB",
  "description": "Оплата заказа"
}

## Параметры:
- operationId: обязательный, строка.
- amount: положительное число с не более чем двумя знаками после запятой.
- currency: поддерживается только RUB.
Ответ: 201 Created

json
{
  "operationId": "operation-123",
  "amount": "1000.00",
  "currency": "RUB",
  "description": "Оплата заказа",
  "status": "CREATED",
  "providerPaymentId": null
}

## Ошибки:
- 400: неверный формат запроса.
- 409: операция с таким operationId уже существует.
## Пример запроса:
curl -X POST http://localhost:8080/operations \
  -H "Content-Type: application/json" \
  -d '{
    "operationId": "operation-123",
    "amount": "1000.00",
    "currency": "RUB",
    "description": "Оплата заказа"
  }'

# POST /operations/{id}/submit
Отправка платежа провайдеру.
Поведение:
- первый вызов для операции в статусе CREATED: сохраняет намерение, переводит в PROCESSING, возвращает 202.
- повторные вызовы: возвращают текущее состояние с кодом 200.
- для операций в финальных статусах: возвращают текущее состояние с кодом 200.
Ответ: 202 Accepted (первый вызов) или 200 OK (повторный).
json
{
  "operationId": "operation-123",
  "amount": "1000.00",
  "currency": "RUB",
  "description": "Оплата заказа",
  "status": "PROCESSING",
  "providerPaymentId": null
}

## Ошибки:
- 404: операция не найдена.
Пример запроса:
curl -X POST http://localhost:8080/operations/operation-123/submit

# POST /receipts.
Приём callback-квитанции от провайдера.
Тело запроса:
{
  "providerPaymentId": "aa5b7856-e9f2-4fd5-955b-38b1f28d9c57",
  "operationId": "operation-123",
  "result": "COMPLETED",
  "message": "Payment completed",
  "occurredAt": "2026-07-15T12:00:00Z"
}

## Правила обработки:
- result принимает значения COMPLETED или REJECTED.
- первая валидная квитанция определяет финальный статус.
- повторная квитанция с тем же providerPaymentId игнорируется.
- поздняя квитанция с противоположным результатом игнорируется.
- несовпадающий providerPaymentId после установления связи возвращает 409.
Ответ: 204 No Content
Пример запроса:
curl -X POST http://localhost:8080/receipts \
  -H "Content-Type: application/json" \
  -d '{
    "providerPaymentId": "aa5b7856-e9f2-4fd5-955b-38b1f28d9c57",
    "operationId": "operation-123",
    "result": "COMPLETED",
    "message": "Payment completed",
    "occurredAt": "2026-07-15T12:00:00Z"
  }'

## GET /operations/{id}.
Получение текущего состояния операции.
Ответ: 200 OK
{
  "operationId": "operation-123",
  "amount": "1000.00",
  "currency": "RUB",
  "description": "Оплата заказа",
  "status": "COMPLETED",
  "providerPaymentId": "aa5b7856-e9f2-4fd5-955b-38b1f28d9c57"
}
Ошибки:
- 404: операция не найдена.
Пример запроса:
curl http://localhost:8080/operations/operation-123

## GET /operations/{id}/events.
Получение истории переходов операции.
Ответ: 200 OK
[
  {
    "eventId": 1,
    "type": "CREATED",
    "fromStatus": null,
    "toStatus": "CREATED",
    "message": "Operation created",
    "occurredAt": "2026-07-15T12:00:00Z"
  },
  {
    "eventId": 2,
    "type": "SUBMIT",
    "fromStatus": "CREATED",
    "toStatus": "PROCESSING",
    "message": "Operation submitted for processing",
    "occurredAt": "2026-07-15T12:00:01Z"
  }
]

## Ошибки:
- 404: операция не найдена
Пример запроса:
curl http://localhost:8080/operations/operation-123/events

## Состояния операции.
Состояние	Описание
CREATED	    Операция создана, отправка не запрошена
PROCESSING	Намерение отправки сохранено, ожидается результат
COMPLETED	Провайдер подтвердил успех callback-квитанцией
REJECTED	Провайдер подтвердил отказ callback-квитанцией
Главный инвариант: при любых повторах, конкурентных запросах, потерянных ответах и перезапусках одной операции соответствует не более одного платежа провайдера, а финальный статус определяется только callback-квитанцией.

# Сквозные сценарии проверки.
Сценарий 1: Успешный платёж.
## Создание операции.
curl -X POST http://localhost:8080/operations \
  -H "Content-Type: application/json" \
  -d '{
    "operationId": "success-test-1",
    "amount": "100.00",
    "currency": "RUB",
    "description": "Test payment"
  }'
## Отправка платежа.
curl -X POST http://localhost:8080/operations/success-test-1/submit
## Проверка статуса (ожидается COMPLETED).
curl http://localhost:8080/operations/success-test-1
## Проверка истории.
curl http://localhost:8080/operations/success-test-1/events
## Проверка метрик.
curl http://localhost:8080/metrics

Сценарий 2: Отказ платежа.
# Создание операции с суммой, вызывающей отказ
curl -X POST http://localhost:8080/operations \
  -H "Content-Type: application/json" \
  -d '{
    "operationId": "reject-test-1",
    "amount": "99999.00",
    "currency": "RUB",
    "description": "Test rejection"
  }'
# Отправка платежа
curl -X POST http://localhost:8080/operations/reject-test-1/submit
# Проверка статуса (ожидается REJECTED)
curl http://localhost:8080/operations/reject-test-1

Сценарий 3: Конкурентные запросы.
# Создание операции.
curl -X POST http://localhost:8080/operations \
  -H "Content-Type: application/json" \
  -d '{
    "operationId": "concurrent-test-1",
    "amount": "100.00",
    "currency": "RUB",
    "description": "Concurrent test"
  }'
# Пять одновременных submit.
for i in {1..5}; do
  curl -X POST http://localhost:8080/operations/concurrent-test-1/submit &
done
wait
# Проверка: только один запрос создал намерение.
curl http://localhost:8080/operations/concurrent-test-1

Сценарий 4: Callback до ответа провайдера.
# Создание операции.
curl -X POST http://localhost:8080/operations \
  -H "Content-Type: application/json" \
  -d '{
    "operationId": "callback-first-test-1",
    "amount": "100.00",
    "currency": "RUB",
    "description": "Callback first test"
  }'
# Отправка квитанции до submit.
curl -X POST http://localhost:8080/receipts \
  -H "Content-Type: application/json" \
  -d '{
    "providerPaymentId": "cb-first-1",
    "operationId": "callback-first-test-1",
    "result": "COMPLETED",
    "message": "Payment completed",
    "occurredAt": "2026-07-15T12:00:00Z"
  }'
# Отправка платежа (должен вернуть COMPLETED).
curl -X POST http://localhost:8080/operations/callback-first-test-1/submit
# Проверка статуса.
curl http://localhost:8080/operations/callback-first-test-1

Сценарий 5: Восстановление после перезапуска.
# Создание и отправка операции.
curl -X POST http://localhost:8080/operations \
  -H "Content-Type: application/json" \
  -d '{
    "operationId": "recovery-test-1",
    "amount": "100.00",
    "currency": "RUB",
    "description": "Recovery test"
  }'

curl -X POST http://localhost:8080/operations/recovery-test-1/submit
# Перезапуск сервиса.
docker compose restart candidate-service
# Проверка восстановления операции.
curl http://localhost:8080/operations/recovery-test-1
# Проверка логов восстановления.
docker compose logs candidate-service | grep "recovery"

Сценарий 6: Проверка сохранности данных.
# Создание операции.
curl -X POST http://localhost:8080/operations \
  -H "Content-Type: application/json" \
  -d '{
    "operationId": "persist-test-1",
    "amount": "100.00",
    "currency": "RUB",
    "description": "Persistence test"
  }'
# Остановка контейнеров.
docker compose down
# Запуск заново.
docker compose up -d
# Проверка сохранности данных.
curl http://localhost:8080/operations/persist-test-1

Сценарий 7: Проверка retry с attempt.
# Создание операции.
curl -X POST http://localhost:8080/operations \
  -H "Content-Type: application/json" \
  -d '{
    "operationId": "retry-test-1",
    "amount": "1000.00",
    "currency": "RUB",
    "description": "Retry test"
  }'
# Отправка.
curl -X POST http://localhost:8080/operations/retry-test-1/submit
# Просмотр логов с attempt.
docker compose logs candidate-service | grep "retry-test-1" | grep "attempt"

# Тестирование.
## Запуск тестов.
#### Установка зависимостей.
pip install -r requirements.txt
#### Запуск всех тестов
pytest tests/ -v
# Запуск с покрытием.
pytest tests/ --cov=src --cov-report=html
# Запуск конкретного теста.
pytest tests/test_api.py::test_create_operation_success -v

# Структура тестов.
Файл	              Описание
test_api.py	          Тестирование всех API эндпоинтов
test_concurrency.py	  Тестирование конкурентных сценариев
test_recovery.py	  Тестирование восстановления и сохранности

# Логирование.
## Логи формируются в формате JSON:
{
  "timestamp": "2026-07-15T12:00:00Z",
  "level": "INFO",
  "logger": "src.service",
  "message": "Processing payment operation-123",
  "operation_id": "operation-123",
  "provider_payment_id": "aa5b7856-e9f2-4fd5-955b-38b1f28d9c57",
  "attempt": 1
}

# Просмотр логов:
## Все логи.
docker compose logs -f candidate-service
## Фильтр по operation_id.
docker compose logs candidate-service | grep "operation-123"
## Только ошибки.
docker compose logs candidate-service | grep ERROR
## Логи с attempt (retry).
docker compose logs candidate-service | grep "attempt"

# База данных.
Используется SQLite с постоянным томом. Данные сохраняются при перезапуске контейнеров.
Таблица	               Описание.
operations	           Основная информация об операциях.
events	               История переходов состояний.
receipts	           Все полученные квитанции.
processed_receipts	   Обработанные квитанции для проверки конфликтов.

# Отказоустойчивость.
1. Идемпотентность: повторные запросы с тем же operationId не создают новый платёж.
2. Атомарность: сохранение состояния до внешнего вызова провайдера.
3. Восстановление: автоматическое продолжение обработки после перезапуска.
4. Конкурентность: блокировки на уровне БД предотвращают двойную обработку.
5. Retry: экспоненциальная задержка с jitter (0-0.5с) при сетевых ошибках, до 5 попыток.
6. Структурированные логи: JSON формат с полями operation_id, provider_payment_id, attempt.
7. Метрики: эндпоинт /metrics для мониторинга состояния сервиса.
8. Graceful Shutdown: корректное завершение фоновых задач при остановке.

# Коды ответов API.
Код	   Описание.
200	   Успешный запрос.
201	   Операция создана.
202	   Запрос на отправку принят.
204	   Квитанция обработана.
400	   Неверный запрос.
404	   Операция не найдена.
409	   Конфликт.
500	   Внутренняя ошибка сервера.

# Зависимости.
Библиотека	       Версия	Назначение.
FastAPI	           0.115.6	Веб-фреймворк.
Uvicorn	           0.34.0	ASGI сервер.
aiosqlite	       0.20.0	Асинхронный драйвер SQLite.
httpx	           0.28.1	HTTP клиент.
tenacity	       9.0.0	Retry с backoff и jitter.
pytest	           8.3.4	Тестирование.
pytest-asyncio	   0.24.0	Асинхронные тесты.

# Требования к системе.
- Docker 20.10+.
- Docker Compose 2.0+.
- Python 3.14 (для локальной разработки).
- 512 MB RAM.
- 1 GB свободного дискового пространства.
