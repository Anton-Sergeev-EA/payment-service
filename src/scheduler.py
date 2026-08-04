import asyncio
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, service):
        self.service = service
        self.running = True
        self._recovery_task = None

    async def recover_processing_operations(self):
        """Recover processing operations on startup."""
        logger.info("Starting recovery of processing operations")

        operations = await self.service.get_processing_operations()
        logger.info(f"Found {len(operations)} processing operations to recover")

        for operation in operations:
            logger.info(f"Recovering operation {operation.operation_id}")
            try:
                # Check if operation has been processing for too long.
                processing_time = datetime.now(timezone.utc) - operation.updated_at
                if processing_time > timedelta(minutes=5):
                    logger.warning(f"Operation {operation.operation_id} has been processing for {processing_time}")

                # Re-process the payment.
                asyncio.create_task(self.service.process_payment(operation.operation_id))
                await asyncio.sleep(0.1)  # Don't overload.
            except Exception as e:
                logger.error(f"Error recovering operation {operation.operation_id}: {e}")

    async def periodic_recovery(self):
        """Periodically check for stuck operations."""
        while self.running:
            try:
                await asyncio.sleep(60)  # Check every minute.
                await self.recover_processing_operations()
            except Exception as e:
                logger.error(f"Error in periodic recovery: {e}")

    async def shutdown(self):
        """Graceful shutdown."""
        self.running = False
        if self._recovery_task:
            self._recovery_task.cancel()
            