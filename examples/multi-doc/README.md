# Multi-Document YAML Example

This example demonstrates nodeforge's multi-document YAML support (v0.4+).

A single YAML file contains two specs separated by `---`:

1. **Document 1:** Bootstrap a fresh Debian/Ubuntu server
2. **Document 2:** Install PostgreSQL on the bootstrapped server

## Usage

```bash
# Validate both documents
nodeforge validate bootstrap-and-service.yaml

# Show plans for both documents
nodeforge plan bootstrap-and-service.yaml

# Apply both in sequence
nodeforge apply bootstrap-and-service.yaml
```

## How It Works

When nodeforge encounters `---` separators in a YAML file, it parses each
document independently. Each document must have its own `kind:` field and
a complete spec structure. Documents are processed in file order.
