# `liftwork.yaml`

Commit a `liftwork.yaml` at the **root of your application repo** to control
how liftwork builds and deploys it. Every field is optional — most apps work
out of the box without one.

## Resolution order (lowest priority first)

1. **Inferred defaults** — picked at build time from the repo:
   - `port`: `EXPOSE` from your `Dockerfile` if present, else a per-language
     convention (`node`→3000, `python`→8000, `ruby`→3000, `dotnet`→5000,
     everything else→8080).
   - `health_check.path`: always `/`.
   - `replicas`: always 1.
2. **Application form fields** (`Application.app_port`, etc.) — legacy
   override layer; consumed only when no inferred defaults were captured.
3. **`liftwork.yaml` `deploy:` block** — file wins.

So the typical flow: clone a Node app with `EXPOSE 3000`, deploy with
**zero config**. Once you outgrow the defaults, commit a `liftwork.yaml`.

A future release will surface the diff between dashboard fields and the
latest committed file (Argo-style sync UX).

## Schema

```yaml
version: "1"                 # currently the only supported version
language: python             # optional; overrides language autodetect
                             # one of: python | node | go | rust | static

build:
  dockerfile: ./Dockerfile   # if you commit your own Dockerfile, point here
  context: .
  args:
    PY_VERSION: "3.12"
  target: runtime            # multi-stage target
  cache_from: []
  extra_files: []

deploy:
  port: 8080                 # container port your app listens on
  replicas: 1
  command: ["uvicorn", "main:app"]   # overrides the image's CMD if set
  env:
    LOG_LEVEL: INFO
    DB_URL:
      from_secret: my-db
      key: url               # optional — defaults to the env var name
    OTEL:
      from_configmap: telemetry
      key: otlp
  resources:
    requests: { cpu: "100m", memory: "128Mi" }
    limits:   { cpu: "1",    memory: "512Mi" }
  health_check:
    path: /healthz
    initial_delay_seconds: 5
    period_seconds: 10
  ingress:
    enabled: true
    host: api.example.com
    class_name: nginx
    annotations: {}
    tls_secret_name: api-tls
```

## Env vars: strings vs refs

Three forms are supported:

```yaml
deploy:
  env:
    PLAIN: hello                                           # literal string
    DB_URL: { from_secret: my-db, key: url }              # k8s Secret ref
    OTEL:   { from_configmap: telemetry, key: otlp }      # k8s ConfigMap ref
    API_KEY: { from_secret: api-creds }                   # key defaults to "API_KEY"
```

The referenced `Secret` / `ConfigMap` must already exist in the target
namespace — liftwork **does not** manage their lifecycle. Use `kubectl
create secret` or your secret manager to create them before deploy.

## Merge semantics

Per-field deep merge. The base is built from the Application row's columns
(`app_port`, `health_check_path`, `replicas`); your file is merged on top.
Lists and scalars **replace** wholesale; nested mappings **merge**.

So if your file has only:

```yaml
deploy:
  health_check:
    path: /readyz
```

…the deploy still uses your `Application.app_port` for `port`, your
`Application.replicas` for `replicas`, and the default
`health_check.initial_delay_seconds` of 5 — only `health_check.path` is
overridden.

## Validation

`liftwork.yaml` is parsed and validated at build time. A malformed file
**fails the build** with the validation error in the error column — your
deploy will never get a half-broken spec.
