{{/*
Liftwork chart — common helpers.

Conventions:
- `liftwork.namespace` returns either an explicit `.Values.namespace` or
  the release namespace (`.Release.Namespace`). All resource manifests
  use this.
- `liftwork.<comp>.fullname` returns `<release>-<comp>` (e.g. `lw-api`).
- `liftwork.labels` and `liftwork.selectorLabels` follow the
  Kubernetes recommended label set.
*/}}

{{/* Resolve the namespace — explicit value > release namespace */}}
{{- define "liftwork.namespace" -}}
{{- if .Values.namespace -}}
{{ .Values.namespace }}
{{- else -}}
{{ .Release.Namespace }}
{{- end -}}
{{- end -}}

{{/* Base name (capped at 63 chars per DNS-1123) */}}
{{- define "liftwork.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Per-component fullname helpers */}}
{{- define "liftwork.api.fullname"       -}}{{ printf "%s-%s" .Release.Name "api"       | trunc 63 | trimSuffix "-" }}{{- end -}}
{{- define "liftwork.worker.fullname"    -}}{{ printf "%s-%s" .Release.Name "worker"    | trunc 63 | trimSuffix "-" }}{{- end -}}
{{- define "liftwork.dashboard.fullname" -}}{{ printf "%s-%s" .Release.Name "dashboard" | trunc 63 | trimSuffix "-" }}{{- end -}}
{{- define "liftwork.migrate.fullname"   -}}{{ printf "%s-%s" .Release.Name "migrate"   | trunc 63 | trimSuffix "-" }}{{- end -}}
{{- define "liftwork.secret.fullname"    -}}{{ printf "%s-%s" .Release.Name "secrets"   | trunc 63 | trimSuffix "-" }}{{- end -}}
{{- define "liftwork.config.fullname"    -}}{{ printf "%s-%s" .Release.Name "config"    | trunc 63 | trimSuffix "-" }}{{- end -}}
{{- define "liftwork.ingress.fullname"   -}}{{ printf "%s-%s" .Release.Name "ingress"   | trunc 63 | trimSuffix "-" }}{{- end -}}

{{/* Common labels — applied to every resource */}}
{{- define "liftwork.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "liftwork.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: liftwork
{{- with .Values.global.labels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/* Per-component selector labels (stable across rollouts) */}}
{{- define "liftwork.api.selectorLabels" -}}
app.kubernetes.io/name: {{ include "liftwork.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: api
{{- end -}}

{{- define "liftwork.worker.selectorLabels" -}}
app.kubernetes.io/name: {{ include "liftwork.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: worker
{{- end -}}

{{- define "liftwork.dashboard.selectorLabels" -}}
app.kubernetes.io/name: {{ include "liftwork.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: dashboard
{{- end -}}

{{/* Service account names */}}
{{- define "liftwork.api.serviceAccountName" -}}
{{- if .Values.serviceAccount.api.create -}}
{{ default (printf "%s-api" .Release.Name) .Values.serviceAccount.api.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.api.name }}
{{- end -}}
{{- end -}}

{{- define "liftwork.worker.serviceAccountName" -}}
{{- if .Values.serviceAccount.worker.create -}}
{{ default (printf "%s-worker" .Release.Name) .Values.serviceAccount.worker.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.worker.name }}
{{- end -}}
{{- end -}}

{{- define "liftwork.dashboard.serviceAccountName" -}}
{{- if .Values.serviceAccount.dashboard.create -}}
{{ default (printf "%s-dashboard" .Release.Name) .Values.serviceAccount.dashboard.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.dashboard.name }}
{{- end -}}
{{- end -}}

{{/*
Resolve the database URL. Priority:
  1. Bundled postgresql subchart (if .Values.postgresql.enabled)
  2. .Values.externalDatabase.url
*/}}
{{- define "liftwork.databaseUrl" -}}
{{- if .Values.postgresql.enabled -}}
{{- $auth := .Values.postgresql.auth -}}
postgresql+asyncpg://{{ $auth.username }}:{{ $auth.password }}@{{ .Release.Name }}-postgresql:5432/{{ $auth.database }}
{{- else -}}
{{ required "Set externalDatabase.url or postgresql.enabled=true" .Values.externalDatabase.url }}
{{- end -}}
{{- end -}}

{{/* Resolve the redis URL — same logic */}}
{{- define "liftwork.redisUrl" -}}
{{- if .Values.redis.enabled -}}
redis://{{ .Release.Name }}-redis-master:6379/0
{{- else -}}
{{ required "Set externalRedis.url or redis.enabled=true" .Values.externalRedis.url }}
{{- end -}}
{{- end -}}

{{/* Resolve image refs — supports global registry override */}}
{{- define "liftwork.image" -}}
{{- $registry := .global.imageRegistry | default "" -}}
{{- $repo := .image.repository -}}
{{- $tag := .image.tag | default .chartVersion -}}
{{- if $registry -}}
{{ printf "%s/%s:%s" $registry $repo $tag }}
{{- else -}}
{{ printf "%s:%s" $repo $tag }}
{{- end -}}
{{- end -}}

{{/* Secret name resolver — existingSecret > chart-managed */}}
{{- define "liftwork.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{ .Values.secrets.existingSecret }}
{{- else -}}
{{ include "liftwork.secret.fullname" . }}
{{- end -}}
{{- end -}}
