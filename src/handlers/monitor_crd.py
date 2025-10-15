# pylint: disable=duplicate-code
"""KOPF handlers for Monitor CRD resources."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

import kopf
from kubernetes import client
from kubernetes.client.rest import ApiException

from ..config import config
from ..lunalytics.client import LunalyticsClient
from ..lunalytics.exceptions import LunalyticsAPIError, LunalyticsNotFoundError
from ..lunalytics.models import MonitorCreate, MonitorUpdate

logger = logging.getLogger(__name__)

# Kubernetes API clients
v1 = client.CoreV1Api()
networking_v1 = client.NetworkingV1Api()
custom_api = client.CustomObjectsApi()


async def _check_duplicate_annotations(
    url: str, namespace: str
) -> Optional[Dict[str, str]]:
    """Check if Ingress or Service annotations already exist for the same URL."""
    for resource_type, list_func in [
        ("ingress", networking_v1.list_namespaced_ingress),
        ("service", v1.list_namespaced_service),
    ]:
        try:
            resources = list_func(namespace)
            for item in resources.items:
                annotations = item.metadata.annotations or {}
                if (
                    annotations.get("lunalytics.io/enabled", "").lower() == "true"
                    and annotations.get("lunalytics.io/url") == url
                ):
                    return {
                        "type": resource_type,
                        "name": item.metadata.name,
                        "namespace": namespace,
                    }
        except ApiException as e:
            logger.warning(
                "Error listing %s resources in %s: %s", resource_type, namespace, e
            )
    return None


async def _update_monitor_status(
    namespace: str, name: str, status: Dict[str, Any]
) -> None:
    """Update Monitor CRD status."""
    try:
        status_body = {
            "status": {
                **status,
                "lastSyncTime": datetime.utcnow().isoformat() + "Z",
            }
        }
        custom_api.patch_namespaced_custom_object_status(
            group="lunalytics.io",
            version="v1alpha1",
            namespace=namespace,
            plural="monitors",
            name=name,
            body=status_body,
        )
        logger.info("Updated Monitor CRD %s/%s status to %s", namespace, name, status)
    except ApiException as e:
        logger.error("Error updating Monitor CRD status: %s", e)


def _get_monitor_config(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Get monitor configuration from spec."""
    return {
        "name": spec["name"],
        "url": spec["url"],
        "type": spec.get("type", "http"),
        "method": spec.get("method", "GET"),
        "interval": spec.get("interval", 30),
        "retry_interval": spec.get("retryInterval", 30),
        "request_timeout": spec.get("requestTimeout", 30),
        "valid_status_codes": spec.get("validStatusCodes", ["200-299"]),
    }


async def _create_or_update_monitor(
    lunalytics_client: LunalyticsClient,
    monitor_config: Dict[str, Any],
    existing_monitor_id: Optional[str],
) -> Dict[str, Any]:
    """Create or update a monitor in Lunalytics."""
    if existing_monitor_id:
        if await lunalytics_client.validate_monitor_exists(existing_monitor_id):
            update_payload = MonitorUpdate(
                monitor_id=existing_monitor_id,
                **{k: v for k, v in monitor_config.items() if k != "url"},
            )
            return await lunalytics_client.edit_monitor(update_payload)

    create_payload = MonitorCreate(**monitor_config)
    return await lunalytics_client.add_monitor(create_payload)


@kopf.on.create("lunalytics.io", "v1alpha1", "monitors")
@kopf.on.update("lunalytics.io", "v1alpha1", "monitors")
async def handle_monitor_create_or_update(
    spec: Dict[str, Any], namespace: str, name: str, status: Dict[str, Any], **_
):
    """Handle Monitor CRD create or update events."""
    if not config.is_namespace_monitored(namespace):
        logger.debug("Namespace %s not monitored for Monitor CRD %s", namespace, name)
        return

    logger.info("Processing Monitor CRD %s/%s", namespace, name)

    try:
        if not spec.get("name"):
            await _update_monitor_status(
                namespace, name, {"state": "error", "message": "Missing required field: name"}
            )
            return

        if not spec.get("url"):
            await _update_monitor_status(
                namespace, name, {"state": "error", "message": "Missing required field: url"}
            )
            return

        url = spec["url"]
        duplicate_handling = config.duplicate_handling

        if duplicate_handling == "annotation_priority":
            duplicate_info = await _check_duplicate_annotations(url, namespace)
            if duplicate_info:
                await _update_monitor_status(
                    namespace,
                    name,
                    {
                        "state": "conflict",
                        "message": f"Conflict: {duplicate_info['type'].title()} "
                        f"annotation takes precedence for URL {url}",
                    },
                )
                return

        monitor_config = _get_monitor_config(spec)
        existing_monitor_id = status.get("monitorId")

        async with LunalyticsClient() as lunalytics_client:
            monitor_response = await _create_or_update_monitor(
                lunalytics_client, monitor_config, existing_monitor_id
            )
            await _update_monitor_status(
                namespace,
                name,
                {
                    "state": "active",
                    "message": "Monitor created/updated successfully",
                    "monitorId": monitor_response.monitor_id,
                    "uptimePercentage": monitor_response.uptime_percentage,
                    "averageLatency": monitor_response.average_heartbeat_latency,
                },
            )
            logger.info(
                "Created/updated monitor %s for Monitor CRD %s/%s",
                monitor_response.monitor_id,
                namespace,
                name,
            )

    except LunalyticsAPIError as e:
        await _update_monitor_status(
            namespace, name, {"state": "error", "message": f"Lunalytics API error: {e}"}
        )
        logger.error(
            "Lunalytics API error for Monitor CRD %s/%s: %s", namespace, name, e
        )
    except ApiException as e:
        await _update_monitor_status(
            namespace, name, {"state": "error", "message": f"Kubernetes API error: {e}"}
        )
        logger.error(
            "Kubernetes API error for Monitor CRD %s/%s: %s", namespace, name, e
        )


@kopf.on.delete("lunalytics.io", "v1alpha1", "monitors")
async def handle_monitor_delete(
    namespace: str, name: str, status: Dict[str, Any], **_
):
    """Handle Monitor CRD delete events."""
    monitor_id = status.get("monitorId")

    if not monitor_id:
        logger.debug(
            "No monitor ID found for deleted Monitor CRD %s/%s", namespace, name
        )
        return

    logger.info("Deleting monitor %s for Monitor CRD %s/%s", monitor_id, namespace, name)

    try:
        async with LunalyticsClient() as lunalytics_client:
            await lunalytics_client.delete_monitor(monitor_id)
            logger.info(
                "Successfully deleted monitor %s for Monitor CRD %s/%s",
                monitor_id,
                namespace,
                name,
            )

    except LunalyticsNotFoundError:
        logger.info(
            "Monitor %s not found in Lunalytics (already deleted)", monitor_id
        )
    except LunalyticsAPIError as e:
        logger.error(
            "Error deleting monitor %s for Monitor CRD %s/%s: %s",
            monitor_id,
            namespace,
            name,
            e,
        )
    except ApiException as e:
        logger.error(
            "Kubernetes API error deleting monitor for Monitor CRD %s/%s: %s",
            namespace,
            name,
            e,
        )


@kopf.on.resume("lunalytics.io", "v1alpha1", "monitors")
async def handle_monitor_resume(
    namespace: str, name: str, status: Dict[str, Any], **_
):
    """Handle Monitor CRD resume events (operator startup)."""
    monitor_id = status.get("monitorId")
    if not monitor_id:
        return

    logger.info(
        "Validating monitor %s for resumed Monitor CRD %s/%s",
        monitor_id,
        namespace,
        name,
    )

    try:
        async with LunalyticsClient() as lunalytics_client:
            try:
                monitor_response = await lunalytics_client.get_monitor(monitor_id)
                await _update_monitor_status(
                    namespace,
                    name,
                    {
                        "state": "active",
                        "message": "Monitor validated successfully",
                        "monitorId": monitor_response.monitor_id,
                        "uptimePercentage": monitor_response.uptime_percentage,
                        "averageLatency": monitor_response.average_heartbeat_latency,
                    },
                )
                logger.info(
                    "Monitor %s validated for resumed Monitor CRD %s/%s",
                    monitor_id,
                    namespace,
                    name,
                )
            except LunalyticsNotFoundError:
                await _update_monitor_status(
                    namespace,
                    name,
                    {"state": "error", "message": "Monitor not found in Lunalytics"},
                )
                logger.warning(
                    "Monitor %s not found for resumed Monitor CRD %s/%s",
                    monitor_id,
                    namespace,
                    name,
                )

    except (LunalyticsAPIError, ApiException) as e:
        await _update_monitor_status(
            namespace, name, {"state": "error", "message": f"Error validating monitor: {e}"}
        )
        logger.error(
            "Error validating monitor %s for resumed Monitor CRD %s/%s: %s",
            monitor_id,
            namespace,
            name,
            e,
        )
