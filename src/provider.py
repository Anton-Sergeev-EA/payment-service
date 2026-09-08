import logging
import os
import asyncio
import random
from typing import Dict, Optional
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_random,
    retry_if_exception_type,
    before_sleep_log
)

logger = logging.getLogger(__name__)


class ProviderClient:
    """HTTP client for external payment provider."""

    def __init__(self):
        self.base_url = os.getenv("PROVIDER_URL", "http://provider-simulator:8081")
        self.timeout = httpx.Timeout(10.0, connect=5.0)
        self.client = httpx.AsyncClient(timeout=self.timeout)
        self._retry_count = 0

    @retry(
        retry=retry_if_exception_type((
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.ConnectError,
                httpx.ConnectTimeout
        )),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=30) + wait_random(0, 0.5),
        stop=stop_after_attempt(5),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def create_payment(self, operation_id: str, amount: str, currency: str) -> Dict:
        """
        Create payment with provider.

        Args:
            operation_id: Unique operation identifier (used as Idempotency-Key).
            amount: Payment amount as string.
            currency: Currency code (RUB).

        Returns:
            Dict containing provider_payment_id and status.

        Raises:
            httpx.HTTPError: On network or HTTP errors.
        """
        self._retry_count += 1
        attempt = self._retry_count

        # Log retry attempt with structured fields.
        logger.warning(
            f"Calling provider for operation {operation_id}, attempt {attempt}",
            extra={
                "operation_id": operation_id,
                "attempt": attempt
            }
        )

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

            # Log successful response.
            logger.info(
                f"Provider response for {operation_id}: {data}",
                extra={
                    "operation_id": operation_id,
                    "provider_payment_id": data.get("providerPaymentId"),
                    "attempt": attempt
                }
            )

            return {
                "provider_payment_id": data.get("providerPaymentId"),
                "status": data.get("status")
            }

        except httpx.HTTPStatusError as e:
            # Handle specific HTTP status codes.
            if e.response.status_code == 503:
                logger.warning(
                    f"Provider service unavailable for {operation_id}",
                    extra={
                        "operation_id": operation_id,
                        "attempt": attempt,
                        "status_code": 503
                    }
                )
                raise httpx.NetworkError("Service unavailable")

            elif e.response.status_code == 409:
                # Conflict - payment already exists, this is idempotent behavior.
                logger.info(
                    f"Payment {operation_id} already exists (idempotent)",
                    extra={
                        "operation_id": operation_id,
                        "attempt": attempt
                    }
                )
                try:
                    error_data = e.response.json()
                    return {
                        "provider_payment_id": error_data.get("providerPaymentId"),
                        "status": "ACCEPTED"
                    }
                except:
                    # If can't parse response, return generic.
                    return {
                        "provider_payment_id": None,
                        "status": "ACCEPTED"
                    }
            else:
                logger.error(
                    f"Provider HTTP error for {operation_id}: {e}",
                    extra={
                        "operation_id": operation_id,
                        "attempt": attempt,
                        "status_code": e.response.status_code
                    }
                )
                raise

        except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError, httpx.ConnectTimeout) as e:
            # Network errors - will be retried by tenacity.
            logger.error(
                f"Network error calling provider for {operation_id}: {e}",
                extra={
                    "operation_id": operation_id,
                    "attempt": attempt
                }
            )
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error calling provider for {operation_id}: {e}",
                extra={
                    "operation_id": operation_id,
                    "attempt": attempt
                },
                exc_info=True
            )
            raise

    async def close(self):
        """Close HTTP client session."""
        await self.client.aclose()

    def reset_retry_count(self):
        """Reset retry counter."""
        self._retry_count = 0
