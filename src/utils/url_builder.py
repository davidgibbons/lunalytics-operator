"""URL construction utilities for different Kubernetes resource types."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def build_ingress_url(ingress_spec: Dict[str, Any]) -> Optional[str]:
    """Build monitor URL from Ingress specification."""
    try:
        rules = ingress_spec.get("rules", [])
        if not rules:
            logger.warning("Ingress has no rules")
            return None

        first_rule = rules[0]
        host = first_rule.get("host")
        if not host:
            logger.warning("Ingress rule has no host")
            return None

        http_paths = first_rule.get("http", {}).get("paths", [])
        if not http_paths:
            logger.warning("Ingress rule has no HTTP paths")
            return None

        first_path = http_paths[0]
        path = first_path.get("path", "/")

        tls = ingress_spec.get("tls", [])
        protocol = "https" if tls else "http"

        url = f"{protocol}://{host}{path}"
        logger.debug("Built Ingress URL: %s", url)
        return url

    except (KeyError, IndexError) as e:
        logger.error("Error building Ingress URL: %s", e)
        return None


def build_service_url(
    service_spec: Dict[str, Any], service_name: str, namespace: str = "default"
) -> Optional[str]:
    """Build monitor URL from Service specification."""
    try:
        ports = service_spec.get("ports", [])
        if not ports:
            logger.warning("Service %s has no ports", service_name)
            return None

        first_port = ports[0]
        port = first_port.get("port")
        if not port:
            logger.warning("Service %s port has no port number", service_name)
            return None

        protocol = "http"
        port_name = first_port.get("name", "").lower()
        if "https" in port_name or "ssl" in port_name or "tls" in port_name:
            protocol = "https"
        elif first_port.get("protocol", "").lower() == "tcp":
            protocol = "http"  # Default for TCP

        url = f"{protocol}://{service_name}.{namespace}.svc.cluster.local:{port}/"
        logger.debug("Built Service URL: %s", url)
        return url

    except (KeyError, IndexError) as e:
        logger.error("Error building Service URL: %s", e)
        return None


def build_monitor_url(
    resource_spec: Dict[str, Any],
    resource_type: str,
    resource_name: str,
    namespace: str = "default",
    explicit_url: Optional[str] = None,
) -> Optional[str]:
    """Build monitor URL based on resource type and specification."""
    if explicit_url:
        logger.debug("Using explicit URL: %s", explicit_url)
        return explicit_url

    if resource_type.lower() == "ingress":
        return build_ingress_url(resource_spec)
    if resource_type.lower() == "service":
        return build_service_url(resource_spec, resource_name, namespace)

    logger.warning("Unsupported resource type for URL building: %s", resource_type)
    return None


def validate_url(url: str) -> bool:
    """Validate URL format."""
    try:
        if not url.startswith(("http://", "https://")):
            return False

        # Basic URL validation - could be enhanced with urllib.parse
        if len(url) < 8:  # Minimum: http://a
            return False

        return True

    except (AttributeError, TypeError):
        return False
