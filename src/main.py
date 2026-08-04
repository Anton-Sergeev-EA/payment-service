import asyncio
import json
import logging
from contextlib import asynccontextmanager
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
import uvicorn

from src.models import OperationStatus
from src.service import PaymentService, NotFoundError, ConflictError
from src.scheduler import Scheduler
from src.logging_config import setup_logging

# Setup logging.
setup_logging()
logger = logging.getLogger(__name__)

# Initialize service.
service = PaymentService()
scheduler = Scheduler(service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan."""
    logger.info("Starting payment service")

    # Start recovery process.
    asyncio.create_task(scheduler.recover_processing_operations())

    # Start periodic recovery.
    asyncio.create_task(scheduler.periodic_recovery())

    logger.info("Payment service started")
    yield

    logger.info("Shutting down payment service")
    await scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/operations", status_code=201)
async def create_operation(request: Request):
    """Create new operation."""
    try:
        data = await request.json()

        operation_id = data.get("operationId")
        amount = data.get("amount")
        currency = data.get("currency", "RUB")
        description = data.get("description", "")

        if not operation_id:
            raise HTTPException(status_code=400, detail="operationId is required")
        if not amount:
            raise HTTPException(status_code=400, detail="amount is required")

        operation = await service.create_operation(
            operation_id=operation_id,
            amount=amount,
            currency=currency,
            description=description
        )

        return JSONResponse(
            status_code=201,
            content={
                "operationId": operation.operation_id,
                "amount": str(operation.amount),
                "currency": operation.currency,
                "description": operation.description,
                "status": operation.status.value,
                "providerPaymentId": operation.provider_payment_id
            }
        )

    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating operation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/operations/{id}/submit")
async def submit_operation(id: str):
    """Submit operation for processing."""
    try:
        operation, created = await service.submit_operation(id)

        status_code = 202 if created else 200

        return JSONResponse(
            status_code=status_code,
            content={
                "operationId": operation.operation_id,
                "amount": str(operation.amount),
                "currency": operation.currency,
                "description": operation.description,
                "status": operation.status.value,
                "providerPaymentId": operation.provider_payment_id
            }
        )

    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error submitting operation {id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/receipts", status_code=204)
async def process_receipt(request: Request):
    """Process callback receipt."""
    try:
        data = await request.json()
        logger.info(f"Received receipt: {data}")

        success = await service.process_receipt(data)

        if not success:
            raise HTTPException(status_code=409, detail="Conflicting receipt")

        return JSONResponse(status_code=204, content=None)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing receipt: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/operations/{id}")
async def get_operation(id: str):
    """Get operation by ID."""
    try:
        operation = await service.get_operation(id)

        return {
            "operationId": operation.operation_id,
            "amount": str(operation.amount),
            "currency": operation.currency,
            "description": operation.description,
            "status": operation.status.value,
            "providerPaymentId": operation.provider_payment_id
        }

    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting operation {id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/operations/{id}/events")
async def get_events(id: str):
    """Get operation events."""
    try:
        events = await service.get_events(id)

        return [
            {
                "eventId": event.event_id,
                "type": event.event_type,
                "fromStatus": event.from_status,
                "toStatus": event.to_status,
                "message": event.message,
                "occurredAt": event.occurred_at.isoformat()
            }
            for event in events
        ]

    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting events for {id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False
    )
