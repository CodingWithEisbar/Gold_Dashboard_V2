FROM node:24.22.1-alpine AS build
WORKDIR /app
RUN npm install --global npm@12.2.2 && npm uninstall --global corepack
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run typecheck && npm run build

FROM nginxinc/nginx-unprivileged:1.30.6-alpine AS runtime
USER root
# Vendor base contains patched-available brotli/curl/expat CVEs; final image scan remains mandatory.
RUN apk upgrade --no-cache
COPY infra/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
USER 101:101
EXPOSE 8080
ENTRYPOINT ["nginx", "-g", "daemon off;"]
