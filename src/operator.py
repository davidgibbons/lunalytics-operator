"""
Main KOPF operator module for Lunalytics monitoring.
"""

import logging
import kopf
import asyncio
from typing import Dict, Any

from .config import config
from .handlers import ingress, service, monitor_crd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@kopf.on.startup()
async def startup(**kwargs):
    """Handle operator startup."""
    logger.info("Lunalytics KOPF Operator starting up...")
    logger.info(f"Configuration loaded:")
    logger.info(f"  - Lunalytics API URL: {config.lunalytics_api_url}")
    logger.info(f"  - Duplicate handling: {config.duplicate_handling}")
    logger.info(f"  - Max retry attempts: {config.max_retry_attempts}")
    logger.info(f"  - Retry backoff factor: {config.retry_backoff_factor}")
    logger.info(f"  - Namespace filter: {config.namespace_filter}")
    logger.info(f"  - Kubernetes config: {config.kubernetes_config}")
    logger.info(f"  - Monitor defaults: {config.monitor_defaults}")


@kopf.on.cleanup()
async def cleanup(**kwargs):
    """Handle operator cleanup."""
    logger.info("Lunalytics KOPF Operator shutting down...")


@kopf.on.probe()
async def health_check(**kwargs):
    """Health check endpoint."""
    return {
        'status': 'healthy',
        'api_url': config.lunalytics_api_url,
        'duplicate_handling': config.duplicate_handling
    }


if __name__ == '__main__':
    # Run the operator
    kopf.run()
