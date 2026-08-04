import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, List, Tuple
import asyncio

from src.models import Operation, OperationStatus, Event, Receipt
from src.database import db
from src.provider import ProviderClient
from src.metrics import metrics

logger = logging.getLogger(__name__)


class PaymentService:
    """Core payment service with idempotent operations."""

    def __init__(self):
        self.provider = ProviderClient()
        self._processing_tasks = {}

    async def create_operation(
            self,
            operation_id: str,
            amount: str,
            currency: str,
            description: str
    ) -> Operation:
        """
        Create new payment operation.

        Args:
            operation_id: Unique operation identifier.
            amount: Payment amount as string.
            currency: Currency code (RUB).
            description: Operation description.

        Returns:
            Created Operation object.

        Raises:
            ConflictError: If operation already exists.
            ValueError: If validation fails.
        """
        async with db.get_connection() as conn:
            # Check if operation already exists.
            cursor = await conn.execute(
                "SELECT * FROM operations WHERE operation_id = ?",
                (operation_id,)
            )
            existing = await cursor.fetchone()
            if existing:
                metrics.increment("operations_conflict")
                raise ConflictError(f"Operation {operation_id} already exists")

            # Validate amount.
            try:
                amount_dec = Decimal(amount)
                if amount_dec <= 0:
                    raise ValueError("Amount must be positive")
                if amount_dec.as_tuple().exponent < -2:
                    raise ValueError("Amount must have at most 2 decimal places")
            except:
                raise ValueError("Invalid amount format")

            if currency != "RUB":
                raise ValueError("Only RUB currency supported")

            now = datetime.now(timezone.utc).isoformat()

            # Insert operation.
            await conn.execute(
                """INSERT INTO operations 
                   (operation_id, amount, currency, description, status, provider_payment_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (operation_id, amount, currency, description, OperationStatus.CREATED.value, None, now, now)
            )

            # Insert event.
            await conn.execute(
                """INSERT INTO events 
                   (operation_id, event_type, from_status, to_status, message, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (operation_id, "CREATED", None, OperationStatus.CREATED.value, "Operation created", now)
            )

            await conn.commit()

            # Update metrics.
            metrics.increment("operations_total")
            metrics.increment("operations_created")

            logger.info(
                f"Operation {operation_id} created",
                extra={
                    "operation_id": operation_id,
                    "amount": amount,
                    "currency": currency
                }
            )

            return Operation(
                operation_id=operation_id,
                amount=amount_dec,
                currency=currency,
                description=description,
                status=OperationStatus.CREATED,
                provider_payment_id=None,
                created_at=datetime.fromisoformat(now),
                updated_at=datetime.fromisoformat(now)
            )

    async def submit_operation(self, operation_id: str) -> Tuple[Operation, bool]:
        """
        Submit operation for processing.

        Args:
            operation_id: Operation identifier.

        Returns:
            Tuple of (Operation, bool) where bool indicates if new submission was created.
        """
        async with db.get_connection() as conn:
            # Get operation with lock.
            cursor = await conn.execute(
                "SELECT * FROM operations WHERE operation_id = ?",
                (operation_id,)
            )
            row = await cursor.fetchone()
            if not row:
                raise NotFoundError(f"Operation {operation_id} not found")

            operation = self._row_to_operation(row)

            # If already PROCESSING or final, return current state.
            if operation.status in [OperationStatus.PROCESSING, OperationStatus.COMPLETED, OperationStatus.REJECTED]:
                logger.info(
                    f"Operation {operation_id} already in status {operation.status}",
                    extra={
                        "operation_id": operation_id,
                        "status": operation.status.value
                    }
                )
                return operation, False

            if operation.status != OperationStatus.CREATED:
                raise ValueError(f"Invalid status: {operation.status}")

            # Update to PROCESSING atomically.
            now = datetime.now(timezone.utc).isoformat()
            await conn.execute(
                """UPDATE operations 
                   SET status = ?, updated_at = ?
                   WHERE operation_id = ? AND status = ?""",
                (OperationStatus.PROCESSING.value, now, operation_id, OperationStatus.CREATED.value)
            )

            # Check if update succeeded (race condition).
            cursor = await conn.execute(
                "SELECT * FROM operations WHERE operation_id = ?",
                (operation_id,)
            )
            row = await cursor.fetchone()
            updated = self._row_to_operation(row)

            if updated.status != OperationStatus.PROCESSING:
                # Another request already changed it.
                logger.info(
                    f"Operation {operation_id} already changed to {updated.status}",
                    extra={
                        "operation_id": operation_id,
                        "status": updated.status.value
                    }
                )
                return updated, False

            # Add event.
            await conn.execute(
                """INSERT INTO events 
                   (operation_id, event_type, from_status, to_status, message, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (operation_id, "SUBMIT", OperationStatus.CREATED.value, OperationStatus.PROCESSING.value,
                 "Operation submitted for processing", now)
            )
            await conn.commit()

            # Update metrics.
            metrics.set_processing(operation_id)
            metrics.increment("operations_processing")

            logger.info(
                f"Operation {operation_id} submitted for processing",
                extra={
                    "operation_id": operation_id,
                    "status": OperationStatus.PROCESSING.value
                }
            )

            # Schedule async processing.
            task = asyncio.create_task(self._process_payment_async(operation_id))
            self._processing_tasks[operation_id] = task
            task.add_done_callback(lambda t: self._processing_tasks.pop(operation_id, None))

            return updated, True

    async def _process_payment_async(self, operation_id: str):
        """Background processing of payment."""
        try:
            # Wait a moment to ensure transaction is committed.
            await asyncio.sleep(0.1)
            await self.process_payment(operation_id)
        except Exception as e:
            logger.error(
                f"Error processing payment {operation_id}: {e}",
                extra={"operation_id": operation_id},
                exc_info=True
            )

    async def process_payment(self, operation_id: str):
        """Process payment with provider."""
        logger.info(
            f"Processing payment {operation_id}",
            extra={"operation_id": operation_id}
        )

        # Get operation.
        async with db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM operations WHERE operation_id = ?",
                (operation_id,)
            )
            row = await cursor.fetchone()
            if not row:
                logger.error(
                    f"Operation {operation_id} not found",
                    extra={"operation_id": operation_id}
                )
                return

            operation = self._row_to_operation(row)

            if operation.status != OperationStatus.PROCESSING:
                logger.info(
                    f"Operation {operation_id} is no longer PROCESSING, skipping",
                    extra={
                        "operation_id": operation_id,
                        "status": operation.status.value
                    }
                )
                return

            # Check if already has provider_payment_id from callback.
            if operation.provider_payment_id:
                logger.info(
                    f"Operation {operation_id} already has provider_payment_id: {operation.provider_payment_id}",
                    extra={
                        "operation_id": operation_id,
                        "provider_payment_id": operation.provider_payment_id
                    }
                )
                return

        # Call provider with retry.
        try:
            result = await self.provider.create_payment(
                operation_id=operation_id,
                amount=str(operation.amount),
                currency=operation.currency
            )

            # Update with provider_payment_id.
            async with db.get_connection() as conn:
                await conn.execute(
                    """UPDATE operations 
                       SET provider_payment_id = ?, updated_at = ?
                       WHERE operation_id = ? AND provider_payment_id IS NULL""",
                    (result["provider_payment_id"], datetime.now(timezone.utc).isoformat(), operation_id)
                )
                await conn.commit()

            # Reset provider retry counter on success.
            self.provider.reset_retry_count()

            logger.info(
                f"Payment {operation_id} accepted by provider: {result['provider_payment_id']}",
                extra={
                    "operation_id": operation_id,
                    "provider_payment_id": result["provider_payment_id"]
                }
            )

        except Exception as e:
            metrics.increment("provider_errors")
            logger.error(
                f"Error calling provider for {operation_id}: {e}",
                extra={"operation_id": operation_id},
                exc_info=True
            )
            # Operation stays PROCESSING for retry.

    async def process_receipt(self, receipt_data: Dict) -> bool:
        """
        Process callback receipt from provider.

        Args:
            receipt_data: Receipt data from provider.

        Returns:
            True if receipt was processed successfully.
        """
        receipt = Receipt(
            provider_payment_id=receipt_data["providerPaymentId"],
            operation_id=receipt_data["operationId"],
            result=receipt_data["result"],
            message=receipt_data.get("message", ""),
            occurred_at=datetime.fromisoformat(receipt_data["occurredAt"].replace('Z', '+00:00')),
            processed_at=datetime.now(timezone.utc)
        )

        logger.info(
            f"Processing receipt for operation {receipt.operation_id}, result: {receipt.result}",
            extra={
                "operation_id": receipt.operation_id,
                "provider_payment_id": receipt.provider_payment_id
            }
        )

        async with db.get_connection() as conn:
            # Start transaction
            await conn.execute("BEGIN")

            try:
                # Check if receipt already processed.
                cursor = await conn.execute(
                    "SELECT * FROM receipts WHERE provider_payment_id = ?",
                    (receipt.provider_payment_id,)
                )
                existing_receipt = await cursor.fetchone()
                if existing_receipt:
                    logger.info(
                        f"Receipt {receipt.provider_payment_id} already processed",
                        extra={
                            "operation_id": receipt.operation_id,
                            "provider_payment_id": receipt.provider_payment_id
                        }
                    )
                    await conn.commit()
                    metrics.increment("receipts_duplicate")
                    return True

                # Get operation.
                cursor = await conn.execute(
                    "SELECT * FROM operations WHERE operation_id = ?",
                    (receipt.operation_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    logger.error(
                        f"Operation {receipt.operation_id} not found",
                        extra={"operation_id": receipt.operation_id}
                    )
                    await conn.commit()
                    return False

                operation = self._row_to_operation(row)
                status_result = OperationStatus(receipt.result) if receipt.result in ["COMPLETED", "REJECTED"] else None

                if not status_result:
                    logger.error(
                        f"Invalid result: {receipt.result}",
                        extra={
                            "operation_id": receipt.operation_id,
                            "result": receipt.result
                        }
                    )
                    await conn.commit()
                    return False

                # Check if operation already final.
                if operation.status in [OperationStatus.COMPLETED, OperationStatus.REJECTED]:
                    logger.info(
                        f"Operation {receipt.operation_id} already final: {operation.status}",
                        extra={
                            "operation_id": receipt.operation_id,
                            "status": operation.status.value
                        }
                    )

                    # Store receipt as processed anyway.
                    await self._store_receipt(conn, receipt, "IGNORED")
                    await conn.commit()
                    metrics.increment("receipts_ignored")
                    return True

                # Check provider_payment_id consistency.
                if operation.provider_payment_id and operation.provider_payment_id != receipt.provider_payment_id:
                    logger.error(
                        f"Provider payment ID mismatch: {operation.provider_payment_id} != {receipt.provider_payment_id}",
                        extra={
                            "operation_id": receipt.operation_id,
                            "expected": operation.provider_payment_id,
                            "received": receipt.provider_payment_id
                        }
                    )
                    await conn.commit()
                    return False

                # Check if final status already set by another receipt.
                cursor = await conn.execute(
                    "SELECT * FROM processed_receipts WHERE operation_id = ?",
                    (receipt.operation_id,)
                )
                processed = await cursor.fetchone()
                if processed and processed["result"] != receipt.result:
                    logger.warning(
                        f"Operation {receipt.operation_id} already has result {processed['result']}, ignoring {receipt.result}",
                        extra={
                            "operation_id": receipt.operation_id,
                            "existing_result": processed["result"],
                            "new_result": receipt.result
                        }
                    )
                    await self._store_receipt(conn, receipt, "IGNORED")
                    await conn.commit()
                    metrics.increment("receipts_conflict")
                    return True

                # Update operation.
                now = datetime.now(timezone.utc).isoformat()
                await conn.execute(
                    """UPDATE operations 
                       SET status = ?, provider_payment_id = ?, updated_at = ?
                       WHERE operation_id = ?""",
                    (status_result.value, receipt.provider_payment_id, now, receipt.operation_id)
                )

                # Add event.
                await conn.execute(
                    """INSERT INTO events 
                       (operation_id, event_type, from_status, to_status, message, occurred_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (receipt.operation_id, "RECEIPT", operation.status.value, status_result.value,
                     receipt.message, receipt.occurred_at.isoformat())
                )

                # Store receipt.
                await self._store_receipt(conn, receipt, "PROCESSED")

                # Store processed receipt for conflict detection.
                await conn.execute(
                    """INSERT OR REPLACE INTO processed_receipts 
                       (operation_id, provider_payment_id, result)
                       VALUES (?, ?, ?)""",
                    (receipt.operation_id, receipt.provider_payment_id, receipt.result)
                )

                await conn.commit()

                # Update metrics.
                metrics.remove_processing(receipt.operation_id)
                metrics.increment("receipts_processed")
                if status_result == OperationStatus.COMPLETED:
                    metrics.increment("operations_completed")
                else:
                    metrics.increment("operations_rejected")

                logger.info(
                    f"Operation {receipt.operation_id} updated to {status_result.value}",
                    extra={
                        "operation_id": receipt.operation_id,
                        "status": status_result.value,
                        "provider_payment_id": receipt.provider_payment_id
                    }
                )

                return True

            except Exception as e:
                await conn.rollback()
                logger.error(
                    f"Error processing receipt: {e}",
                    extra={"operation_id": receipt.operation_id},
                    exc_info=True
                )
                raise

    async def _store_receipt(self, conn, receipt: Receipt, status: str):
        """Store receipt in database."""
        await conn.execute(
            """INSERT INTO receipts 
               (provider_payment_id, operation_id, result, message, occurred_at, processed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (receipt.provider_payment_id, receipt.operation_id, receipt.result,
             receipt.message, receipt.occurred_at.isoformat(), receipt.processed_at.isoformat())
        )

    async def get_operation(self, operation_id: str) -> Operation:
        """Get operation by ID."""
        async with db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM operations WHERE operation_id = ?",
                (operation_id,)
            )
            row = await cursor.fetchone()
            if not row:
                raise NotFoundError(f"Operation {operation_id} not found")
            return self._row_to_operation(row)

    async def get_events(self, operation_id: str) -> List[Event]:
        """Get operation events."""
        async with db.get_connection() as conn:
            cursor = await conn.execute(
                """SELECT * FROM events 
                   WHERE operation_id = ? 
                   ORDER BY event_id ASC""",
                (operation_id,)
            )
            rows = await cursor.fetchall()
            return [self._row_to_event(row) for row in rows]

    async def get_processing_operations(self) -> List[Operation]:
        """Get all PROCESSING operations for recovery."""
        async with db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM operations WHERE status = ?",
                (OperationStatus.PROCESSING.value,)
            )
            rows = await cursor.fetchall()
            return [self._row_to_operation(row) for row in rows]

    def _row_to_operation(self, row) -> Operation:
        """Convert database row to Operation object."""
        return Operation(
            operation_id=row["operation_id"],
            amount=Decimal(row["amount"]),
            currency=row["currency"],
            description=row["description"],
            status=OperationStatus(row["status"]),
            provider_payment_id=row["provider_payment_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
        )

    def _row_to_event(self, row) -> Event:
        """Convert database row to Event object."""
        return Event(
            event_id=row["event_id"],
            operation_id=row["operation_id"],
            event_type=row["event_type"],
            from_status=row["from_status"],
            to_status=row["to_status"],
            message=row["message"],
            occurred_at=datetime.fromisoformat(row["occurred_at"])
        )

    async def shutdown(self):
        """Graceful shutdown of service."""
        logger.info("Shutting down payment service")

        # Cancel all processing tasks.
        if self._processing_tasks:
            logger.info(f"Cancelling {len(self._processing_tasks)} processing tasks")
            for task in self._processing_tasks.values():
                if not task.done():
                    task.cancel()

            # Wait for tasks to complete.
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._processing_tasks.values(), return_exceptions=True),
                    timeout=10
                )
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for processing tasks")

        await self.provider.close()
        logger.info("Payment service shutdown complete")


class NotFoundError(Exception):
    """Raised when operation is not found."""
    pass


class ConflictError(Exception):
    """Raised when operation already exists."""
    pass
