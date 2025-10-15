"""Configuration management for Lunalytics KOPF Operator."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class Config:
    """Configuration manager for the Lunalytics operator."""

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or os.getenv(
            "LUNALYTICS_CONFIG_FILE", "/app/config/defaults.yaml"
        )
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file and environment variables."""
        defaults = self._load_yaml_config()
        env_config = self._load_env_config()
        self._config = {**defaults, **env_config}

    def _load_yaml_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            config_path = Path(self.config_file)
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        except (IOError, yaml.YAMLError) as e:
            print(f"Warning: Could not load config file {self.config_file}: {e}")
        return {}

    def _load_env_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        env_config = {}

        # Lunalytics API configuration
        if api_url := os.getenv("LUNALYTICS_API_URL"):
            env_config.setdefault("lunalytics", {})["api_url"] = api_url
        if api_token := os.getenv("LUNALYTICS_API_TOKEN"):
            env_config.setdefault("lunalytics", {})["api_token"] = api_token

        # Retry configuration
        self._load_retry_config(env_config)

        # Duplicate handling
        if duplicate_handling := os.getenv("DUPLICATE_HANDLING"):
            env_config["duplicate_handling"] = duplicate_handling

        # Monitor defaults
        self._load_monitor_defaults(env_config)

        # Kubernetes API configuration
        self._load_k8s_config(env_config)

        # Namespace filtering
        self._load_namespace_filter(env_config)

        return env_config

    def _load_retry_config(self, env_config: Dict[str, Any]) -> None:
        """Load retry configuration from environment variables."""
        if max_attempts := os.getenv("MAX_RETRY_ATTEMPTS"):
            try:
                env_config.setdefault("retry", {})["max_attempts"] = int(max_attempts)
            except ValueError:
                pass
        if backoff_factor := os.getenv("RETRY_BACKOFF_FACTOR"):
            try:
                env_config.setdefault("retry", {})["backoff_factor"] = float(
                    backoff_factor
                )
            except ValueError:
                pass
        if max_delay := os.getenv("RETRY_MAX_DELAY"):
            try:
                env_config.setdefault("retry", {})["max_delay"] = int(max_delay)
            except ValueError:
                pass

    def _load_monitor_defaults(self, env_config: Dict[str, Any]) -> None:
        """Load monitor defaults from environment variables."""
        monitor_defaults = {}
        for key in ["type", "method", "interval", "retry_interval", "request_timeout"]:
            if value := os.getenv(f"MONITOR_DEFAULT_{key.upper()}"):
                monitor_defaults[key] = value

        if status_codes := os.getenv("MONITOR_DEFAULT_VALID_STATUS_CODES"):
            monitor_defaults["valid_status_codes"] = [
                code.strip() for code in status_codes.split(",")
            ]

        if monitor_defaults:
            env_config.setdefault("monitor_defaults", {}).update(monitor_defaults)

    def _load_k8s_config(self, env_config: Dict[str, Any]) -> None:
        """Load Kubernetes API configuration from environment variables."""
        k8s_config = {}
        if in_cluster := os.getenv("KUBERNETES_IN_CLUSTER"):
            k8s_config["in_cluster"] = in_cluster.lower() in (
                "true",
                "1",
                "yes",
                "on",
            )
        if config_file := os.getenv("KUBECONFIG"):
            k8s_config["config_file"] = config_file
        if context := os.getenv("KUBERNETES_CONTEXT"):
            k8s_config["context"] = context
        if k8s_config:
            env_config["kubernetes"] = k8s_config

    def _load_namespace_filter(self, env_config: Dict[str, Any]) -> None:
        """Load namespace filtering configuration from environment variables."""
        namespace_filter = {}
        if strategy := os.getenv("NAMESPACE_FILTER_STRATEGY"):
            namespace_filter["strategy"] = strategy
        if namespaces := os.getenv("NAMESPACE_FILTER_NAMESPACES"):
            namespace_filter["namespaces"] = [
                ns.strip() for ns in namespaces.split(",") if ns.strip()
            ]
        if annotation_key := os.getenv("NAMESPACE_FILTER_ANNOTATION_KEY"):
            namespace_filter["annotation_key"] = annotation_key
        if annotation_value := os.getenv("NAMESPACE_FILTER_ANNOTATION_VALUE"):
            namespace_filter["annotation_value"] = annotation_value
        if namespace_filter:
            env_config["namespace_filter"] = namespace_filter

    @property
    def lunalytics_api_url(self) -> str:
        """Get Lunalytics API URL."""
        return self._config.get("lunalytics", {}).get(
            "api_url", "https://lunalytics.xyz"
        )

    @property
    def lunalytics_api_token(self) -> str:
        """Get Lunalytics API token."""
        token = self._config.get("lunalytics", {}).get("api_token")
        if not token:
            raise ValueError("LUNALYTICS_API_TOKEN environment variable is required")
        return token

    @property
    def duplicate_handling(self) -> str:
        """Get duplicate handling strategy."""
        return self._config.get("duplicate_handling", "annotation_priority")

    @property
    def max_retry_attempts(self) -> int:
        """Get maximum retry attempts (-1 for infinite)."""
        return self._config.get("retry", {}).get("max_attempts", 3)

    @property
    def retry_backoff_factor(self) -> float:
        """Get retry backoff factor."""
        return self._config.get("retry", {}).get("backoff_factor", 2.0)

    @property
    def retry_max_delay(self) -> int:
        """Get maximum retry delay in seconds."""
        return self._config.get("retry", {}).get("max_delay", 300)

    @property
    def monitor_defaults(self) -> Dict[str, Any]:
        """Get default monitor configuration."""
        return self._config.get(
            "monitor_defaults",
            {
                "type": "http",
                "method": "GET",
                "interval": 30,
                "retry_interval": 30,
                "request_timeout": 30,
                "valid_status_codes": ["200-299"],
            },
        )

    def get_monitor_default(self, key: str, default: Any = None) -> Any:
        """Get a specific monitor default value."""
        return self.monitor_defaults.get(key, default)

    @property
    def kubernetes_config(self) -> Dict[str, Any]:
        """Get Kubernetes API configuration."""
        return self._config.get("kubernetes", {})

    @property
    def namespace_filter(self) -> Dict[str, Any]:
        """Get namespace filtering configuration."""
        return self._config.get(
            "namespace_filter",
            {
                "strategy": "all",
                "namespaces": [],
                "annotation_key": "lunalytics.io/enabled",
                "annotation_value": "true",
            },
        )

    def is_namespace_monitored(
        self, namespace: str, namespace_annotations: Optional[Dict[str, str]] = None
    ) -> bool:
        """Check if a namespace should be monitored based on filtering configuration."""
        filter_config = self.namespace_filter
        strategy = filter_config.get("strategy", "all")

        if strategy == "all":
            return True
        if strategy == "list":
            allowed_namespaces = filter_config.get("namespaces", [])
            return namespace in allowed_namespaces
        if strategy == "annotation":
            if not namespace_annotations:
                return False
            annotation_key = filter_config.get(
                "annotation_key", "lunalytics.io/enabled"
            )
            annotation_value = filter_config.get("annotation_value", "true")
            return namespace_annotations.get(annotation_key) == annotation_value

        return False

    def reload(self) -> None:
        """Reload configuration from files and environment."""
        self._load_config()


# Global config instance
config = Config()
