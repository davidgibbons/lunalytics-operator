"""
URL construction utilities for different Kubernetes resource types.
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def build_ingress_url(ingress_spec: Dict[str, Any], namespace: str = 'default') -> Optional[str]:
    """
    Build monitor URL from Ingress specification.
    
    Args:
        ingress_spec: Ingress spec dictionary
        namespace: Namespace of the ingress
        
    Returns:
        Constructed URL or None if cannot be built
    """
    try:
        rules = ingress_spec.get('rules', [])
        if not rules:
            logger.warning("Ingress has no rules")
            return None
        
        # Get first rule
        first_rule = rules[0]
        host = first_rule.get('host')
        if not host:
            logger.warning("Ingress rule has no host")
            return None
        
        # Get first path
        http_paths = first_rule.get('http', {}).get('paths', [])
        if not http_paths:
            logger.warning("Ingress rule has no HTTP paths")
            return None
        
        first_path = http_paths[0]
        path = first_path.get('path', '/')
        
        # Determine protocol (default to https)
        tls = ingress_spec.get('tls', [])
        protocol = 'https' if tls else 'http'
        
        # Build URL
        url = f"{protocol}://{host}{path}"
        logger.debug(f"Built Ingress URL: {url}")
        return url
        
    except Exception as e:
        logger.error(f"Error building Ingress URL: {e}")
        return None


def build_service_url(
    service_spec: Dict[str, Any],
    service_name: str,
    namespace: str = 'default'
) -> Optional[str]:
    """
    Build monitor URL from Service specification.
    
    Args:
        service_spec: Service spec dictionary
        service_name: Name of the service
        namespace: Namespace of the service
        
    Returns:
        Constructed URL or None if cannot be built
    """
    try:
        ports = service_spec.get('ports', [])
        if not ports:
            logger.warning(f"Service {service_name} has no ports")
            return None
        
        # Get first port
        first_port = ports[0]
        port = first_port.get('port')
        if not port:
            logger.warning(f"Service {service_name} port has no port number")
            return None
        
        # Determine protocol
        protocol = 'http'
        port_name = first_port.get('name', '').lower()
        if 'https' in port_name or 'ssl' in port_name or 'tls' in port_name:
            protocol = 'https'
        elif first_port.get('protocol', '').lower() == 'tcp':
            protocol = 'http'  # Default for TCP
        
        # Build internal cluster URL
        url = f"{protocol}://{service_name}.{namespace}.svc.cluster.local:{port}/"
        logger.debug(f"Built Service URL: {url}")
        return url
        
    except Exception as e:
        logger.error(f"Error building Service URL: {e}")
        return None


def build_monitor_url(
    resource_spec: Dict[str, Any],
    resource_type: str,
    resource_name: str,
    namespace: str = 'default',
    explicit_url: Optional[str] = None
) -> Optional[str]:
    """
    Build monitor URL based on resource type and specification.
    
    Args:
        resource_spec: Resource specification dictionary
        resource_type: Type of resource (ingress, service)
        resource_name: Name of the resource
        namespace: Namespace of the resource
        explicit_url: Explicit URL override from annotations
        
    Returns:
        Constructed URL or None if cannot be built
    """
    # Use explicit URL if provided
    if explicit_url:
        logger.debug(f"Using explicit URL: {explicit_url}")
        return explicit_url
    
    # Build URL based on resource type
    if resource_type.lower() == 'ingress':
        return build_ingress_url(resource_spec, namespace)
    elif resource_type.lower() == 'service':
        return build_service_url(resource_spec, resource_name, namespace)
    else:
        logger.warning(f"Unsupported resource type for URL building: {resource_type}")
        return None


def validate_url(url: str) -> bool:
    """
    Validate URL format.
    
    Args:
        url: URL to validate
        
    Returns:
        True if URL is valid
    """
    try:
        if not url.startswith(('http://', 'https://')):
            return False
        
        # Basic URL validation - could be enhanced with urllib.parse
        if len(url) < 8:  # Minimum: http://a
            return False
        
        return True
        
    except Exception:
        return False
