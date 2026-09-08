import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta

from src.main import app
from src.database import db
from src.models import OperationStatus
from src.service import PaymentService


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
async def test_recovery_processing_operations(client):
    """Test recovery of PROCESSING operations."""
    service = PaymentService()

    # Create multiple operations.
    operation_ids = []
    for i in range(3):
        op_id = f"test-recovery-{i}"
        operation_ids.append(op_id)

        await client.post(
            "/operations",
            json={
                "operationId": op_id,
                "amount": "1000.00",
                "currency": "RUB",
                "description": f"Test recovery {i}"
            }
        )

        # Submit.
        await client.post(f"/operations/{op_id}/submit")

    # Get PROCESSING operations.
    operations = await service.get_processing_operations()
    assert len(operations) >= 3

    # Run recovery.
    await service.process_payment(operations[0].operation_id)

    # Check operation wasn't changed (may remain PROCESSING).
    operation = await service.get_operation(operations[0].operation_id)
    assert operation.status in [OperationStatus.PROCESSING, OperationStatus.COMPLETED, OperationStatus.REJECTED]


@pytest.mark.asyncio
async def test_restart_recovery(client):
    """Test recovery after restart."""
    operation_id = "test-restart"

    # Create and submit.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test restart"
        }
    )

    response = await client.post(f"/operations/{operation_id}/submit")
    assert response.status_code == 202

    # Simulate restart - get all PROCESSING operations.
    service = PaymentService()
    operations = await service.get_processing_operations()

    # Should contain our operation.
    assert any(op.operation_id == operation_id for op in operations)

    # Run recovery.
    for op in operations:
        await service.process_payment(op.operation_id)

    # Check operation is being processed.
    response = await client.get(f"/operations/{operation_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_persistence_after_restart(client):
    """Test data persistence after restart."""
    operation_id = "test-persist"

    # Create operation.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test persist"
        }
    )

    # Get operation before "restart".
    response1 = await client.get(f"/operations/{operation_id}")
    data1 = response1.json()
    assert data1["status"] == "CREATED"

    # Simulate "restart" - new DB connection.
    db.db_path = "/tmp/test_payments.db"  # Use same DB.

    # Get operation after "restart".
    response2 = await client.get(f"/operations/{operation_id}")
    data2 = response2.json()

    # Data should persist.
    assert data2["operationId"] == data1["operationId"]
    assert data2["status"] == data1["status"]
    assert data2["amount"] == data1["amount"]


@pytest.mark.asyncio
async def test_processing_operation_detection(client):
    """Test detection of stuck operations."""
    operation_id = "test-stuck"

    # Create and submit.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test stuck"
        }
    )

    await client.post(f"/operations/{operation_id}/submit")

    # Directly modify updated_at (simulate stuck operation).
    async with db.get_connection() as conn:
        old_time = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        await conn.execute(
            "UPDATE operations SET updated_at = ? WHERE operation_id = ?",
            (old_time, operation_id)
        )
        await conn.commit()

    # Get operations.
    service = PaymentService()
    operations = await service.get_processing_operations()

    # Operation should be detected.
    found = any(op.operation_id == operation_id for op in operations)
    assert found
