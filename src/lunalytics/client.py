"""Async HTTP client for Lunalytics API operations."""

import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx

from ..config import config
from ..utils.retry import async_retry
from .exceptions import (
    LunalyticsAPIError,
    LunalyticsAuthenticationError,
    LunalyticsNotFoundError,
    LunalyticsRateLimitError,
    LunalyticsServerError,
    LunalyticsValidationError,
)
from .models import MonitorCreate, MonitorResponse, MonitorUpdate

logger = logging.getLogger(__name__)


class LunalyticsClient:
    """Async HTTP client for Lunalytics API."""

    def __init__(self, api_url: Optional[str] = None, api_token: Optional[str] = None):
        """Initialize Lunalytics client."""
        self.api_url = api_url or config.lunalytics_api_url
        self.api_token = api_token or config.lunalytics_api_token
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"API Token {self.api_token}",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    async def _ensure_client(self):
        """Ensure HTTP client is initialized."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """Handle HTTP response and raise appropriate exceptions."""
        try:
            data = response.json()
        except json.JSONDecodeError:
            data = {"message": response.text or "Unknown error"}

        if response.status_code == 200:
            return data
        if response.status_code == 401:
            raise LunalyticsAuthenticationError(
                "Authentication failed - check API token",
                status_code=response.status_code,
                response_data=data,
            )
        if response.status_code == 404:
            raise LunalyticsNotFoundError(
                "Monitor not found",
                status_code=response.status_code,
                response_data=data,
            )
        if response.status_code == 422:
            raise LunalyticsValidationError(
                f"Validation failed: {data.get('message', 'Unknown validation error')}",
                status_code=response.status_code,
                response_data=data,
            )
        if response.status_code == 429:
            raise LunalyticsRateLimitError(
                "Rate limit exceeded",
                status_code=response.status_code,
                response_data=data,
            )
        if 500 <= response.status_code < 600:
            raise LunalyticsServerError(
                f"Server error: {data.get('message', 'Unknown server error')}",
                status_code=response.status_code,
                response_data=data,
            )

        raise LunalyticsAPIError(
            f"Unexpected error: {data.get('message', 'Unknown error')}",
            status_code=response.status_code,
            response_data=data,
        )

    @async_retry(
        exceptions=(
            LunalyticsServerError,
            LunalyticsRateLimitError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
        )
    )
    async def add_monitor(self, payload: MonitorCreate) -> MonitorResponse:
        """Add a new monitor."""
        await self._ensure_client()

        url = urljoin(self.api_url, "/api/monitor/add")
        logger.info("Creating monitor: %s -> %s", payload.name, payload.url)

        response = await self._client.post(url, json=payload.dict())
        data = self._handle_response(response)

        logger.info("Monitor created successfully: %s", data.get("monitorId"))
        return MonitorResponse(**data)

    @async_retry(
        exceptions=(
            LunalyticsServerError,
            LunalyticsRateLimitError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
        )
    )
    async def edit_monitor(self, payload: MonitorUpdate) -> MonitorResponse:
        """Edit an existing monitor."""
        await self._ensure_client()

        url = urljoin(self.api_url, "/api/monitor/edit")
        logger.info("Updating monitor: %s", payload.monitor_id)

        response = await self._client.post(url, json=payload.dict(by_alias=True))
        data = self._handle_response(response)

        logger.info("Monitor updated successfully: %s", payload.monitor_id)
        return MonitorResponse(**data)

    @async_retry(
        exceptions=(
            LunalyticsServerError,
            LunalyticsRateLimitError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
        )
    )
    async def delete_monitor(self, monitor_id: str) -> bool:
        """Delete a monitor."""
        await self._ensure_client()

        url = urljoin(self.api_url, "/api/monitor/delete")
        logger.info("Deleting monitor: %s", monitor_id)

        response = await self._client.get(url, params={"monitorId": monitor_id})
        self._handle_response(response)

        logger.info("Monitor deleted successfully: %s", monitor_id)
        return True

    @async_retry(
        exceptions=(
            LunalyticsServerError,
            LunalyticsRateLimitError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
        )
    )
    async def get_monitor(self, monitor_id: str) -> MonitorResponse:
        """Get monitor information."""
        await self._ensure_client()

        url = urljoin(self.api_url, "/api/monitor/id")
        logger.debug("Getting monitor: %s", monitor_id)

        response = await self._client.get(url, params={"monitorId": monitor_id})
        data = self._handle_response(response)

        return MonitorResponse(**data)

    async def validate_monitor_exists(self, monitor_id: str) -> bool:
        """Check if a monitor exists without raising exceptions."""
        try:
            await self.get_monitor(monitor_id)
            return True
        except LunalyticsNotFoundError:
            return False
        except (httpx.RequestError, LunalyticsAPIError) as e:
            logger.warning("Error checking monitor existence %s: %s", monitor_id, e)
            return False
