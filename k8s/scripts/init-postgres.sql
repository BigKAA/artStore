-- Скрипт инициализации PostgreSQL для ArtStore
-- Выполнить от имени суперпользователя (artur) в кластерном PostgreSQL (postgresql.pg.svc)
--
-- Подключение через NodePort:
--   psql -h <node-ip> -p 32543 -U artur -d postgres
-- Или через pgAdmin: pg.kryukov.lan

-- 1. Создание пользователя artstore
CREATE USER artstore WITH PASSWORD 'password';

-- 2. Создание баз данных
CREATE DATABASE artstore OWNER artstore;
CREATE DATABASE artstore_admin OWNER artstore;
CREATE DATABASE artstore_query OWNER artstore;

-- 3. Назначение привилегий
GRANT ALL PRIVILEGES ON DATABASE artstore TO artstore;
GRANT ALL PRIVILEGES ON DATABASE artstore_admin TO artstore;
GRANT ALL PRIVILEGES ON DATABASE artstore_query TO artstore;

-- 4. Подключиться к каждой БД и дать права на schema public
\c artstore
GRANT ALL ON SCHEMA public TO artstore;

\c artstore_admin
GRANT ALL ON SCHEMA public TO artstore;

\c artstore_query
GRANT ALL ON SCHEMA public TO artstore;
