import asyncio
import logging
from datetime import datetime, timedelta
from typing import Set

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, service):
        self.service = service
        self.running = True
        self._recovery_task = None
        self._periodic_task = None
        self._active_tasks: Set[asyncio.Task] = set()

    async def recover_processing_operations(self):
        """Recover processing operations on startup."""
        logger.info("Starting recovery of processing operations...")

        operations = await self.service.get_processing_operations()
        logger.info(f"Found {len(operations)} processing operations to recover")

        for operation in operations:
            logger.info(f"Recovering operation {operation.operation_id}")
            try:
                # Create task and track it.
                task = asyncio.create_task(
                    self.service.process_payment(operation.operation_id)
                )
                self._active_tasks.add(task)
                task.add_done_callback(self._active_tasks.discard)

                await asyncio.sleep(0.1)  # Don't overload.
            except Exception as e:
                logger.error(f"Error recovering operation {operation.operation_id}: {e}")

    async def periodic_recovery(self):
        """Periodically check for stuck operations."""
        while self.running:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self.recover_processing_operations()
            except asyncio.CancelledError:
                logger.info("Periodic recovery cancelled")
                break
            except Exception as e:
                logger.error(f"Error in periodic recovery: {e}")

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down scheduler...")
        self.running = False

        # Cancel periodic task.
        if self._periodic_task and not self._periodic_task.done():
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass

        # Wait for active tasks to complete.
        if self._active_tasks:
            logger.info(f"Waiting for {len(self._active_tasks)} active tasks to complete...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_tasks, return_exceptions=True),
                    timeout=30
                )
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for active tasks, cancelling remaining...")
                for task in self._active_tasks:
                    if not task.done():
                        task.cancel()

        logger.info("Scheduler shutdown complete")
            