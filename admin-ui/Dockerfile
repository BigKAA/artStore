# =============================================================================
# ArtStore Admin UI - Multi-stage Docker Build
# =============================================================================
# Stage 1: Build Angular application with Node.js
# Stage 2: Serve static files with Nginx
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder - Compile Angular application
# -----------------------------------------------------------------------------
FROM node:20-alpine AS builder

# Установка рабочей директории
WORKDIR /app

# Копирование файлов зависимостей для кеширования слоев
COPY package*.json ./

# Установка зависимостей (ci для reproducible builds)
RUN npm ci

# Копирование исходного кода
COPY . .

# Сборка production версии Angular приложения
RUN npm run build -- --configuration=production

# -----------------------------------------------------------------------------
# Stage 2: Runtime - Nginx для раздачи статики
# -----------------------------------------------------------------------------
FROM nginx:alpine

# Метаданные образа
LABEL maintainer="ArtStore Team"
LABEL description="ArtStore Admin UI - Angular Frontend"
LABEL version="1.0.0"

# Копирование собранного приложения из builder stage
# Angular 20+ выводит в browser/ подпапку
COPY --from=builder /app/dist/artstore-admin-ui/browser /usr/share/nginx/html

# Копирование кастомной конфигурации Nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Порт для HTTP
EXPOSE 80

# Healthcheck для Docker и orchestrators
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

# Запуск Nginx в foreground режиме
CMD ["nginx", "-g", "daemon off;"]
