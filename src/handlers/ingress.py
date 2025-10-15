"""
KOPF handlers for Ingress resources.
"""

import logging
import kopf
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from kubernetes import client
from kubernetes.client.rest import ApiException

from ..lunalytics.client import LunalyticsClient
from ..lunalytics.models import MonitorCreate, MonitorUpdate
from ..lunalytics.exceptions import LunalyticsAPIError, LunalyticsNotFoundError
from ..utils.annotations import (
    is_monitoring_enabled,
    get_monitor_name,
    get_monitor_config_from_annotations,
    get_monitor_id_from_annotations,
    create_monitor_id_annotation,
    merge_with_defaults,
    validate_monitor_config,
    update_resource_annotations
)
from ..utils.url_builder import build_monitor_url
from ..config import config

logger = logging.getLogger(__name__)

# Kubernetes API clients
v1 = client.CoreV1Api()
networking_v1 = client.NetworkingV1Api()


async def _check_duplicate_monitor(url: str, namespace: str) -> Optional[str]:
    """
    Check if a Monitor CRD already exists for the same URL.
    
    Args:
        url: URL to check for duplicates
        namespace: Namespace to search in
        
    Returns:
        Monitor CRD name if duplicate found, None otherwise
    """
    try:
        # List Monitor CRDs in the namespace
        custom_api = client.CustomObjectsApi()
        monitors = custom_api.list_namespaced_custom_object(
            group="lunalytics.io",
            version="v1alpha1",
            namespace=namespace,
            plural="monitors"
        )
        
        for monitor in monitors.get('items', []):
            monitor_spec = monitor.get('spec', {})
            if monitor_spec.get('url') == url:
                return monitor.get('metadata', {}).get('name')
        
        return None
        
    except Exception as e:
        logger.warning(f"Error checking for duplicate monitors: {e}")
        return None


async def _handle_duplicate_conflict(duplicate_name: str, namespace: str, url: str) -> None:
    """
    Handle duplicate conflict by updating Monitor CRD status.
    
    Args:
        duplicate_name: Name of the duplicate Monitor CRD
        namespace: Namespace of the Monitor CRD
        url: URL that caused the conflict
    """
    try:
        custom_api = client.CustomObjectsApi()
        
        # Update Monitor CRD status to conflict
        patch_body = {
            "status": {
                "state": "conflict",
                "message": f"Conflict: Ingress annotation takes precedence for URL {url}",
                "lastSyncTime": datetime.utcnow().isoformat() + "Z"
            }
        }
        
        custom_api.patch_namespaced_custom_object_status(
            group="lunalytics.io",
            version="v1alpha1",
            namespace=namespace,
            plural="monitors",
            name=duplicate_name,
            body=patch_body
        )
        
        logger.info(f"Updated Monitor CRD {duplicate_name} to conflict state due to annotation precedence")
        
    except Exception as e:
        logger.error(f"Error updating Monitor CRD conflict status: {e}")


@kopf.on.create('networking.k8s.io', 'v1', 'ingresses')
@kopf.on.update('networking.k8s.io', 'v1', 'ingresses')
async def handle_ingress_create_or_update(
    spec: Dict[str, Any],
    meta: Dict[str, Any],
    namespace: str,
    name: str,
    status: Dict[str, Any],
    **kwargs
):
    """Handle Ingress create or update events."""
    
    annotations = meta.get('annotations', {})
    
    # Check if namespace is monitored
    if not config.is_namespace_monitored(namespace):
        logger.debug(f"Namespace {namespace} not monitored for Ingress {name}")
        return
    
    # Check if monitoring is enabled
    if not is_monitoring_enabled(annotations):
        logger.debug(f"Monitoring not enabled for Ingress {namespace}/{name}")
        return
    
    logger.info(f"Processing Ingress {namespace}/{name} for monitoring")
    
    try:
        # Get monitor configuration from annotations
        annotation_config = get_monitor_config_from_annotations(annotations)
        
        # Build URL from Ingress spec
        url = build_monitor_url(
            resource_spec=spec,
            resource_type='ingress',
            resource_name=name,
            namespace=namespace,
            explicit_url=annotation_config.get('url')
        )
        
        if not url:
            logger.error(f"Could not build URL for Ingress {namespace}/{name}")
            return
        
        # Add name to config
        monitor_name = get_monitor_name(annotations, name, 'Ingress')
        annotation_config['name'] = monitor_name
        annotation_config['url'] = url
        
        # Merge with defaults
        monitor_config = merge_with_defaults(annotation_config)
        
        # Validate configuration
        validation_errors = validate_monitor_config(monitor_config)
        if validation_errors:
            logger.error(f"Invalid monitor configuration for Ingress {namespace}/{name}: {validation_errors}")
            return
        
        # Check for duplicates if configured
        if config.duplicate_handling == 'annotation_priority':
            duplicate_name = await _check_duplicate_monitor(url, namespace)
            if duplicate_name:
                await _handle_duplicate_conflict(duplicate_name, namespace, url)
        
        # Get existing monitor ID
        existing_monitor_id = get_monitor_id_from_annotations(annotations)
        
        # Create or update monitor in Lunalytics
        async with LunalyticsClient() as lunalytics_client:
            if existing_monitor_id:
                # Check if monitor still exists
                if await lunalytics_client.validate_monitor_exists(existing_monitor_id):
                    # Update existing monitor
                    update_payload = MonitorUpdate(
                        monitor_id=existing_monitor_id,
                        **{k: v for k, v in monitor_config.items() if k != 'url'}
                    )
                    monitor_response = await lunalytics_client.edit_monitor(update_payload)
                    logger.info(f"Updated monitor {existing_monitor_id} for Ingress {namespace}/{name}")
                else:
                    # Monitor doesn't exist, create new one
                    create_payload = MonitorCreate(**monitor_config)
                    monitor_response = await lunalytics_client.add_monitor(create_payload)
                    # Update annotation with new monitor ID
                    monitor_id_annotation = create_monitor_id_annotation(monitor_response.monitor_id)
                    update_resource_annotations(
                        networking_v1, namespace, 'ingress', name, monitor_id_annotation
                    )
                    logger.info(f"Created new monitor {monitor_response.monitor_id} for Ingress {namespace}/{name}")
            else:
                # Create new monitor
                create_payload = MonitorCreate(**monitor_config)
                monitor_response = await lunalytics_client.add_monitor(create_payload)
                # Update annotation with monitor ID
                monitor_id_annotation = create_monitor_id_annotation(monitor_response.monitor_id)
                update_resource_annotations(
                    networking_v1, namespace, 'ingress', name, monitor_id_annotation
                )
                logger.info(f"Created monitor {monitor_response.monitor_id} for Ingress {namespace}/{name}")
    
    except LunalyticsAPIError as e:
        logger.error(f"Lunalytics API error for Ingress {namespace}/{name}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error processing Ingress {namespace}/{name}: {e}")


@kopf.on.delete('networking.k8s.io', 'v1', 'ingresses')
async def handle_ingress_delete(
    spec: Dict[str, Any],
    meta: Dict[str, Any],
    namespace: str,
    name: str,
    **kwargs
):
    """Handle Ingress delete events."""
    
    annotations = meta.get('annotations', {})
    monitor_id = get_monitor_id_from_annotations(annotations)
    
    if not monitor_id:
        logger.debug(f"No monitor ID found for deleted Ingress {namespace}/{name}")
        return
    
    logger.info(f"Deleting monitor {monitor_id} for Ingress {namespace}/{name}")
    
    try:
        async with LunalyticsClient() as lunalytics_client:
            await lunalytics_client.delete_monitor(monitor_id)
            logger.info(f"Successfully deleted monitor {monitor_id} for Ingress {namespace}/{name}")
    
    except LunalyticsNotFoundError:
        logger.info(f"Monitor {monitor_id} not found in Lunalytics (already deleted)")
    except LunalyticsAPIError as e:
        logger.error(f"Error deleting monitor {monitor_id} for Ingress {namespace}/{name}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error deleting monitor for Ingress {namespace}/{name}: {e}")


@kopf.on.resume('networking.k8s.io', 'v1', 'ingresses')
async def handle_ingress_resume(
    spec: Dict[str, Any],
    meta: Dict[str, Any],
    namespace: str,
    name: str,
    **kwargs
):
    """Handle Ingress resume events (operator startup)."""
    
    annotations = meta.get('annotations', {})
    
    # Only process if monitoring is enabled and monitor ID exists
    if not is_monitoring_enabled(annotations):
        return
    
    monitor_id = get_monitor_id_from_annotations(annotations)
    if not monitor_id:
        return
    
    logger.info(f"Validating monitor {monitor_id} for resumed Ingress {namespace}/{name}")
    
    try:
        async with LunalyticsClient() as lunalytics_client:
            # Validate monitor still exists
            if not await lunalytics_client.validate_monitor_exists(monitor_id):
                logger.warning(f"Monitor {monitor_id} not found for resumed Ingress {namespace}/{name}, will recreate on next update")
    
    except Exception as e:
        logger.error(f"Error validating monitor {monitor_id} for resumed Ingress {namespace}/{name}: {e}")
