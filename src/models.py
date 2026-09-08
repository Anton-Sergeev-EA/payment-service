from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, List
from decimal import Decimal

class OperationStatus(str, Enum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"

@dataclass
class Operation:
    operation_id: str
    amount: Decimal
    currency: str
    description: str
    status: OperationStatus
    provider_payment_id: Optional[str]
    created_at: datetime
    updated_at: datetime

@dataclass
class Event:
    event_id: int
    operation_id: str
    event_type: str
    from_status: Optional[str]
    to_status: str
    message: str
    occurred_at: datetime

@dataclass
class Receipt:
    provider_payment_id: str
    operation_id: str
    result: str
    message: str
    occurred_at: datetime
    processed_at: datetime
