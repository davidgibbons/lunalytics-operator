"""Annotation parsing utilities for Lunalytics monitoring."""

import logging
import re
from typing import Any, Dict, List, Optional

from kubernetes.client.rest import ApiException

from ..config import config

logger = logging.getLogger(__name__)

ANNOTATION_PREFIX = "lunalytics.io/"

ANNOTATION_ENABLED = f"{ANNOTATION_PREFIX}enabled"
ANNOTATION_NAME = f"{ANNOTATION_PREFIX}name"
ANNOTATION_URL = f"{ANNOTATION_PREFIX}url"
ANNOTATION_INTERVAL = f"{ANNOTATION_PREFIX}interval"
ANNOTATION_RETRY_INTERVAL = f"{ANNOTATION_PREFIX}retry-interval"
ANNOTATION_REQUEST_TIMEOUT = f"{ANNOTATION_PREFIX}request-timeout"
ANNOTATION_METHOD = f"{ANNOTATION_PREFIX}method"
ANNOTATION_VALID_STATUS_CODES = f"{ANNOTATION_PREFIX}valid-status-codes"
ANNOTATION_MONITOR_ID = f"{ANNOTATION_PREFIX}monitor-id"


def is_monitoring_enabled(annotations: Dict[str, str]) -> bool:
    """Check if Lunalytics monitoring is enabled for a resource."""
    return annotations.get(ANNOTATION_ENABLED, "").lower() == "true"


def get_monitor_name(
    annotations: Dict[str, str], resource_name: str, resource_kind: str
) -> str:
    """Get monitor name from annotations or generate default."""
    name = annotations.get(ANNOTATION_NAME)
    if name:
        return name

    return f"{resource_kind}/{resource_name}"


def get_monitor_config_from_annotations(annotations: Dict[str, str]) -> Dict[str, Any]:
    """Extract monitor configuration from annotations."""
    config_dict = {}

    if url := annotations.get(ANNOTATION_URL):
        config_dict["url"] = url

    if interval := annotations.get(ANNOTATION_INTERVAL):
        try:
            config_dict["interval"] = int(interval)
        except ValueError:
            logger.warning("Invalid interval value: %s", interval)

    if retry_interval := annotations.get(ANNOTATION_RETRY_INTERVAL):
        try:
            config_dict["retry_interval"] = int(retry_interval)
        except ValueError:
            logger.warning("Invalid retry interval value: %s", retry_interval)

    if request_timeout := annotations.get(ANNOTATION_REQUEST_TIMEOUT):
        try:
            config_dict["request_timeout"] = int(request_timeout)
        except ValueError:
            logger.warning("Invalid request timeout value: %s", request_timeout)

    if method := annotations.get(ANNOTATION_METHOD):
        config_dict["method"] = method.upper()

    if status_codes := annotations.get(ANNOTATION_VALID_STATUS_CODES):
        codes = [code.strip() for code in status_codes.split(",")]
        config_dict["valid_status_codes"] = codes

    return config_dict


def get_monitor_id_from_annotations(annotations: Dict[str, str]) -> Optional[str]:
    """Get stored monitor ID from annotations."""
    return annotations.get(ANNOTATION_MONITOR_ID)


def create_monitor_id_annotation(monitor_id: str) -> Dict[str, str]:
    """Create annotation for storing monitor ID."""
    return {ANNOTATION_MONITOR_ID: monitor_id}


def merge_with_defaults(annotation_config: Dict[str, Any]) -> Dict[str, Any]:
    """Merge annotation configuration with defaults."""
    merged = config.monitor_defaults.copy()
    merged.update(annotation_config)
    return merged


def validate_monitor_config(config_dict: Dict[str, Any]) -> List[str]:
    """Validate monitor configuration and return list of errors."""
    errors = []

    if not config_dict.get("url"):
        errors.append("URL is required")

    if not config_dict.get("name"):
        errors.append("Name is required")

    for field in ["interval", "retry_interval", "request_timeout"]:
        value = config_dict.get(field)
        if value is not None and (not isinstance(value, int) or value < 1):
            errors.append(f"{field} must be a positive integer")

    method = config_dict.get("method", "").upper()
    valid_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
    if method and method not in valid_methods:
        errors.append(f"method must be one of: {', '.join(valid_methods)}")

    status_codes = config_dict.get("valid_status_codes", [])
    if status_codes:
        for code in status_codes:
            if not re.match(r"^\d{3}(-\d{3})?$", code):
                errors.append(f"Invalid status code format: {code}")

    return errors


def update_resource_annotations(
    api_instance,
    namespace: str,
    resource_type: str,
    name: str,
    annotations: Dict[str, str],
) -> bool:
    """Update resource annotations."""
    try:
        if resource_type.lower() == "ingress":
            resource = api_instance.read_namespaced_ingress(name, namespace)
            if not resource.metadata.annotations:
                resource.metadata.annotations = {}
            resource.metadata.annotations.update(annotations)
            api_instance.patch_namespaced_ingress(name, namespace, resource)

        elif resource_type.lower() == "service":
            resource = api_instance.read_namespaced_service(name, namespace)
            if not resource.metadata.annotations:
                resource.metadata.annotations = {}
            resource.metadata.annotations.update(annotations)
            api_instance.patch_namespaced_service(name, namespace, resource)

        logger.info(
            "Updated annotations for %s/%s: %s",
            resource_type,
            name,
            list(annotations.keys()),
        )
        return True

    except ApiException as e:
        logger.error(
            "Failed to update annotations for %s/%s: %s", resource_type, name, e
        )
        return False
    except (ValueError, TypeError) as e:
        logger.error(
            "Unexpected error updating annotations for %s/%s: %s",
            resource_type,
            name,
            e,
        )
        return False
