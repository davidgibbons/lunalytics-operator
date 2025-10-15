"""
KOPF handlers for Monitor CRD resources.
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
from ..config import config

logger = logging.getLogger(__name__)

# Kubernetes API clients
v1 = client.CoreV1Api()
networking_v1 = client.NetworkingV1Api()
custom_api = client.CustomObjectsApi()


async def _check_duplicate_annotations(url: str, namespace: str) -> Optional[Dict[str, str]]:
    """
    Check if Ingress or Service annotations already exist for the same URL.
    
    Args:
        url: URL to check for duplicates
        namespace: Namespace to search in
        
    Returns:
        Dict with resource info if duplicate found, None otherwise
    """
    try:
        # Check Ingress resources
        try:
            ingresses = networking_v1.list_namespaced_ingress(namespace)
            for ingress in ingresses.items:
                annotations = ingress.metadata.annotations or {}
                if (annotations.get('lunalytics.io/enabled', '').lower() == 'true' and
                    annotations.get('lunalytics.io/url') == url):
                    return {
                        'type': 'ingress',
                        'name': ingress.metadata.name,
                        'namespace': namespace
                    }
        except ApiException:
            pass
        
        # Check Service resources
        try:
            services = v1.list_namespaced_service(namespace)
            for service in services.items:
                annotations = service.metadata.annotations or {}
                if (annotations.get('lunalytics.io/enabled', '').lower() == 'true' and
                    annotations.get('lunalytics.io/url') == url):
                    return {
                        'type': 'service',
                        'name': service.metadata.name,
                        'namespace': namespace
                    }
        except ApiException:
            pass
        
        return None
        
    except Exception as e:
        logger.warning(f"Error checking for duplicate annotations: {e}")
        return None


async def _update_monitor_status(
    namespace: str,
    name: str,
    state: str,
    message: str = "",
    monitor_id: str = None,
    uptime_percentage: float = None,
    average_latency: float = None
) -> None:
    """
    Update Monitor CRD status.
    
    Args:
        namespace: Namespace of the Monitor CRD
        name: Name of the Monitor CRD
        state: New state
        message: Status message
        monitor_id: Monitor ID from Lunalytics
        uptime_percentage: Uptime percentage from Lunalytics
        average_latency: Average latency from Lunalytics
    """
    try:
        status_body = {
            "status": {
                "state": state,
                "message": message,
                "lastSyncTime": datetime.utcnow().isoformat() + "Z"
            }
        }
        
        if monitor_id:
            status_body["status"]["monitorId"] = monitor_id
        
        if uptime_percentage is not None:
            status_body["status"]["uptimePercentage"] = uptime_percentage
        
        if average_latency is not None:
            status_body["status"]["averageLatency"] = average_latency
        
        custom_api.patch_namespaced_custom_object_status(
            group="lunalytics.io",
            version="v1alpha1",
            namespace=namespace,
            plural="monitors",
            name=name,
            body=status_body
        )
        
        logger.info(f"Updated Monitor CRD {namespace}/{name} status to {state}")
        
    except Exception as e:
        logger.error(f"Error updating Monitor CRD status: {e}")


@kopf.on.create('lunalytics.io', 'v1alpha1', 'monitors')
@kopf.on.update('lunalytics.io', 'v1alpha1', 'monitors')
async def handle_monitor_create_or_update(
    spec: Dict[str, Any],
    meta: Dict[str, Any],
    namespace: str,
    name: str,
    status: Dict[str, Any],
    **kwargs
):
    """Handle Monitor CRD create or update events."""
    
    # Check if namespace is monitored
    if not config.is_namespace_monitored(namespace):
        logger.debug(f"Namespace {namespace} not monitored for Monitor CRD {name}")
        return
    
    logger.info(f"Processing Monitor CRD {namespace}/{name}")
    
    try:
        # Validate required fields
        if not spec.get('name'):
            await _update_monitor_status(namespace, name, 'error', 'Missing required field: name')
            return
        
        if not spec.get('url'):
            await _update_monitor_status(namespace, name, 'error', 'Missing required field: url')
            return
        
        url = spec['url']
        
        # Check for duplicates based on configuration
        duplicate_handling = config.duplicate_handling
        
        if duplicate_handling == 'annotation_priority':
            duplicate_info = await _check_duplicate_annotations(url, namespace)
            if duplicate_info:
                await _update_monitor_status(
                    namespace, name, 'conflict',
                    f"Conflict: {duplicate_info['type'].title()} annotation takes precedence for URL {url}"
                )
                return
        
        # Prepare monitor configuration
        monitor_config = {
            'name': spec['name'],
            'url': url,
            'type': spec.get('type', 'http'),
            'method': spec.get('method', 'GET'),
            'interval': spec.get('interval', 30),
            'retry_interval': spec.get('retryInterval', 30),
            'request_timeout': spec.get('requestTimeout', 30),
            'valid_status_codes': spec.get('validStatusCodes', ['200-299'])
        }
        
        # Get existing monitor ID from status
        existing_monitor_id = status.get('monitorId')
        
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
                    await _update_monitor_status(
                        namespace, name, 'active', 'Monitor updated successfully',
                        monitor_id=monitor_response.monitor_id,
                        uptime_percentage=monitor_response.uptime_percentage,
                        average_latency=monitor_response.average_heartbeat_latency
                    )
                    logger.info(f"Updated monitor {existing_monitor_id} for Monitor CRD {namespace}/{name}")
                else:
                    # Monitor doesn't exist, create new one
                    create_payload = MonitorCreate(**monitor_config)
                    monitor_response = await lunalytics_client.add_monitor(create_payload)
                    await _update_monitor_status(
                        namespace, name, 'active', 'Monitor created successfully',
                        monitor_id=monitor_response.monitor_id,
                        uptime_percentage=monitor_response.uptime_percentage,
                        average_latency=monitor_response.average_heartbeat_latency
                    )
                    logger.info(f"Created new monitor {monitor_response.monitor_id} for Monitor CRD {namespace}/{name}")
            else:
                # Create new monitor
                create_payload = MonitorCreate(**monitor_config)
                monitor_response = await lunalytics_client.add_monitor(create_payload)
                await _update_monitor_status(
                    namespace, name, 'active', 'Monitor created successfully',
                    monitor_id=monitor_response.monitor_id,
                    uptime_percentage=monitor_response.uptime_percentage,
                    average_latency=monitor_response.average_heartbeat_latency
                )
                logger.info(f"Created monitor {monitor_response.monitor_id} for Monitor CRD {namespace}/{name}")
    
    except LunalyticsAPIError as e:
        await _update_monitor_status(namespace, name, 'error', f'Lunalytics API error: {str(e)}')
        logger.error(f"Lunalytics API error for Monitor CRD {namespace}/{name}: {e}")
    except Exception as e:
        await _update_monitor_status(namespace, name, 'error', f'Unexpected error: {str(e)}')
        logger.error(f"Unexpected error processing Monitor CRD {namespace}/{name}: {e}")


@kopf.on.delete('lunalytics.io', 'v1alpha1', 'monitors')
async def handle_monitor_delete(
    spec: Dict[str, Any],
    meta: Dict[str, Any],
    namespace: str,
    name: str,
    status: Dict[str, Any],
    **kwargs
):
    """Handle Monitor CRD delete events."""
    
    monitor_id = status.get('monitorId')
    
    if not monitor_id:
        logger.debug(f"No monitor ID found for deleted Monitor CRD {namespace}/{name}")
        return
    
    logger.info(f"Deleting monitor {monitor_id} for Monitor CRD {namespace}/{name}")
    
    try:
        async with LunalyticsClient() as lunalytics_client:
            await lunalytics_client.delete_monitor(monitor_id)
            logger.info(f"Successfully deleted monitor {monitor_id} for Monitor CRD {namespace}/{name}")
    
    except LunalyticsNotFoundError:
        logger.info(f"Monitor {monitor_id} not found in Lunalytics (already deleted)")
    except LunalyticsAPIError as e:
        logger.error(f"Error deleting monitor {monitor_id} for Monitor CRD {namespace}/{name}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error deleting monitor for Monitor CRD {namespace}/{name}: {e}")


@kopf.on.resume('lunalytics.io', 'v1alpha1', 'monitors')
async def handle_monitor_resume(
    spec: Dict[str, Any],
    meta: Dict[str, Any],
    namespace: str,
    name: str,
    status: Dict[str, Any],
    **kwargs
):
    """Handle Monitor CRD resume events (operator startup)."""
    
    monitor_id = status.get('monitorId')
    if not monitor_id:
        return
    
    logger.info(f"Validating monitor {monitor_id} for resumed Monitor CRD {namespace}/{name}")
    
    try:
        async with LunalyticsClient() as lunalytics_client:
            # Validate monitor still exists and get current status
            try:
                monitor_response = await lunalytics_client.get_monitor(monitor_id)
                await _update_monitor_status(
                    namespace, name, 'active', 'Monitor validated successfully',
                    monitor_id=monitor_response.monitor_id,
                    uptime_percentage=monitor_response.uptime_percentage,
                    average_latency=monitor_response.average_heartbeat_latency
                )
                logger.info(f"Monitor {monitor_id} validated for resumed Monitor CRD {namespace}/{name}")
            except LunalyticsNotFoundError:
                await _update_monitor_status(
                    namespace, name, 'error', 'Monitor not found in Lunalytics'
                )
                logger.warning(f"Monitor {monitor_id} not found for resumed Monitor CRD {namespace}/{name}")
    
    except Exception as e:
        await _update_monitor_status(
            namespace, name, 'error', f'Error validating monitor: {str(e)}'
        )
        logger.error(f"Error validating monitor {monitor_id} for resumed Monitor CRD {namespace}/{name}: {e}")
