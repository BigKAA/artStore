#!/bin/bash
# ==============================================================================
# ArtStore Database Initialization Script
# ==============================================================================
# Автоматически создает отдельные базы данных для каждого модуля при первом
# запуске PostgreSQL контейнера.
#
# Этот скрипт выполняется только один раз при инициализации данных PostgreSQL.
# ==============================================================================

set -e

# Функция создания БД если она не существует
create_database() {
    local database=$1
    echo "Creating database: $database"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
        SELECT 'CREATE DATABASE $database'
        WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$database')\gexec
EOSQL
}

echo "=========================================="
echo "Initializing ArtStore databases..."
echo "=========================================="

# Создание БД для каждого модуля
create_database "artstore_admin"
create_database "artstore_storage_01"
create_database "artstore_storage_02"
create_database "artstore_ingester"
create_database "artstore_query"

# Создание расширений для Full-Text Search (PostgreSQL)
echo "Enabling PostgreSQL extensions..."
for db in artstore_admin artstore_storage_01 artstore_storage_02 artstore_ingester artstore_query; do
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<-EOSQL
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
        CREATE EXTENSION IF NOT EXISTS btree_gin;
EOSQL
done

echo "=========================================="
echo "Database initialization completed!"
echo "=========================================="
