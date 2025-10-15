"""Pydantic models for Lunalytics API requests and responses."""

# pylint: disable=no-self-argument,too-few-public-methods

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


class MonitorCreate(BaseModel):
    """Model for creating a new monitor."""

    name: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., regex=r"^https?://")
    type: str = Field(default="http", regex=r"^(http|https|tcp|udp)$")
    method: str = Field(
        default="GET", regex=r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$"
    )
    valid_status_codes: List[str] = Field(default=["200-299"])
    interval: int = Field(default=30, ge=1, le=86400)  # 1 second to 1 day
    retry_interval: int = Field(default=30, ge=1, le=86400)
    request_timeout: int = Field(default=30, ge=1, le=300)  # 1 second to 5 minutes

    @validator("valid_status_codes")
    def validate_status_codes(cls, v):
        """Validate status codes format."""
        for code in v:
            if not re.match(r"^\d{3}(-\d{3})?$", code):
                raise ValueError(f"Invalid status code format: {code}")
        return v

    @validator("url")
    def validate_url(cls, v):
        """Ensure URL is properly formatted."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class MonitorUpdate(BaseModel):
    """Model for updating an existing monitor."""

    monitor_id: str = Field(..., alias="monitorId")
    name: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., regex=r"^https?://")
    type: str = Field(default="http", regex=r"^(http|https|tcp|udp)$")
    method: str = Field(
        default="GET", regex=r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$"
    )
    valid_status_codes: List[str] = Field(default=["200-299"])
    interval: int = Field(default=30, ge=1, le=86400)
    retry_interval: int = Field(default=30, ge=1, le=86400)
    request_timeout: int = Field(default=30, ge=1, le=300)

    @validator("valid_status_codes")
    def validate_status_codes(cls, v):
        """Validate status codes format."""
        for code in v:
            if not re.match(r"^\d{3}(-\d{3})?$", code):
                raise ValueError(f"Invalid status code format: {code}")
        return v


class Heartbeat(BaseModel):
    """Model for a single heartbeat."""

    id: int
    status: int
    latency: int
    date: int
    is_down: bool = Field(alias="isDown")
    message: str


class Certificate(BaseModel):
    """Model for SSL certificate information."""

    is_valid: bool = Field(alias="isValid")
    issuer: Dict[str, str]
    valid_from: str = Field(alias="validFrom")
    valid_till: str = Field(alias="validTill")
    valid_on: List[str] = Field(alias="validOn")
    days_remaining: str = Field(alias="daysRemaining")
    next_check: int = Field(alias="nextCheck")


class MonitorResponse(BaseModel):
    """Model for monitor response from Lunalytics API."""

    monitor_id: str = Field(alias="monitorId")
    name: str
    url: str
    interval: int
    retry_interval: int = Field(alias="retryInterval")
    request_timeout: int = Field(alias="requestTimeout")
    method: str
    headers: Dict[str, Any]
    body: Dict[str, Any]
    valid_status_codes: List[str]
    email: str
    type: str
    port: Optional[int]
    uptime_percentage: float = Field(alias="uptimePercentage")
    average_heartbeat_latency: float = Field(alias="averageHeartbeatLatency")
    show_filters: bool = Field(alias="showFilters")
    paused: bool
    heartbeats: List[Heartbeat]
    cert: Optional[Certificate]

    class Config:
        """Pydantic config."""

        allow_population_by_field_name = True


class MonitorDeleteRequest(BaseModel):
    """Model for monitor deletion request."""

    monitor_id: str = Field(..., alias="monitorId")

    class Config:
        """Pydantic config."""

        allow_population_by_field_name = True


class MonitorGetRequest(BaseModel):
    """Model for monitor retrieval request."""

    monitor_id: str = Field(..., alias="monitorId")

    class Config:
        """Pydantic config."""

        allow_population_by_field_name = True
