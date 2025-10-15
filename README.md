# Lunalytics KOPF Operator

A Kubernetes operator built with KOPF that automatically creates, updates, and deletes monitors in Lunalytics based on Ingress and Service annotations or custom Monitor resources.

## Features

- **Annotation-based monitoring**: Add monitoring to existing Ingress and Service resources via annotations
- **Custom Resource Definitions**: Create dedicated Monitor CRDs for more complex monitoring configurations
- **Automatic URL construction**: Intelligently builds monitor URLs from Kubernetes resource specifications
- **Duplicate detection**: Configurable conflict resolution between annotations and CRDs
- **Retry logic**: Robust retry mechanism with exponential backoff for API calls
- **State validation**: Periodic validation of monitor state with automatic recovery
- **Comprehensive configuration**: Environment variables and YAML configuration support

## Installation

### Prerequisites

- Kubernetes cluster (1.19+)
- Lunalytics API token
- kubectl configured to access your cluster
- Helm 3.x (for Helm installation method)

### Installation Methods

#### Method 1: Helm (Recommended)

1. **Create the namespace**:
   ```bash
   kubectl create namespace lunalytics-system
   ```

2. **Add the Helm repository** (when published):
   ```bash
   helm repo add lunalytics-operator https://davidgibbons.github.io/lunalytics_operator
   helm repo update
   ```

3. **Install with Helm**:
   ```bash
   helm install lunalytics-operator lunalytics-operator/lunalytics-operator \
     --namespace lunalytics-system \
     --set lunalytics.apiToken="your-api-token-here" \
     --set namespaceFilter.strategy="annotation"
   ```

#### Method 2: Manual Deployment

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd lunalytics_operator
   ```

2. **Create the namespace**:
   ```bash
   kubectl apply -f examples/namespace.yaml
   ```

3. **Update the API token**:
   Edit `deploy/deployment.yaml` and replace `your-lunalytics-api-token-here` with your actual Lunalytics API token.

4. **Deploy the operator**:
   ```bash
   # Apply the CRD
   kubectl apply -f deploy/crd.yaml
   
   # Apply RBAC permissions
   kubectl apply -f deploy/rbac.yaml
   
   # Apply the deployment
   kubectl apply -f deploy/deployment.yaml
   ```

### Verify Installation

```bash
kubectl get pods -n lunalytics-system -l app.kubernetes.io/name=lunalytics-operator
kubectl logs -n lunalytics-system -l app.kubernetes.io/name=lunalytics-operator
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LUNALYTICS_API_TOKEN` | Lunalytics API token (required) | - |
| `LUNALYTICS_API_URL` | Lunalytics API base URL | `https://lunalytics.xyz` |
| `DUPLICATE_HANDLING` | Conflict resolution strategy | `annotation_priority` |
| `MAX_RETRY_ATTEMPTS` | Max retry attempts (-1 for infinite) | `3` |
| `RETRY_BACKOFF_FACTOR` | Exponential backoff factor | `2.0` |
| `RETRY_MAX_DELAY` | Maximum delay between retries (seconds) | `300` |
| `MONITOR_DEFAULT_*` | Default monitor configuration | See defaults.yaml |
| `NAMESPACE_FILTER_STRATEGY` | Namespace filtering strategy (`all`, `list`, `annotation`) | `all` |
| `NAMESPACE_FILTER_NAMESPACES` | Comma-separated list of namespaces (when strategy=`list`) | - |
| `NAMESPACE_FILTER_ANNOTATION_KEY` | Annotation key for namespace filtering (when strategy=`annotation`) | `lunalytics.io/enabled` |
| `NAMESPACE_FILTER_ANNOTATION_VALUE` | Annotation value for namespace filtering (when strategy=`annotation`) | `true` |
| `KUBERNETES_IN_CLUSTER` | Run in Kubernetes cluster mode (auto-detected if not set) | - |
| `KUBECONFIG` | Path to kubeconfig file (for out-of-cluster testing) | - |
| `KUBERNETES_CONTEXT` | Kubernetes context to use | - |

### Configuration File

The operator also supports YAML configuration via `config/defaults.yaml`:

```yaml
# Default monitor configuration
monitor_defaults:
  type: "http"
  method: "GET"
  interval: 30
  retry_interval: 30
  request_timeout: 30
  valid_status_codes: ["200-299"]

# Retry configuration
retry:
  max_attempts: 3  # -1 for infinite retries
  backoff_factor: 2
  max_delay: 300  # seconds

# Duplicate handling: annotation_priority, crd_priority, allow_both
duplicate_handling: "annotation_priority"

# Namespace filtering
namespace_filter:
  # Strategy: all, list, annotation
  strategy: "all"
  # List of namespaces to monitor (when strategy is 'list')
  namespaces: []
  # Annotation key to check for on namespaces (when strategy is 'annotation')
  annotation_key: "lunalytics.io/enabled"
  annotation_value: "true"

# Kubernetes API configuration
kubernetes:
  # Run in cluster mode (auto-detected)
  in_cluster: true
  # kubeconfig file path (for testing)
  config_file: ""
  # context name
  context: ""

# Lunalytics API configuration
lunalytics:
  api_url: "https://lunalytics.xyz"
```

## Usage

### Ingress Monitoring

Add annotations to your Ingress resources to enable monitoring:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app-ingress
  namespace: lunalytics-system
  annotations:
    # Enable Lunalytics monitoring
    lunalytics.io/enabled: "true"
    
    # Optional: Override monitor name
    lunalytics.io/name: "My App Frontend"
    
    # Optional: Override URL (defaults to first host + path)
    lunalytics.io/url: "https://my-app.example.com/api/health"
    
    # Optional: Customize monitoring parameters
    lunalytics.io/interval: "60"
    lunalytics.io/retry-interval: "30"
    lunalytics.io/request-timeout: "10"
    lunalytics.io/method: "GET"
    lunalytics.io/valid-status-codes: "200-299,301"
spec:
  rules:
    - host: my-app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-app-service
                port:
                  number: 80
```

### Service Monitoring

Add annotations to your Service resources:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-app-service
  namespace: lunalytics-system
  annotations:
    # Enable Lunalytics monitoring
    lunalytics.io/enabled: "true"
    
    # Optional: Custom monitor name
    lunalytics.io/name: "My App Service"
    
    # Optional: Override URL (defaults to cluster internal URL)
    lunalytics.io/url: "http://my-app-service.default.svc.cluster.local:8080/health"
    
    # Optional: Customize monitoring
    lunalytics.io/interval: "30"
    lunalytics.io/method: "GET"
spec:
  selector:
    app: my-app
  ports:
    - port: 8080
      targetPort: 8080
      protocol: TCP
```

### Monitor CRD

Create dedicated Monitor resources for more control:

```yaml
apiVersion: lunalytics.io/v1alpha1
kind: Monitor
metadata:
  name: my-custom-monitor
  namespace: lunalytics-system
spec:
  name: "Custom Monitor"
  url: "https://api.example.com/health"
  type: "http"
  method: "GET"
  interval: 60
  retryInterval: 30
  requestTimeout: 15
  validStatusCodes: ["200-299"]
```

## Annotation Reference

| Annotation | Description | Required | Default |
|------------|-------------|----------|---------|
| `lunalytics.io/enabled` | Enable monitoring for this resource | Yes | `false` |
| `lunalytics.io/name` | Monitor name | No | `{kind}/{name}` |
| `lunalytics.io/url` | Explicit URL override | No | Auto-generated |
| `lunalytics.io/interval` | Monitoring interval (seconds) | No | `30` |
| `lunalytics.io/retry-interval` | Retry interval (seconds) | No | `30` |
| `lunalytics.io/request-timeout` | Request timeout (seconds) | No | `30` |
| `lunalytics.io/method` | HTTP method | No | `GET` |
| `lunalytics.io/valid-status-codes` | Valid status codes (comma-separated) | No | `200-299` |

**Note**: `lunalytics.io/monitor-id` is automatically managed by the operator and should not be set manually.

## Duplicate Handling

The operator supports three conflict resolution strategies:

- **`annotation_priority`** (default): Annotations take precedence over CRDs
- **`crd_priority`**: CRDs take precedence over annotations  
- **`allow_both`**: Both annotations and CRDs can create monitors for the same URL

Configure via environment variable or config file:

```bash
export DUPLICATE_HANDLING="annotation_priority"
```

## Namespace Filtering

The operator supports filtering which namespaces to monitor:

### Filtering Strategies

1. **`all`** (default): Monitor all namespaces - no filtering applied
2. **`list`**: Monitor only specified namespaces - requires `NAMESPACE_FILTER_NAMESPACES` to be set
3. **`annotation`**: Monitor only namespaces with specific annotation - requires `NAMESPACE_FILTER_ANNOTATION_KEY` and `NAMESPACE_FILTER_ANNOTATION_VALUE`

### Configuration Examples

**Monitor all namespaces**:
```yaml
namespace_filter:
  strategy: "all"
```

**Monitor specific namespaces**:
```yaml
namespace_filter:
  strategy: "list"
  namespaces: ["production", "staging"]
```

**Monitor namespaces with annotation**:
```yaml
namespace_filter:
  strategy: "annotation"
  annotation_key: "lunalytics.io/enabled"
  annotation_value: "true"
```

**Enable monitoring for a namespace**:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: my-monitored-namespace
  annotations:
    lunalytics.io/enabled: "true"
```

## URL Construction

### Ingress URLs

For Ingress resources, the operator constructs URLs using:
- **Protocol**: `https` if TLS is configured, otherwise `http`
- **Host**: First rule's host
- **Path**: First path from the first rule

Example: `https://my-app.example.com/api/health`

### Service URLs

For Service resources, the operator constructs internal cluster URLs:
- **Protocol**: `https` if port name contains ssl/tls/https, otherwise `http`
- **Host**: `{service-name}.{namespace}.svc.cluster.local`
- **Port**: First port number

Example: `http://my-app-service.default.svc.cluster.local:8080/`

## Monitoring and Troubleshooting

### Check Operator Status

```bash
# Check operator pod status
kubectl get pods -n lunalytics-system -l app.kubernetes.io/name=lunalytics-operator

# View operator logs
kubectl logs -n lunalytics-system -l app.kubernetes.io/name=lunalytics-operator -f

# Check Monitor CRD status
kubectl get monitors -A
kubectl describe monitor <monitor-name> -n <namespace>

# Check namespace filtering
kubectl get namespaces --show-labels
```

### Common Issues

1. **Monitor not created**:
   - Check if `lunalytics.io/enabled: "true"` annotation is set
   - Verify API token is correct
   - Check operator logs for errors

2. **Duplicate conflicts**:
   - Review `DUPLICATE_HANDLING` configuration
   - Check for existing Monitor CRDs with same URL
   - Use `kubectl get monitors` to see conflict status

3. **API connection issues**:
   - Verify `LUNALYTICS_API_URL` is correct
   - Check network connectivity from cluster
   - Review retry configuration

### Log Levels

The operator uses structured logging. Key log messages include:
- Monitor creation/update/deletion events
- API call results and retries
- Conflict detection and resolution
- Configuration validation errors

## Kubernetes API Configuration

The operator automatically detects how to connect to the Kubernetes API:

### In-Cluster Mode (Production)
When deployed in a Kubernetes cluster, the operator automatically uses:
- Service account token from `/var/run/secrets/kubernetes.io/serviceaccount/`
- Cluster DNS for API server discovery
- No additional configuration required

### Out-of-Cluster Mode (Development)
For local development or testing, configure via environment variables:

```bash
# Use kubeconfig file
export KUBECONFIG="/path/to/kubeconfig"

# Specify context
export KUBERNETES_CONTEXT="my-context"

# Force out-of-cluster mode
export KUBERNETES_IN_CLUSTER="false"
```

### Configuration Options

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `KUBERNETES_IN_CLUSTER` | Force in-cluster mode (`true`) or out-of-cluster (`false`) | Auto-detected |
| `KUBECONFIG` | Path to kubeconfig file (out-of-cluster only) | `~/.kube/config` |
| `KUBERNETES_CONTEXT` | Kubernetes context to use | Current context |

## Development

### Building the Operator

#### Container Build

The repository includes GitHub Actions workflows that automatically build and push container images:

- **Push to main**: Builds and pushes `latest` tag
- **Create release tag**: Builds and pushes version-specific tags
- **Pull requests**: Builds and pushes PR-specific tags

#### Local Development

```bash
# Build Docker image locally
docker build -t lunalytics-operator:latest .

# Run locally for development
python -m src.operator

# Test with Helm chart
helm install test ./helm/lunalytics-operator \
  --set lunalytics.apiToken="your-token" \
  --dry-run --debug

# Run locally for development (requires kubeconfig)
export KUBECONFIG="/path/to/your/kubeconfig"
export LUNALYTICS_API_TOKEN="your-token"
python -m src.operator
```

### Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests (when implemented)
pytest tests/
```

## API Reference

### Lunalytics API Endpoints

The operator interacts with these Lunalytics API endpoints:

- `POST /api/monitor/add` - Create new monitor
- `POST /api/monitor/edit` - Update existing monitor
- `GET /api/monitor/delete` - Delete monitor
- `GET /api/monitor/id` - Get monitor details

### Monitor Payload Format

```json
{
  "name": "Monitor Name",
  "url": "https://example.com/health",
  "type": "http",
  "method": "GET",
  "valid_status_codes": ["200-299"],
  "interval": 30,
  "retryInterval": 30,
  "requestTimeout": 30
}
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
- Create an issue in the repository
- Check the troubleshooting section above
- Review operator logs for detailed error information
