# Redash Extension for Dify

A Dify plugin that integrates Redash data visualization and querying capabilities into the Dify AI platform. Enables AI agents and workflows to discover queries, execute them, retrieve results, browse dashboards, and list data sources from a connected Redash instance.

## Features

- **List Queries** - Discover available saved queries with search and pagination
- **Execute Query** - Run queries with parameters and cache control
- **Get Query Results** - Retrieve cached results without re-execution
- **List Dashboards** - Browse available dashboards with search and pagination
- **Get Dashboard Details** - Retrieve dashboard structure and widget data
- **List Data Sources** - View configured database connections

## Installation

1. Package this plugin following the [Dify Plugin Development Guide](https://docs.dify.ai/plugins/quick-start/develop-plugins)
2. Install the plugin in your Dify instance
3. Configure the provider with:
   - **Redash Instance URL** (HTTPS required)
   - **API Key** from your Redash user account

## Configuration

| Setting | Description | Required |
|---------|-------------|----------|
| `redash_url` | HTTPS URL of your Redash instance | Yes |
| `api_key` | Your Redash API key | Yes |

## Plugin Structure

```
├── manifest.yaml              # Plugin manifest
├── _assets/icon.svg           # Plugin icon
├── provider/
│   ├── redash.yaml            # Provider credential schema
│   └── redash.py              # Credential validation
├── tools/
│   ├── list_queries.yaml/py
│   ├── execute_query.yaml/py
│   ├── get_query_results.yaml/py
│   ├── list_dashboards.yaml/py
│   ├── get_dashboard_details.yaml/py
│   └── list_data_sources.yaml/py
├── utils/
│   ├── error_handler.py       # Structured error codes
│   ├── redash_client.py       # HTTP client with retry logic
│   └── response_formatter.py  # Result formatting
└── tests/                     # 329 unit + integration tests
```

## Development

### Requirements

- Python 3.12+
- pytest

### Running Tests

```bash
cd /path/to/this/repo
pytest
```

## Security

- HTTPS enforced for all Redash API communication
- API keys masked in all log outputs (only last 4 characters visible)
- HTTP URLs rejected at configuration time
- Structured error codes without internal detail exposure
- Connection and read timeouts configured

## Error Handling

The plugin uses structured error codes for all failure scenarios:

| Code | Category | Description |
|------|----------|-------------|
| AUTH_001 | Authentication | Invalid/expired credentials |
| AUTH_002 | Authentication | Insufficient permissions |
| CONN_001 | Connection | Instance unreachable |
| CONN_002 | Connection | Request timeout |
| RATE_001 | Rate Limit | API rate limit exceeded |
| QUERY_001 | Query | Query not found |
| QUERY_002 | Query | Execution timeout |
| QUERY_003 | Query | Execution error |
| QUERY_004 | Query | Invalid parameters |
| DASH_001 | Dashboard | Dashboard not found |
| VAL_001 | Validation | Input validation error |
| SERVER_001 | Server | Redash server error |

## License

MIT
