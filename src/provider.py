import logging
import os
import asyncio
from typing import Dict, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class ProviderClient:
    def __init__(self):
        self.base_url = os.getenv("PROVIDER_URL", "http://provider-simulator:8081")
        self.timeout = httpx.Timeout(10.0, connect=5.0)
        self.client = httpx.AsyncClient(timeout=self.timeout)

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError,
                                       httpx.ConnectError, httpx.ConnectTimeout)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=30),
        stop=stop_after_attempt(5),
        reraise=True
    )
    async def create_payment(self, operation_id: str, amount: str, currency: str) -> Dict:
        """Create payment with provider."""
        url = f"{self.base_url}/payments"

        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": operation_id,
            "X-Correlation-ID": operation_id
        }

        body = {
            "operationId": operation_id,
            "amount": amount,
            "currency": currency
        }

        try:
            response = await self.client.post(url, json=body, headers=headers)
            response.raise_for_status()

            data = response.json()
            logger.info(f"Provider response for {operation_id}: {data}")

            return {
                "provider_payment_id": data.get("providerPaymentId"),
                "status": data.get("status")
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 503:
                logger.warning(f"Provider service unavailable for {operation_id}")
                raise httpx.NetworkError("Service unavailable")
            elif e.response.status_code == 409:
                # Conflict - payment already exists, this is fine.
                logger.info(f"Payment {operation_id} already exists")
                return {
                    "provider_payment_id": e.response.json().get("providerPaymentId"),
                    "status": "ACCEPTED"
                }
            else:
                logger.error(f"Provider error for {operation_id}: {e}")
                raise

        except Exception as e:
            logger.error(f"Error calling provider for {operation_id}: {e}")
            raise

    async def close(self):
        await self.client.aclose()
