# syntax=docker/dockerfile:1.7

# --- Build the SPA ---------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app

# Install deps with the lockfile we have. The dashboard ships
# package.json + (optional) pnpm-lock.yaml; the Dockerfile prefers npm
# ci because it doesn't require a lockfile-tooling alignment dance.
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY . .
RUN npm run build


# --- Serve via nginx-unprivileged (runs as uid 101) ------------------------
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
WORKDIR /usr/share/nginx/html

USER root
RUN rm -rf /usr/share/nginx/html/*
USER 101

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget --quiet --tries=1 --spider http://localhost:8080/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
