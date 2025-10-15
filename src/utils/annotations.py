"""
Annotation parsing utilities for Lunalytics monitoring.
"""

import logging
from typing import Dict, Any, Optional, List
from kubernetes.client.rest import ApiException

from ..config import config

logger = logging.getLogger(__name__)

# Annotation prefix for Lunalytics
ANNOTATION_PREFIX = 'lunalytics.io/'

# Annotation keys
ANNOTATION_ENABLED = f'{ANNOTATION_PREFIX}enabled'
ANNOTATION_NAME = f'{ANNOTATION_PREFIX}name'
ANNOTATION_URL = f'{ANNOTATION_PREFIX}url'
ANNOTATION_INTERVAL = f'{ANNOTATION_PREFIX}interval'
ANNOTATION_RETRY_INTERVAL = f'{ANNOTATION_PREFIX}retry-interval'
ANNOTATION_REQUEST_TIMEOUT = f'{ANNOTATION_PREFIX}request-timeout'
ANNOTATION_METHOD = f'{ANNOTATION_PREFIX}method'
ANNOTATION_VALID_STATUS_CODES = f'{ANNOTATION_PREFIX}valid-status-codes'
ANNOTATION_MONITOR_ID = f'{ANNOTATION_PREFIX}monitor-id'


def is_monitoring_enabled(annotations: Dict[str, str]) -> bool:
    """
    Check if Lunalytics monitoring is enabled for a resource.
    
    Args:
        annotations: Resource annotations dictionary
        
    Returns:
        True if monitoring is enabled
    """
    return annotations.get(ANNOTATION_ENABLED, '').lower() == 'true'


def get_monitor_name(annotations: Dict[str, str], resource_name: str, resource_kind: str) -> str:
    """
    Get monitor name from annotations or generate default.
    
    Args:
        annotations: Resource annotations dictionary
        resource_name: Name of the Kubernetes resource
        resource_kind: Kind of the Kubernetes resource
        
    Returns:
        Monitor name
    """
    name = annotations.get(ANNOTATION_NAME)
    if name:
        return name
    
    # Generate default name
    return f"{resource_kind}/{resource_name}"


def get_monitor_config_from_annotations(annotations: Dict[str, str]) -> Dict[str, Any]:
    """
    Extract monitor configuration from annotations.
    
    Args:
        annotations: Resource annotations dictionary
        
    Returns:
        Monitor configuration dictionary
    """
    config_dict = {}
    
    # Get URL if explicitly provided
    if url := annotations.get(ANNOTATION_URL):
        config_dict['url'] = url
    
    # Get interval
    if interval := annotations.get(ANNOTATION_INTERVAL):
        try:
            config_dict['interval'] = int(interval)
        except ValueError:
            logger.warning(f"Invalid interval value: {interval}")
    
    # Get retry interval
    if retry_interval := annotations.get(ANNOTATION_RETRY_INTERVAL):
        try:
            config_dict['retry_interval'] = int(retry_interval)
        except ValueError:
            logger.warning(f"Invalid retry interval value: {retry_interval}")
    
    # Get request timeout
    if request_timeout := annotations.get(ANNOTATION_REQUEST_TIMEOUT):
        try:
            config_dict['request_timeout'] = int(request_timeout)
        except ValueError:
            logger.warning(f"Invalid request timeout value: {request_timeout}")
    
    # Get method
    if method := annotations.get(ANNOTATION_METHOD):
        config_dict['method'] = method.upper()
    
    # Get valid status codes
    if status_codes := annotations.get(ANNOTATION_VALID_STATUS_CODES):
        codes = [code.strip() for code in status_codes.split(',')]
        config_dict['valid_status_codes'] = codes
    
    return config_dict


def get_monitor_id_from_annotations(annotations: Dict[str, str]) -> Optional[str]:
    """
    Get stored monitor ID from annotations.
    
    Args:
        annotations: Resource annotations dictionary
        
    Returns:
        Monitor ID if present, None otherwise
    """
    return annotations.get(ANNOTATION_MONITOR_ID)


def create_monitor_id_annotation(monitor_id: str) -> Dict[str, str]:
    """
    Create annotation for storing monitor ID.
    
    Args:
        monitor_id: Monitor ID to store
        
    Returns:
        Annotation dictionary
    """
    return {ANNOTATION_MONITOR_ID: monitor_id}


def merge_with_defaults(annotation_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge annotation configuration with defaults.
    
    Args:
        annotation_config: Configuration from annotations
        
    Returns:
        Merged configuration with defaults
    """
    # Start with defaults
    merged = config.monitor_defaults.copy()
    
    # Override with annotation values
    merged.update(annotation_config)
    
    return merged


def validate_monitor_config(config_dict: Dict[str, Any]) -> List[str]:
    """
    Validate monitor configuration and return list of errors.
    
    Args:
        config_dict: Monitor configuration dictionary
        
    Returns:
        List of validation error messages
    """
    errors = []
    
    # Check required fields
    if not config_dict.get('url'):
        errors.append("URL is required")
    
    if not config_dict.get('name'):
        errors.append("Name is required")
    
    # Validate numeric fields
    for field in ['interval', 'retry_interval', 'request_timeout']:
        value = config_dict.get(field)
        if value is not None and (not isinstance(value, int) or value < 1):
            errors.append(f"{field} must be a positive integer")
    
    # Validate method
    method = config_dict.get('method', '').upper()
    valid_methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
    if method and method not in valid_methods:
        errors.append(f"method must be one of: {', '.join(valid_methods)}")
    
    # Validate status codes
    status_codes = config_dict.get('valid_status_codes', [])
    if status_codes:
        import re
        for code in status_codes:
            if not re.match(r'^\d{3}(-\d{3})?$', code):
                errors.append(f"Invalid status code format: {code}")
    
    return errors


def update_resource_annotations(
    api_instance,
    namespace: str,
    resource_type: str,
    name: str,
    annotations: Dict[str, str]
) -> bool:
    """
    Update resource annotations.
    
    Args:
        api_instance: Kubernetes API client instance
        namespace: Resource namespace
        resource_type: Type of resource (ingress, service, etc.)
        name: Resource name
        annotations: Annotations to add/update
        
    Returns:
        True if update was successful
    """
    try:
        if resource_type.lower() == 'ingress':
            # Get current resource
            resource = api_instance.read_namespaced_ingress(name, namespace)
            # Update annotations
            if not resource.metadata.annotations:
                resource.metadata.annotations = {}
            resource.metadata.annotations.update(annotations)
            # Apply update
            api_instance.patch_namespaced_ingress(name, namespace, resource)
            
        elif resource_type.lower() == 'service':
            # Get current resource
            resource = api_instance.read_namespaced_service(name, namespace)
            # Update annotations
            if not resource.metadata.annotations:
                resource.metadata.annotations = {}
            resource.metadata.annotations.update(annotations)
            # Apply update
            api_instance.patch_namespaced_service(name, namespace, resource)
        
        logger.info(f"Updated annotations for {resource_type}/{name}: {list(annotations.keys())}")
        return True
        
    except ApiException as e:
        logger.error(f"Failed to update annotations for {resource_type}/{name}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error updating annotations for {resource_type}/{name}: {e}")
        return False
