"""Main KOPF operator module for Lunalytics monitoring."""

import logging

import kopf

from .config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@kopf.on.startup()
async def startup(**_):
    """Handle operator startup."""
    logger.info("Lunalytics KOPF Operator starting up...")
    logger.info("Configuration loaded:")
    logger.info("  - Lunalytics API URL: %s", config.lunalytics_api_url)
    logger.info("  - Duplicate handling: %s", config.duplicate_handling)
    logger.info("  - Max retry attempts: %s", config.max_retry_attempts)
    logger.info("  - Retry backoff factor: %s", config.retry_backoff_factor)
    logger.info("  - Namespace filter: %s", config.namespace_filter)
    logger.info("  - Kubernetes config: %s", config.kubernetes_config)
    logger.info("  - Monitor defaults: %s", config.monitor_defaults)


@kopf.on.cleanup()
async def cleanup(**_):
    """Handle operator cleanup."""
    logger.info("Lunalytics KOPF Operator shutting down...")


@kopf.on.probe()
async def health_check(**_):
    """Health check endpoint."""
    return {
        "status": "healthy",
        "api_url": config.lunalytics_api_url,
        "duplicate_handling": config.duplicate_handling,
    }
