# syntax=docker/dockerfile:1.6
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
# Telegram login-widget bot username — build-time (Vite инлайнит import.meta.env
# в бандл). Дефолт = прод infrasafe.uz; profk.uz передаёт profkbot через compose.
ARG VITE_BOT_USERNAME=infrasafebot
ENV VITE_BOT_USERNAME=$VITE_BOT_USERNAME
# Brand variant — build-time (Vite инлайнит import.meta.env; плагин
# transformIndexHtml читает process.env.VITE_BRAND для шрифтов/favicon/manifest).
# Дефолт = infrasafe (тёмная тема). profk.uz передаёт profk через compose.
ARG VITE_BRAND=infrasafe
ENV VITE_BRAND=$VITE_BRAND
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
