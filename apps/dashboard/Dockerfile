# syntax=docker/dockerfile:1.7

# --- Build the SPA ---------------------------------------------------------
# Build context: this Dockerfile is built from the *repo root*
# (`docker build -f apps/dashboard/Dockerfile .`) so the workspace
# pnpm-lock.yaml is in scope for deterministic installs.
FROM node:20-alpine AS builder
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

# Copy just the manifests first so install layer caches across source-only changes.
COPY pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/dashboard/package.json ./apps/dashboard/
RUN pnpm install --frozen-lockfile --filter @liftwork/dashboard

# Bring in the source and build.
COPY apps/dashboard ./apps/dashboard
WORKDIR /app/apps/dashboard
RUN pnpm build


# --- Serve via nginx-unprivileged (runs as uid 101) ------------------------
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
WORKDIR /usr/share/nginx/html

USER root
RUN rm -rf /usr/share/nginx/html/*
USER 101

COPY --from=builder /app/apps/dashboard/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget --quiet --tries=1 --spider http://localhost:8080/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
