# payment-service

[Русский](README.md) · [English](README.en.md) · **中文** · [हिन्दी](README.hi.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Italiano](README.it.md)

支付状态后端原型。作为补充作品集项目，目前不扩展功能。测试使用模拟支付提供方，不能证明真实支付集成、认证或生产运行。

## 安装与测试

CI 测试 Python 3.11 和 3.12。Dockerfile 使用 Python 3.14，镜像构建是单独检查。SQLite 保存操作、事件和回执。导入应用前将 DATABASE_PATH 设置为可写路径；每个测试使用独立数据库。

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p testdata
DATABASE_PATH="$PWD/testdata/bootstrap.sqlite" .venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

## Docker 演示

Compose 使用外部 provider-simulator 镜像，拉取需要访问镜像仓库；单元测试不保证镜像可用。candidate-data 卷在重启后保留 SQLite；删除卷会删除数据。PROVIDER_URL 配置提供方地址；CALLBACK_URL 是模拟器配置，指向服务回执接口。

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

## API 与状态

GET /health 仅说明进程能响应，不检查依赖就绪或支付完成。GET /metrics 返回 JSON 计数器，不是 Prometheus 格式。POST /operations 创建操作：operationId 必填，amount 为正数且最多两位小数，currency 为 RUB。POST /operations/{id}/submit 保存提交意图：首次返回 202，重复提交或终态返回 200。GET /operations/{id} 查询状态；GET /operations/{id}/events 查询历史。POST /receipts 接收 providerPaymentId、operationId、result（COMPLETED 或 REJECTED）、message 和 occurredAt。

CREATED → PROCESSING → COMPLETED / REJECTED。首个有效回执决定终态；重复或相反的迟到回执被忽略；已关联的 providerPaymentId 冲突返回 409。API 对校验、找不到操作和冲突分别处理，但并非所有错误请求都保证返回 400。

## 恢复与限制

调用提供方前保存本地提交意图。客户端以 operationId 发送 Idempotency-Key 和 X-Correlation-ID；指定的暂时错误最多尝试五次，使用指数退避与随机抖动。启动和周期恢复扫描 PROCESSING 操作。JSON 日志在适用时包含 operation_id、provider_payment_id 和 attempt。测试覆盖 API、并发与恢复，不能证明任意真实提供方的容错能力。

外部支付至多一次依赖提供方持久幂等性，SQLite 本身无法保证。真实使用前需实现认证、回调真实性验证、安全审查和运维流程。不声称处理过真实支付或取得支付系统认证。README 翻译不改变应用响应或日志语言。

## 操作示例

```sh
curl -X POST http://localhost:8080/operations \
  -H 'Content-Type: application/json' \
  -d '{"operationId":"demo-1","amount":"100.00","currency":"RUB","description":"Demo"}'
curl -X POST http://localhost:8080/operations/demo-1/submit
curl http://localhost:8080/operations/demo-1
curl http://localhost:8080/operations/demo-1/events
```

[详细示例与项目结构见俄文 README。](README.md)
