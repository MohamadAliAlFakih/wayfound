# Frontend image — builds the React app, then serves it with a tiny nginx.
# Two-stage build: stage 1 compiles, stage 2 serves the static output.

# === Stage 1: build ===
FROM node:20-alpine AS build

WORKDIR /app

# Cache layer: only re-install when package*.json changes.
COPY package.json package-lock.json ./
RUN npm ci

# Copy the rest and build the production bundle.
COPY . .
RUN npm run build

# === Stage 2: serve ===
FROM nginx:1.27-alpine

# Drop the default nginx site config; ship our own SPA-friendly one.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the built static files into nginx's serve directory.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80