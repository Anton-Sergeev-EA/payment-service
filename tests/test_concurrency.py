import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from datetime import datetime

from src.main import app
from src.database import db
from src.models import OperationStatus


@pytest.fixture
async def client():
    """Create test client for API testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
async def clean_db():
    """Clean database before each test."""
    db.db_path = "/tmp/test_payments.db"
    db._init_db()

    async with db.get_connection() as conn:
        await conn.execute("DELETE FROM operations")
        await conn.execute("DELETE FROM events")
        await conn.execute("DELETE FROM receipts")
        await conn.execute("DELETE FROM processed_receipts")
        await conn.commit()

    yield

    import os
    if os.path.exists("/tmp/test_payments.db"):
        os.remove("/tmp/test_payments.db")


@pytest.mark.asyncio
async def test_concurrent_submit(client):
    """Test concurrent submit requests for the same operation."""
    operation_id = "test-concurrent"

    # Create operation.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test concurrent"
        }
    )

    # Launch 10 concurrent submit requests.
    async def submit_request():
        return await client.post(f"/operations/{operation_id}/submit")

    tasks = [submit_request() for _ in range(10)]
    responses = await asyncio.gather(*tasks)

    # Check: only one should return 202 (created intent).
    status_codes = [r.status_code for r in responses]
    assert status_codes.count(202) == 1
    assert status_codes.count(200) == 9  # Others return current state.

    # Check: all responses should have the same status (PROCESSING).
    statuses = [r.json()["status"] for r in responses if r.status_code in [200, 202]]
    assert all(s == "PROCESSING" for s in statuses)

    # Check in DB: only one SUBMIT event.
    response = await client.get(f"/operations/{operation_id}/events")
    events = response.json()
    submit_events = [e for e in events if e["type"] == "SUBMIT"]
    assert len(submit_events) == 1


@pytest.mark.asyncio
async def test_concurrent_create(client):
    """Test concurrent create requests for the same operation."""
    operation_id = "test-concurrent-create"

    # Launch 10 concurrent create requests.
    async def create_request():
        return await client.post(
            "/operations",
            json={
                "operationId": operation_id,
                "amount": "1000.00",
                "currency": "RUB",
                "description": "Test concurrent create"
            }
        )

    tasks = [create_request() for _ in range(10)]
    responses = await asyncio.gather(*tasks)

    # Check: only one should return 201.
    status_codes = [r.status_code for r in responses]
    assert status_codes.count(201) == 1
    assert status_codes.count(409) == 9

    # Check: operation created only once.
    response = await client.get(f"/operations/{operation_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_submit_and_receipt(client):
    """Test concurrent submit and receipt requests."""
    operation_id = "test-concurrent-mixed"
    provider_payment_id = "provider-mixed"

    # Create operation.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test concurrent mixed"
        }
    )

    # Launch submit and receipt concurrently.
    async def submit_request():
        return await client.post(f"/operations/{operation_id}/submit")

    async def receipt_request():
        await asyncio.sleep(0.01)  # Small delay.
        return await client.post(
            "/receipts",
            json={
                "providerPaymentId": provider_payment_id,
                "operationId": operation_id,
                "result": "COMPLETED",
                "message": "Payment completed",
                "occurredAt": datetime.utcnow().isoformat() + "Z"
            }
        )

    results = await asyncio.gather(
        submit_request(),
        receipt_request()
    )

    # Check: at least one request should be successful.
    assert results[0].status_code in [200, 202] or results[1].status_code == 204

    # Check final status.
    response = await client.get(f"/operations/{operation_id}")
    data = response.json()
    assert data["status"] in ["PROCESSING", "COMPLETED"]

    if data["status"] == "COMPLETED":
        assert data["providerPaymentId"] == provider_payment_id


@pytest.mark.asyncio
async def test_submit_after_receipt_completed(client):
    """Test submit after COMPLETED receipt."""
    operation_id = "test-submit-after-completed"
    provider_payment_id = "provider-after"

    # Create.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test after completed"
        }
    )

    # COMPLETED receipt.
    await client.post(
        "/receipts",
        json={
            "providerPaymentId": provider_payment_id,
            "operationId": operation_id,
            "result": "COMPLETED",
            "message": "Payment completed",
            "occurredAt": datetime.utcnow().isoformat() + "Z"
        }
    )

    # Late submit.
    response = await client.post(f"/operations/{operation_id}/submit")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_duplicate_submit_after_completed(client):
    """Test duplicate submit after COMPLETED."""
    operation_id = "test-duplicate-after"
    provider_payment_id = "provider-after2"

    # Create.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test duplicate after"
        }
    )

    # First submit.
    response1 = await client.post(f"/operations/{operation_id}/submit")
    assert response1.status_code == 202

    # COMPLETED receipt.
    await client.post(
        "/receipts",
        json={
            "providerPaymentId": provider_payment_id,
            "operationId": operation_id,
            "result": "COMPLETED",
            "message": "Payment completed",
            "occurredAt": datetime.utcnow().isoformat() + "Z"
        }
    )

    # Second submit.
    response2 = await client.post(f"/operations/{operation_id}/submit")
    assert response2.status_code == 200
    data = response2.json()
    assert data["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_race_condition_submit(client):
    """Test race condition during submit."""
    operation_id = "test-race"

    # Create.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test race"
        }
    )

    # Launch 100 concurrent submit requests.
    async def submit_request():
        return await client.post(f"/operations/{operation_id}/submit")

    tasks = [submit_request() for _ in range(100)]
    responses = await asyncio.gather(*tasks)

    # Check: only one created intent.
    created_count = sum(1 for r in responses if r.status_code == 202)
    assert created_count == 1

    # All others should return 200.
    ok_count = sum(1 for r in responses if r.status_code == 200)
    assert ok_count == 99

    # Check: all responses contain the same operation_id.
    operation_ids = [r.json()["operationId"] for r in responses if r.status_code in [200, 202]]
    assert all(op_id == operation_id for op_id in operation_ids)

    # Check in DB: only one record in PROCESSING.
    response = await client.get(f"/operations/{operation_id}")
    data = response.json()
    assert data["status"] == "PROCESSING"


@pytest.mark.asyncio
async def test_high_load_scenario(client):
    """Test high load scenario with multiple operations."""
    # Create 10 operations.
    operation_ids = []
    for i in range(10):
        op_id = f"test-load-{i}"
        operation_ids.append(op_id)

        await client.post(
            "/operations",
            json={
                "operationId": op_id,
                "amount": str(1000 + i * 100),
                "currency": "RUB",
                "description": f"Test load {i}"
            }
        )

    # Submit all operations.
    async def submit_operation(op_id):
        return await client.post(f"/operations/{op_id}/submit")

    tasks = [submit_operation(op_id) for op_id in operation_ids]
    responses = await asyncio.gather(*tasks)

    # Check: all operations submitted successfully.
    successful = sum(1 for r in responses if r.status_code in [200, 202])
    assert successful == 10

    # Check: all operations transitioned to PROCESSING.
    for op_id in operation_ids:
        response = await client.get(f"/operations/{op_id}")
        data = response.json()
        assert data["status"] in ["PROCESSING", "COMPLETED", "REJECTED"]
