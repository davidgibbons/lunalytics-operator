"""
Async HTTP client for Lunalytics API operations.
"""

import logging
from typing import Dict, Any, Optional
import httpx
from urllib.parse import urljoin

from .models import MonitorCreate, MonitorUpdate, MonitorResponse, MonitorDeleteRequest, MonitorGetRequest
from .exceptions import (
    LunalyticsAPIError,
    LunalyticsAuthenticationError,
    LunalyticsNotFoundError,
    LunalyticsValidationError,
    LunalyticsServerError,
    LunalyticsRateLimitError,
    LunalyticsRetryExhaustedError
)
from ..config import config
from ..utils.retry import async_retry

logger = logging.getLogger(__name__)


class LunalyticsClient:
    """Async HTTP client for Lunalytics API."""
    
    def __init__(self, api_url: Optional[str] = None, api_token: Optional[str] = None):
        """
        Initialize Lunalytics client.
        
        Args:
            api_url: Lunalytics API base URL
            api_token: API authentication token
        """
        self.api_url = api_url or config.lunalytics_api_url
        self.api_token = api_token or config.lunalytics_api_token
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'API Token {self.api_token}'
            }
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
        """
        Handle HTTP response and raise appropriate exceptions.
        
        Args:
            response: HTTP response object
            
        Returns:
            Response JSON data
            
        Raises:
            Various LunalyticsAPIError subclasses based on status code
        """
        try:
            data = response.json()
        except Exception:
            data = {'message': response.text or 'Unknown error'}
        
        if response.status_code == 200:
            return data
        elif response.status_code == 401:
            raise LunalyticsAuthenticationError(
                "Authentication failed - check API token",
                status_code=response.status_code,
                response_data=data
            )
        elif response.status_code == 404:
            raise LunalyticsNotFoundError(
                "Monitor not found",
                status_code=response.status_code,
                response_data=data
            )
        elif response.status_code == 422:
            raise LunalyticsValidationError(
                f"Validation failed: {data.get('message', 'Unknown validation error')}",
                status_code=response.status_code,
                response_data=data
            )
        elif response.status_code == 429:
            raise LunalyticsRateLimitError(
                "Rate limit exceeded",
                status_code=response.status_code,
                response_data=data
            )
        elif 500 <= response.status_code < 600:
            raise LunalyticsServerError(
                f"Server error: {data.get('message', 'Unknown server error')}",
                status_code=response.status_code,
                response_data=data
            )
        else:
            raise LunalyticsAPIError(
                f"Unexpected error: {data.get('message', 'Unknown error')}",
                status_code=response.status_code,
                response_data=data
            )
    
    @async_retry(exceptions=(
        LunalyticsServerError,
        LunalyticsRateLimitError,
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.RemoteProtocolError
    ))
    async def add_monitor(self, payload: MonitorCreate) -> MonitorResponse:
        """
        Add a new monitor.
        
        Args:
            payload: Monitor creation payload
            
        Returns:
            Created monitor response
            
        Raises:
            LunalyticsAPIError: If API call fails
        """
        await self._ensure_client()
        
        url = urljoin(self.api_url, '/api/monitor/add')
        logger.info(f"Creating monitor: {payload.name} -> {payload.url}")
        
        response = await self._client.post(url, json=payload.dict())
        data = self._handle_response(response)
        
        logger.info(f"Monitor created successfully: {data.get('monitorId')}")
        return MonitorResponse(**data)
    
    @async_retry(exceptions=(
        LunalyticsServerError,
        LunalyticsRateLimitError,
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.RemoteProtocolError
    ))
    async def edit_monitor(self, payload: MonitorUpdate) -> MonitorResponse:
        """
        Edit an existing monitor.
        
        Args:
            payload: Monitor update payload
            
        Returns:
            Updated monitor response
            
        Raises:
            LunalyticsAPIError: If API call fails
        """
        await self._ensure_client()
        
        url = urljoin(self.api_url, '/api/monitor/edit')
        logger.info(f"Updating monitor: {payload.monitor_id}")
        
        response = await self._client.post(url, json=payload.dict(by_alias=True))
        data = self._handle_response(response)
        
        logger.info(f"Monitor updated successfully: {payload.monitor_id}")
        return MonitorResponse(**data)
    
    @async_retry(exceptions=(
        LunalyticsServerError,
        LunalyticsRateLimitError,
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.RemoteProtocolError
    ))
    async def delete_monitor(self, monitor_id: str) -> bool:
        """
        Delete a monitor.
        
        Args:
            monitor_id: Monitor ID to delete
            
        Returns:
            True if deletion was successful
            
        Raises:
            LunalyticsAPIError: If API call fails
        """
        await self._ensure_client()
        
        url = urljoin(self.api_url, '/api/monitor/delete')
        logger.info(f"Deleting monitor: {monitor_id}")
        
        response = await self._client.get(url, params={'monitorId': monitor_id})
        data = self._handle_response(response)
        
        logger.info(f"Monitor deleted successfully: {monitor_id}")
        return True
    
    @async_retry(exceptions=(
        LunalyticsServerError,
        LunalyticsRateLimitError,
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.RemoteProtocolError
    ))
    async def get_monitor(self, monitor_id: str) -> MonitorResponse:
        """
        Get monitor information.
        
        Args:
            monitor_id: Monitor ID to retrieve
            
        Returns:
            Monitor response data
            
        Raises:
            LunalyticsAPIError: If API call fails
        """
        await self._ensure_client()
        
        url = urljoin(self.api_url, '/api/monitor/id')
        logger.debug(f"Getting monitor: {monitor_id}")
        
        response = await self._client.get(url, params={'monitorId': monitor_id})
        data = self._handle_response(response)
        
        return MonitorResponse(**data)
    
    async def validate_monitor_exists(self, monitor_id: str) -> bool:
        """
        Check if a monitor exists without raising exceptions.
        
        Args:
            monitor_id: Monitor ID to check
            
        Returns:
            True if monitor exists, False otherwise
        """
        try:
            await self.get_monitor(monitor_id)
            return True
        except LunalyticsNotFoundError:
            return False
        except Exception as e:
            logger.warning(f"Error checking monitor existence {monitor_id}: {e}")
            return False
