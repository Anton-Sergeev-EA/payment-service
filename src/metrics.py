import logging
from typing import Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class Metrics:
    """Simple metrics collector."""

    def __init__(self):
        self._metrics = {
            "operations_total": 0,
            "operations_created": 0,
            "operations_processing": 0,
            "operations_completed": 0,
            "operations_rejected": 0,
            "retry_attempts": 0,
            "provider_errors": 0,
            "receipts_processed": 0,
            "receipts_ignored": 0,
            "recoveries": 0
        }
        self._processing_operations: Dict[str, datetime] = {}

    def increment(self, metric: str, value: int = 1):
        """Increment a metric."""
        if metric in self._metrics:
            self._metrics[metric] += value

    def set_processing(self, operation_id: str):
        """Track a processing operation."""
        self._processing_operations[operation_id] = datetime.utcnow()
        self.increment("operations_processing")

    def remove_processing(self, operation_id: str):
        """Remove a processing operation."""
        if operation_id in self._processing_operations:
            del self._processing_operations[operation_id]

    def get_processing_count(self) -> int:
        """Get number of processing operations."""
        return len(self._processing_operations)

    def get_processing_duration(self, operation_id: str) -> float:
        """Get duration of a processing operation."""
        if operation_id in self._processing_operations:
            return (datetime.utcnow() - self._processing_operations[operation_id]).total_seconds()
        return 0

    def get_metrics(self) -> Dict:
        """Get all metrics."""
        return {
            **self._metrics,
            "operations_processing_current": self.get_processing_count(),
            "stuck_operations": sum(
                1 for op_id in self._processing_operations
                if self.get_processing_duration(op_id) > 300  # 5 minutes.
            )
        }


# Global metrics instance.
metrics = Metrics()
