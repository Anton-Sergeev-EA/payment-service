import pytest
import asyncio
from datetime import datetime
from httpx import AsyncClient, ASGITransport
from decimal import Decimal

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
    # Use test database.
    db.db_path = "/tmp/test_payments.db"
    db._init_db()

    async with db.get_connection() as conn:
        await conn.execute("DELETE FROM operations")
        await conn.execute("DELETE FROM events")
        await conn.execute("DELETE FROM receipts")
        await conn.execute("DELETE FROM processed_receipts")
        await conn.commit()

    yield

    # Clean up after test.
    import os
    if os.path.exists("/tmp/test_payments.db"):
        os.remove("/tmp/test_payments.db")


@pytest.mark.asyncio
async def test_health_check(client):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_create_operation_success(client):
    """Test successful operation creation."""
    operation_id = "test-1"
    response = await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test payment"
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["operationId"] == operation_id
    assert data["amount"] == "1000.00"
    assert data["currency"] == "RUB"
    assert data["status"] == "CREATED"
    assert data["providerPaymentId"] is None


@pytest.mark.asyncio
async def test_create_operation_duplicate(client):
    """Test duplicate operation creation (should return 409)."""
    operation_id = "test-duplicate"

    # First creation.
    response1 = await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test payment"
        }
    )
    assert response1.status_code == 201

    # Second creation (should return 409).
    response2 = await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test payment"
        }
    )
    assert response2.status_code == 409


@pytest.mark.asyncio
async def test_create_operation_invalid_amount(client):
    """Test operation creation with invalid amount."""
    # Negative amount.
    response = await client.post(
        "/operations",
        json={
            "operationId": "test-invalid",
            "amount": "-100.00",
            "currency": "RUB",
            "description": "Test"
        }
    )
    assert response.status_code == 400

    # Amount with more than 2 decimal places.
    response = await client.post(
        "/operations",
        json={
            "operationId": "test-invalid-2",
            "amount": "100.001",
            "currency": "RUB",
            "description": "Test"
        }
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_submit_operation_success(client):
    """Test successful payment submission."""
    operation_id = "test-submit"

    # Create operation.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test payment"
        }
    )

    # Submit.
    response = await client.post(f"/operations/{operation_id}/submit")
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "PROCESSING"


@pytest.mark.asyncio
async def test_submit_operation_not_found(client):
    """Test submission of non-existent operation."""
    response = await client.post("/operations/non-existent/submit")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_operation(client):
    """Test getting operation by ID."""
    operation_id = "test-get"

    # Create.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test payment"
        }
    )

    # Get.
    response = await client.get(f"/operations/{operation_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["operationId"] == operation_id
    assert data["status"] == "CREATED"


@pytest.mark.asyncio
async def test_get_operation_not_found(client):
    """Test getting non-existent operation."""
    response = await client.get("/operations/non-existent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_events(client):
    """Test getting operation events history."""
    operation_id = "test-events"

    # Create.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test payment"
        }
    )

    # Submit.
    await client.post(f"/operations/{operation_id}/submit")

    # Get events.
    response = await client.get(f"/operations/{operation_id}/events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) >= 2  # CREATED + SUBMIT.

    # Check event structure.
    first_event = events[0]
    assert "eventId" in first_event
    assert "type" in first_event
    assert "fromStatus" in first_event
    assert "toStatus" in first_event
    assert "message" in first_event
    assert "occurredAt" in first_event


@pytest.mark.asyncio
async def test_process_receipt_completed(client):
    """Test processing COMPLETED receipt."""
    operation_id = "test-receipt-completed"
    provider_payment_id = "provider-123"

    # Create operation.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test payment"
        }
    )

    # Submit.
    await client.post(f"/operations/{operation_id}/submit")

    # Send receipt.
    response = await client.post(
        "/receipts",
        json={
            "providerPaymentId": provider_payment_id,
            "operationId": operation_id,
            "result": "COMPLETED",
            "message": "Payment completed",
            "occurredAt": datetime.utcnow().isoformat() + "Z"
        }
    )
    assert response.status_code == 204

    # Check status.
    response = await client.get(f"/operations/{operation_id}")
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["providerPaymentId"] == provider_payment_id


@pytest.mark.asyncio
async def test_process_receipt_rejected(client):
    """Test processing REJECTED receipt."""
    operation_id = "test-receipt-rejected"
    provider_payment_id = "provider-456"

    # Create operation.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "99999.00",  # Amount that will cause rejection.
            "currency": "RUB",
            "description": "Test payment"
        }
    )

    # Submit.
    await client.post(f"/operations/{operation_id}/submit")

    # Send receipt.
    response = await client.post(
        "/receipts",
        json={
            "providerPaymentId": provider_payment_id,
            "operationId": operation_id,
            "result": "REJECTED",
            "message": "Payment rejected",
            "occurredAt": datetime.utcnow().isoformat() + "Z"
        }
    )
    assert response.status_code == 204

    # Check status.
    response = await client.get(f"/operations/{operation_id}")
    data = response.json()
    assert data["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_duplicate_receipt(client):
    """Test duplicate receipt processing."""
    operation_id = "test-duplicate-receipt"
    provider_payment_id = "provider-duplicate"

    # Create and submit.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test payment"
        }
    )
    await client.post(f"/operations/{operation_id}/submit")

    # First receipt.
    response1 = await client.post(
        "/receipts",
        json={
            "providerPaymentId": provider_payment_id,
            "operationId": operation_id,
            "result": "COMPLETED",
            "message": "Payment completed",
            "occurredAt": datetime.utcnow().isoformat() + "Z"
        }
    )
    assert response1.status_code == 204

    # Second receipt (duplicate).
    response2 = await client.post(
        "/receipts",
        json={
            "providerPaymentId": provider_payment_id,
            "operationId": operation_id,
            "result": "COMPLETED",
            "message": "Payment completed",
            "occurredAt": datetime.utcnow().isoformat() + "Z"
        }
    )
    assert response2.status_code == 204


@pytest.mark.asyncio
async def test_conflicting_receipt(client):
    """Test conflicting receipt processing."""
    operation_id = "test-conflict-receipt"

    # Create and submit.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test payment"
        }
    )
    await client.post(f"/operations/{operation_id}/submit")

    # First receipt - COMPLETED.
    await client.post(
        "/receipts",
        json={
            "providerPaymentId": "provider-1",
            "operationId": operation_id,
            "result": "COMPLETED",
            "message": "Payment completed",
            "occurredAt": datetime.utcnow().isoformat() + "Z"
        }
    )

    # Second receipt - REJECTED (conflict).
    response = await client.post(
        "/receipts",
        json={
            "providerPaymentId": "provider-2",
            "operationId": operation_id,
            "result": "REJECTED",
            "message": "Payment rejected",
            "occurredAt": datetime.utcnow().isoformat() + "Z"
        }
    )
    # Should return 204 (ignored).
    assert response.status_code == 204

    # Check that status didn't change.
    response = await client.get(f"/operations/{operation_id}")
    data = response.json()
    assert data["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_receipt_before_submit(client):
    """Test receipt before submission."""
    operation_id = "test-receipt-before"
    provider_payment_id = "provider-before"

    # Create operation.
    await client.post(
        "/operations",
        json={
            "operationId": operation_id,
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Test payment"
        }
    )

    # Receipt before submit.
    response = await client.post(
        "/receipts",
        json={
            "providerPaymentId": provider_payment_id,
            "operationId": operation_id,
            "result": "COMPLETED",
            "message": "Payment completed",
            "occurredAt": datetime.utcnow().isoformat() + "Z"
        }
    )
    assert response.status_code == 204

    # Submit.
    response = await client.post(f"/operations/{operation_id}/submit")
    # Should return COMPLETED.
    data = response.json()
    assert data["status"] == "COMPLETED"
