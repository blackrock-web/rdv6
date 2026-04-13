# ── Frontend Production Dockerfile ───────────────────────────────────────────
# Stage 1: Build
FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Stage 2: Serve
FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# Custom Nginx config for SPA routing and API proxying
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
