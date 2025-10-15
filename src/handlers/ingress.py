# pylint: disable=duplicate-code
"""KOPF handlers for Ingress resources."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

import kopf
from kubernetes import client

from ..config import config
from ..lunalytics.client import LunalyticsClient
from ..lunalytics.exceptions import LunalyticsAPIError, LunalyticsNotFoundError
from ..lunalytics.models import MonitorCreate, MonitorUpdate
from ..utils.annotations import (
    create_monitor_id_annotation,
    get_monitor_config_from_annotations,
    get_monitor_id_from_annotations,
    get_monitor_name,
    is_monitoring_enabled,
    merge_with_defaults,
    update_resource_annotations,
    validate_monitor_config,
)
from ..utils.url_builder import build_monitor_url

logger = logging.getLogger(__name__)

networking_v1 = client.NetworkingV1Api()


async def _check_duplicate_monitor(url: str, namespace: str) -> Optional[str]:
    """Check if a Monitor CRD already exists for the same URL."""
    try:
        custom_api = client.CustomObjectsApi()
        monitors = custom_api.list_namespaced_custom_object(
            group="lunalytics.io",
            version="v1alpha1",
            namespace=namespace,
            plural="monitors",
        )
        for monitor in monitors.get("items", []):
            monitor_spec = monitor.get("spec", {})
            if monitor_spec.get("url") == url:
                return monitor.get("metadata", {}).get("name")
        return None
    except client.ApiException as e:
        logger.warning("Error checking for duplicate monitors: %s", e)
        return None


async def _handle_duplicate_conflict(
    duplicate_name: str, namespace: str, url: str
) -> None:
    """Handle duplicate conflict by updating Monitor CRD status."""
    try:
        custom_api = client.CustomObjectsApi()
        patch_body = {
            "status": {
                "state": "conflict",
                "message": f"Conflict: Ingress annotation takes precedence for URL {url}",
                "lastSyncTime": datetime.utcnow().isoformat() + "Z",
            }
        }
        custom_api.patch_namespaced_custom_object_status(
            group="lunalytics.io",
            version="v1alpha1",
            namespace=namespace,
            plural="monitors",
            name=duplicate_name,
            body=patch_body,
        )
        logger.info(
            "Updated Monitor CRD %s to conflict state due to annotation precedence",
            duplicate_name,
        )
    except client.ApiException as e:
        logger.error("Error updating Monitor CRD conflict status: %s", e)


async def _get_and_validate_monitor_config(
    annotations: Dict[str, Any], spec: Dict[str, Any], namespace: str, name: str
) -> Optional[Dict[str, Any]]:
    """Get and validate monitor configuration from annotations."""
    annotation_config = get_monitor_config_from_annotations(annotations)
    url = build_monitor_url(
        resource_spec=spec,
        resource_type="ingress",
        resource_name=name,
        namespace=namespace,
        explicit_url=annotation_config.get("url"),
    )
    if not url:
        logger.error("Could not build URL for Ingress %s/%s", namespace, name)
        return None

    monitor_name = get_monitor_name(annotations, name, "Ingress")
    annotation_config["name"] = monitor_name
    annotation_config["url"] = url

    monitor_config = merge_with_defaults(annotation_config)
    validation_errors = validate_monitor_config(monitor_config)
    if validation_errors:
        logger.error(
            "Invalid monitor configuration for Ingress %s/%s: %s",
            namespace,
            name,
            validation_errors,
        )
        return None

    return monitor_config


@kopf.on.create("networking.k8s.io", "v1", "ingresses")
@kopf.on.update("networking.k8s.io", "v1", "ingresses")
async def handle_ingress_create_or_update(
    spec: Dict[str, Any], meta: Dict[str, Any], namespace: str, name: str, **_
):
    """Handle Ingress create or update events."""
    annotations = meta.get("annotations", {})
    if not config.is_namespace_monitored(namespace):
        logger.debug("Namespace %s not monitored for Ingress %s", namespace, name)
        return

    if not is_monitoring_enabled(annotations):
        logger.debug("Monitoring not enabled for Ingress %s/%s", namespace, name)
        return

    logger.info("Processing Ingress %s/%s for monitoring", namespace, name)

    try:
        monitor_config = await _get_and_validate_monitor_config(
            annotations, spec, namespace, name
        )
        if not monitor_config:
            return

        if config.duplicate_handling == "annotation_priority":
            duplicate_name = await _check_duplicate_monitor(
                monitor_config["url"], namespace
            )
            if duplicate_name:
                await _handle_duplicate_conflict(
                    duplicate_name, namespace, monitor_config["url"]
                )

        existing_monitor_id = get_monitor_id_from_annotations(annotations)

        async with LunalyticsClient() as lunalytics_client:
            if existing_monitor_id:
                if await lunalytics_client.validate_monitor_exists(existing_monitor_id):
                    update_payload = MonitorUpdate(
                        monitor_id=existing_monitor_id,
                        **{k: v for k, v in monitor_config.items() if k != "url"},
                    )
                    await lunalytics_client.edit_monitor(update_payload)
                    logger.info(
                        "Updated monitor %s for Ingress %s/%s",
                        existing_monitor_id,
                        namespace,
                        name,
                    )
                else:
                    create_payload = MonitorCreate(**monitor_config)
                    monitor_response = await lunalytics_client.add_monitor(
                        create_payload
                    )
                    monitor_id_annotation = create_monitor_id_annotation(
                        monitor_response.monitor_id
                    )
                    update_resource_annotations(
                        networking_v1, namespace, "ingress", name, monitor_id_annotation
                    )
                    logger.info(
                        "Created new monitor %s for Ingress %s/%s",
                        monitor_response.monitor_id,
                        namespace,
                        name,
                    )
            else:
                create_payload = MonitorCreate(**monitor_config)
                monitor_response = await lunalytics_client.add_monitor(create_payload)
                monitor_id_annotation = create_monitor_id_annotation(
                    monitor_response.monitor_id
                )
                update_resource_annotations(
                    networking_v1, namespace, "ingress", name, monitor_id_annotation
                )
                logger.info(
                    "Created monitor %s for Ingress %s/%s",
                    monitor_response.monitor_id,
                    namespace,
                    name,
                )

    except LunalyticsAPIError as e:
        logger.error("Lunalytics API error for Ingress %s/%s: %s", namespace, name, e)
    except client.ApiException as e:
        logger.error("Kubernetes API error for Ingress %s/%s: %s", namespace, name, e)


@kopf.on.delete("networking.k8s.io", "v1", "ingresses")
async def handle_ingress_delete(meta: Dict[str, Any], namespace: str, name: str, **_):
    """Handle Ingress delete events."""
    annotations = meta.get("annotations", {})
    monitor_id = get_monitor_id_from_annotations(annotations)

    if not monitor_id:
        logger.debug("No monitor ID found for deleted Ingress %s/%s", namespace, name)
        return

    logger.info("Deleting monitor %s for Ingress %s/%s", monitor_id, namespace, name)

    try:
        async with LunalyticsClient() as lunalytics_client:
            await lunalytics_client.delete_monitor(monitor_id)
            logger.info(
                "Successfully deleted monitor %s for Ingress %s/%s",
                monitor_id,
                namespace,
                name,
            )

    except LunalyticsNotFoundError:
        logger.info("Monitor %s not found in Lunalytics (already deleted)", monitor_id)
    except LunalyticsAPIError as e:
        logger.error(
            "Error deleting monitor %s for Ingress %s/%s: %s",
            monitor_id,
            namespace,
            name,
            e,
        )
    except client.ApiException as e:
        logger.error(
            "Kubernetes API error deleting monitor for Ingress %s/%s: %s",
            namespace,
            name,
            e,
        )


@kopf.on.resume("networking.k8s.io", "v1", "ingresses")
async def handle_ingress_resume(meta: Dict[str, Any], namespace: str, name: str, **_):
    """Handle Ingress resume events (operator startup)."""
    annotations = meta.get("annotations", {})

    if not is_monitoring_enabled(annotations):
        return

    monitor_id = get_monitor_id_from_annotations(annotations)
    if not monitor_id:
        return

    logger.info(
        "Validating monitor %s for resumed Ingress %s/%s", monitor_id, namespace, name
    )

    try:
        async with LunalyticsClient() as lunalytics_client:
            if not await lunalytics_client.validate_monitor_exists(monitor_id):
                logger.warning(
                    "Monitor %s not found for resumed Ingress %s/%s, "
                    "will recreate on next update",
                    monitor_id,
                    namespace,
                    name,
                )
    except (LunalyticsAPIError, client.ApiException) as e:
        logger.error(
            "Error validating monitor %s for resumed Ingress %s/%s: %s",
            monitor_id,
            namespace,
            name,
            e,
        )
