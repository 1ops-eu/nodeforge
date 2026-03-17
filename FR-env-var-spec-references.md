# Feature Request: Environment Variable References in Spec Files

## Summary

Allow nodeforge spec files to reference environment variables using `${VAR}`
syntax, so that secrets and environment-specific values do not need to be
hard-coded or pre-rendered into the spec before running `nodeforge apply`.

## Motivation

Today, any value that varies between environments (host IP, admin username,
SSH key path, WireGuard endpoint, …) must be baked into the spec file before
nodeforge reads it.  In a test suite this is done with a separate `envsubst`
step that renders a `.tpl` file into a concrete `spec.yaml`.  This has several
drawbacks:

1. **Extra tooling dependency.** `envsubst` (part of `gettext`) is an
   additional binary that must be present on every developer machine and CI
   runner.

2. **Rendered files pollute the repo.** The generated `spec.yaml` is a
   build artefact.  It must either be `.gitignore`d (risking accidental
   commits) or committed (causing noise in diffs).

3. **Two sources of truth.** Developers must keep `spec.yaml.tpl` and any
   documentation in sync.  The rendered copy is not the canonical file.

4. **No late binding.** Values are fixed at render time, so the same spec
   cannot be used across environments without re-rendering.

If nodeforge resolved `${VAR}` references at load time (using the process
environment), the template step becomes unnecessary, the `.tpl` file *is* the
spec, and secrets can be injected via environment variables without touching
the file.

## Proposed Behaviour

When nodeforge loads a spec file, after parsing the YAML it walks all string
values and expands any `${VAR_NAME}` or `$VAR_NAME` tokens using
`os.environ`.

```yaml
# spec.yaml — no pre-rendering needed
host:
  address: ${VM_IP}

login:
  user: ${VM_ROOT_USER}
  password: ${VM_ROOT_PASSWORD}

admin_user:
  pubkeys:
    - ${SSH_KEY_PUBLIC}

wireguard:
  private_key_file: ${WG_SERVER_KEY}
  endpoint: ${WG_ENDPOINT}
```

Running:

```bash
export VM_IP=192.168.56.10
export SSH_KEY_PUBLIC=/home/alice/.ssh/id_ed25519.pub
nodeforge apply spec.yaml
```

…resolves the variables inline, without any pre-processing step.

## Design Notes

### Expansion scope

Expansion should apply to **all string-typed fields** in the spec after YAML
parsing.  Non-string fields (integers, booleans, lists) are unaffected unless
their value was quoted as a string in the YAML.

### Missing variables

Two modes should be supported, controlled by a config flag or command-line
option:

- **`strict` (default):** Raise a clear error if a referenced variable is not
  set, rather than silently leaving an unexpanded `${VAR}` token in place.
- **`passthrough`:** Leave unset references unchanged (useful for specs that
  mix static and environment-provided values).

### Interaction with `validate`

`nodeforge validate` should expand environment variables before validation so
that the schema check operates on the resolved values, not the raw `${…}`
tokens.

### Interaction with `plan` / printed output

When nodeforge prints the plan or logs field values it should redact any value
whose source variable name matches a known-secret pattern (e.g. `PASSWORD`,
`SECRET`, `KEY`) or is listed in a `secrets:` block in the spec, consistent
with how passwords are currently redacted in the executor.

### `.env` file support

As an optional convenience, nodeforge could also accept a `--env-file` flag
(or a `env_file:` key in a project-level config) that loads variables from a
`.env` file before resolving the spec.  This removes the need to `export`
variables manually when using nodeforge interactively.

## Alternatives Considered

- **Keep `envsubst` as the current workaround.** Works, but requires an extra
  tool, leaves rendered artefacts in the repo, and is not an idiomatic
  nodeforge pattern.
- **Jinja2 templating in specs.** nodeforge already depends on Jinja2 for
  other purposes.  Full Jinja2 rendering is more powerful but significantly
  increases spec complexity and makes specs harder to read.  Simple `${VAR}`
  expansion covers 95 % of real-world use cases with minimal mental overhead.

## Acceptance Criteria

- [ ] `nodeforge apply spec.yaml` resolves `${VAR}` in all string fields
      using the current process environment.
- [ ] `nodeforge validate spec.yaml` resolves `${VAR}` before schema
      validation.
- [ ] An unset variable in strict mode produces a clear error:
      `"Unresolved variable '${VAR}' in spec field 'host.address'"`.
- [ ] The existing behaviour (spec files without `${}` tokens) is unchanged.
- [ ] Unit tests cover: resolved values, missing-variable error, passthrough
      mode, and interaction with `validate`.
