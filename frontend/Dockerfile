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
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
