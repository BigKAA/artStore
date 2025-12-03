--
-- PostgreSQL database dump
--

\restrict fqO6kFJM2c0dTfyiEyTQVjzR0QK3optP2LLuDbKhT3ysHhyAhiMuFmZ2fnCXvVX

-- Dumped from database version 15.14 (Debian 15.14-1.pgdg13+1)
-- Dumped by pg_dump version 15.14 (Debian 15.14-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: storage_elem_01_config; Type: TABLE; Schema: public; Owner: artstore
--

CREATE TABLE public.storage_elem_01_config (
    id integer NOT NULL,
    current_mode character varying(10) NOT NULL,
    mode_changed_at timestamp with time zone DEFAULT now() NOT NULL,
    mode_changed_by character varying(255),
    is_master boolean NOT NULL,
    master_elected_at timestamp with time zone,
    total_files integer NOT NULL,
    total_size_bytes integer NOT NULL,
    last_cache_rebuild timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.storage_elem_01_config OWNER TO artstore;

--
-- Name: COLUMN storage_elem_01_config.id; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_config.id IS 'Primary key (всегда 1 для singleton)';


--
-- Name: COLUMN storage_elem_01_config.current_mode; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_config.current_mode IS 'Текущий режим работы (edit/rw/ro/ar)';


--
-- Name: COLUMN storage_elem_01_config.mode_changed_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_config.mode_changed_at IS 'Время последнего изменения режима';


--
-- Name: COLUMN storage_elem_01_config.mode_changed_by; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_config.mode_changed_by IS 'User ID кто изменил режим';


--
-- Name: COLUMN storage_elem_01_config.is_master; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_config.is_master IS 'Текущий узел является мастером';


--
-- Name: COLUMN storage_elem_01_config.master_elected_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_config.master_elected_at IS 'Время выбора текущего мастера';


--
-- Name: COLUMN storage_elem_01_config.total_files; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_config.total_files IS 'Количество файлов в хранилище';


--
-- Name: COLUMN storage_elem_01_config.total_size_bytes; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_config.total_size_bytes IS 'Общий размер файлов в байтах';


--
-- Name: COLUMN storage_elem_01_config.last_cache_rebuild; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_config.last_cache_rebuild IS 'Время последней пересборки кеша';


--
-- Name: COLUMN storage_elem_01_config.created_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_config.created_at IS 'Время создания записи';


--
-- Name: COLUMN storage_elem_01_config.updated_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_config.updated_at IS 'Время последнего обновления';


--
-- Name: storage_elem_01_files; Type: TABLE; Schema: public; Owner: artstore
--

CREATE TABLE public.storage_elem_01_files (
    file_id uuid NOT NULL,
    original_filename character varying(500) NOT NULL,
    storage_filename character varying(500) NOT NULL,
    file_size bigint NOT NULL,
    content_type character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by_id character varying(255) NOT NULL,
    created_by_username character varying(255) NOT NULL,
    created_by_fullname character varying(500),
    description text,
    version character varying(50),
    storage_path character varying(1000) NOT NULL,
    checksum character varying(64) NOT NULL,
    search_vector tsvector,
    metadata_json jsonb
);


ALTER TABLE public.storage_elem_01_files OWNER TO artstore;

--
-- Name: COLUMN storage_elem_01_files.file_id; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.file_id IS 'Уникальный идентификатор файла';


--
-- Name: COLUMN storage_elem_01_files.original_filename; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.original_filename IS 'Оригинальное имя файла';


--
-- Name: COLUMN storage_elem_01_files.storage_filename; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.storage_filename IS 'Имя файла в хранилище (с username, timestamp, uuid)';


--
-- Name: COLUMN storage_elem_01_files.file_size; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.file_size IS 'Размер файла в байтах';


--
-- Name: COLUMN storage_elem_01_files.content_type; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.content_type IS 'MIME type файла';


--
-- Name: COLUMN storage_elem_01_files.created_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.created_at IS 'Время создания файла';


--
-- Name: COLUMN storage_elem_01_files.updated_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.updated_at IS 'Время последнего обновления метаданных';


--
-- Name: COLUMN storage_elem_01_files.created_by_id; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.created_by_id IS 'User ID создателя файла';


--
-- Name: COLUMN storage_elem_01_files.created_by_username; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.created_by_username IS 'Username создателя';


--
-- Name: COLUMN storage_elem_01_files.created_by_fullname; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.created_by_fullname IS 'ФИО создателя (опционально)';


--
-- Name: COLUMN storage_elem_01_files.description; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.description IS 'Описание содержимого файла';


--
-- Name: COLUMN storage_elem_01_files.version; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.version IS 'Версия документа';


--
-- Name: COLUMN storage_elem_01_files.storage_path; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.storage_path IS 'Относительный путь в хранилище (year/month/day/hour/)';


--
-- Name: COLUMN storage_elem_01_files.checksum; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.checksum IS 'SHA256 checksum файла';


--
-- Name: COLUMN storage_elem_01_files.search_vector; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.search_vector IS 'Full-text search vector (auto-generated)';


--
-- Name: COLUMN storage_elem_01_files.metadata_json; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_files.metadata_json IS 'Дополнительные метаданные (расширяемое поле)';


--
-- Name: storage_elem_01_wal; Type: TABLE; Schema: public; Owner: artstore
--

CREATE TABLE public.storage_elem_01_wal (
    transaction_id uuid NOT NULL,
    operation_type character varying(50) NOT NULL,
    status character varying(20) NOT NULL,
    file_id uuid,
    operation_data jsonb NOT NULL,
    error_message text,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    duration_ms integer,
    user_id character varying(255)
);


ALTER TABLE public.storage_elem_01_wal OWNER TO artstore;

--
-- Name: COLUMN storage_elem_01_wal.transaction_id; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_wal.transaction_id IS 'UUID транзакции';


--
-- Name: COLUMN storage_elem_01_wal.operation_type; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_wal.operation_type IS 'Тип операции (file_create, file_update, etc.)';


--
-- Name: COLUMN storage_elem_01_wal.status; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_wal.status IS 'Статус транзакции (pending, committed, rolled_back, failed)';


--
-- Name: COLUMN storage_elem_01_wal.file_id; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_wal.file_id IS 'UUID файла (для файловых операций)';


--
-- Name: COLUMN storage_elem_01_wal.operation_data; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_wal.operation_data IS 'Данные операции (файл, путь, метаданные и т.д.)';


--
-- Name: COLUMN storage_elem_01_wal.error_message; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_wal.error_message IS 'Сообщение об ошибке (если failed)';


--
-- Name: COLUMN storage_elem_01_wal.started_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_wal.started_at IS 'Время начала операции';


--
-- Name: COLUMN storage_elem_01_wal.completed_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_wal.completed_at IS 'Время завершения операции';


--
-- Name: COLUMN storage_elem_01_wal.duration_ms; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_wal.duration_ms IS 'Длительность операции в миллисекундах';


--
-- Name: COLUMN storage_elem_01_wal.user_id; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_01_wal.user_id IS 'User ID инициатора операции';


--
-- Name: storage_elem_02_config; Type: TABLE; Schema: public; Owner: artstore
--

CREATE TABLE public.storage_elem_02_config (
    id integer NOT NULL,
    current_mode character varying(10) NOT NULL,
    mode_changed_at timestamp with time zone DEFAULT now() NOT NULL,
    mode_changed_by character varying(255),
    is_master boolean NOT NULL,
    master_elected_at timestamp with time zone,
    total_files integer NOT NULL,
    total_size_bytes integer NOT NULL,
    last_cache_rebuild timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.storage_elem_02_config OWNER TO artstore;

--
-- Name: COLUMN storage_elem_02_config.id; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_config.id IS 'Primary key (всегда 1 для singleton)';


--
-- Name: COLUMN storage_elem_02_config.current_mode; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_config.current_mode IS 'Текущий режим работы (edit/rw/ro/ar)';


--
-- Name: COLUMN storage_elem_02_config.mode_changed_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_config.mode_changed_at IS 'Время последнего изменения режима';


--
-- Name: COLUMN storage_elem_02_config.mode_changed_by; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_config.mode_changed_by IS 'User ID кто изменил режим';


--
-- Name: COLUMN storage_elem_02_config.is_master; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_config.is_master IS 'Текущий узел является мастером';


--
-- Name: COLUMN storage_elem_02_config.master_elected_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_config.master_elected_at IS 'Время выбора текущего мастера';


--
-- Name: COLUMN storage_elem_02_config.total_files; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_config.total_files IS 'Количество файлов в хранилище';


--
-- Name: COLUMN storage_elem_02_config.total_size_bytes; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_config.total_size_bytes IS 'Общий размер файлов в байтах';


--
-- Name: COLUMN storage_elem_02_config.last_cache_rebuild; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_config.last_cache_rebuild IS 'Время последней пересборки кеша';


--
-- Name: COLUMN storage_elem_02_config.created_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_config.created_at IS 'Время создания записи';


--
-- Name: COLUMN storage_elem_02_config.updated_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_config.updated_at IS 'Время последнего обновления';


--
-- Name: storage_elem_02_files; Type: TABLE; Schema: public; Owner: artstore
--

CREATE TABLE public.storage_elem_02_files (
    file_id uuid NOT NULL,
    original_filename character varying(500) NOT NULL,
    storage_filename character varying(500) NOT NULL,
    file_size bigint NOT NULL,
    content_type character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by_id character varying(255) NOT NULL,
    created_by_username character varying(255) NOT NULL,
    created_by_fullname character varying(500),
    description text,
    version character varying(50),
    storage_path character varying(1000) NOT NULL,
    checksum character varying(64) NOT NULL,
    search_vector tsvector,
    metadata_json jsonb
);


ALTER TABLE public.storage_elem_02_files OWNER TO artstore;

--
-- Name: COLUMN storage_elem_02_files.file_id; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.file_id IS 'Уникальный идентификатор файла';


--
-- Name: COLUMN storage_elem_02_files.original_filename; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.original_filename IS 'Оригинальное имя файла';


--
-- Name: COLUMN storage_elem_02_files.storage_filename; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.storage_filename IS 'Имя файла в хранилище (с username, timestamp, uuid)';


--
-- Name: COLUMN storage_elem_02_files.file_size; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.file_size IS 'Размер файла в байтах';


--
-- Name: COLUMN storage_elem_02_files.content_type; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.content_type IS 'MIME type файла';


--
-- Name: COLUMN storage_elem_02_files.created_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.created_at IS 'Время создания файла';


--
-- Name: COLUMN storage_elem_02_files.updated_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.updated_at IS 'Время последнего обновления метаданных';


--
-- Name: COLUMN storage_elem_02_files.created_by_id; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.created_by_id IS 'User ID создателя файла';


--
-- Name: COLUMN storage_elem_02_files.created_by_username; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.created_by_username IS 'Username создателя';


--
-- Name: COLUMN storage_elem_02_files.created_by_fullname; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.created_by_fullname IS 'ФИО создателя (опционально)';


--
-- Name: COLUMN storage_elem_02_files.description; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.description IS 'Описание содержимого файла';


--
-- Name: COLUMN storage_elem_02_files.version; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.version IS 'Версия документа';


--
-- Name: COLUMN storage_elem_02_files.storage_path; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.storage_path IS 'Относительный путь в хранилище (year/month/day/hour/)';


--
-- Name: COLUMN storage_elem_02_files.checksum; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.checksum IS 'SHA256 checksum файла';


--
-- Name: COLUMN storage_elem_02_files.search_vector; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.search_vector IS 'Full-text search vector (auto-generated)';


--
-- Name: COLUMN storage_elem_02_files.metadata_json; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_files.metadata_json IS 'Дополнительные метаданные (расширяемое поле)';


--
-- Name: storage_elem_02_wal; Type: TABLE; Schema: public; Owner: artstore
--

CREATE TABLE public.storage_elem_02_wal (
    transaction_id uuid NOT NULL,
    operation_type character varying(50) NOT NULL,
    status character varying(20) NOT NULL,
    file_id uuid,
    operation_data jsonb NOT NULL,
    error_message text,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    duration_ms integer,
    user_id character varying(255)
);


ALTER TABLE public.storage_elem_02_wal OWNER TO artstore;

--
-- Name: COLUMN storage_elem_02_wal.transaction_id; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_wal.transaction_id IS 'UUID транзакции';


--
-- Name: COLUMN storage_elem_02_wal.operation_type; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_wal.operation_type IS 'Тип операции (file_create, file_update, etc.)';


--
-- Name: COLUMN storage_elem_02_wal.status; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_wal.status IS 'Статус транзакции (pending, committed, rolled_back, failed)';


--
-- Name: COLUMN storage_elem_02_wal.file_id; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_wal.file_id IS 'UUID файла (для файловых операций)';


--
-- Name: COLUMN storage_elem_02_wal.operation_data; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_wal.operation_data IS 'Данные операции (файл, путь, метаданные и т.д.)';


--
-- Name: COLUMN storage_elem_02_wal.error_message; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_wal.error_message IS 'Сообщение об ошибке (если failed)';


--
-- Name: COLUMN storage_elem_02_wal.started_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_wal.started_at IS 'Время начала операции';


--
-- Name: COLUMN storage_elem_02_wal.completed_at; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_wal.completed_at IS 'Время завершения операции';


--
-- Name: COLUMN storage_elem_02_wal.duration_ms; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_wal.duration_ms IS 'Длительность операции в миллисекундах';


--
-- Name: COLUMN storage_elem_02_wal.user_id; Type: COMMENT; Schema: public; Owner: artstore
--

COMMENT ON COLUMN public.storage_elem_02_wal.user_id IS 'User ID инициатора операции';


--
-- Data for Name: storage_elem_01_config; Type: TABLE DATA; Schema: public; Owner: artstore
--

COPY public.storage_elem_01_config (id, current_mode, mode_changed_at, mode_changed_by, is_master, master_elected_at, total_files, total_size_bytes, last_cache_rebuild, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: storage_elem_01_files; Type: TABLE DATA; Schema: public; Owner: artstore
--

COPY public.storage_elem_01_files (file_id, original_filename, storage_filename, file_size, content_type, created_at, updated_at, created_by_id, created_by_username, created_by_fullname, description, version, storage_path, checksum, search_vector, metadata_json) FROM stdin;
\.


--
-- Data for Name: storage_elem_01_wal; Type: TABLE DATA; Schema: public; Owner: artstore
--

COPY public.storage_elem_01_wal (transaction_id, operation_type, status, file_id, operation_data, error_message, started_at, completed_at, duration_ms, user_id) FROM stdin;
\.


--
-- Data for Name: storage_elem_02_config; Type: TABLE DATA; Schema: public; Owner: artstore
--

COPY public.storage_elem_02_config (id, current_mode, mode_changed_at, mode_changed_by, is_master, master_elected_at, total_files, total_size_bytes, last_cache_rebuild, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: storage_elem_02_files; Type: TABLE DATA; Schema: public; Owner: artstore
--

COPY public.storage_elem_02_files (file_id, original_filename, storage_filename, file_size, content_type, created_at, updated_at, created_by_id, created_by_username, created_by_fullname, description, version, storage_path, checksum, search_vector, metadata_json) FROM stdin;
\.


--
-- Data for Name: storage_elem_02_wal; Type: TABLE DATA; Schema: public; Owner: artstore
--

COPY public.storage_elem_02_wal (transaction_id, operation_type, status, file_id, operation_data, error_message, started_at, completed_at, duration_ms, user_id) FROM stdin;
\.


--
-- Name: storage_elem_01_config storage_elem_01_config_pkey; Type: CONSTRAINT; Schema: public; Owner: artstore
--

ALTER TABLE ONLY public.storage_elem_01_config
    ADD CONSTRAINT storage_elem_01_config_pkey PRIMARY KEY (id);


--
-- Name: storage_elem_01_files storage_elem_01_files_pkey; Type: CONSTRAINT; Schema: public; Owner: artstore
--

ALTER TABLE ONLY public.storage_elem_01_files
    ADD CONSTRAINT storage_elem_01_files_pkey PRIMARY KEY (file_id);


--
-- Name: storage_elem_01_wal storage_elem_01_wal_pkey; Type: CONSTRAINT; Schema: public; Owner: artstore
--

ALTER TABLE ONLY public.storage_elem_01_wal
    ADD CONSTRAINT storage_elem_01_wal_pkey PRIMARY KEY (transaction_id);


--
-- Name: storage_elem_02_config storage_elem_02_config_pkey; Type: CONSTRAINT; Schema: public; Owner: artstore
--

ALTER TABLE ONLY public.storage_elem_02_config
    ADD CONSTRAINT storage_elem_02_config_pkey PRIMARY KEY (id);


--
-- Name: storage_elem_02_files storage_elem_02_files_pkey; Type: CONSTRAINT; Schema: public; Owner: artstore
--

ALTER TABLE ONLY public.storage_elem_02_files
    ADD CONSTRAINT storage_elem_02_files_pkey PRIMARY KEY (file_id);


--
-- Name: storage_elem_02_wal storage_elem_02_wal_pkey; Type: CONSTRAINT; Schema: public; Owner: artstore
--

ALTER TABLE ONLY public.storage_elem_02_wal
    ADD CONSTRAINT storage_elem_02_wal_pkey PRIMARY KEY (transaction_id);


--
-- Name: idx_storage_elem_01_filename; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_01_filename ON public.storage_elem_01_files USING btree (original_filename);


--
-- Name: idx_storage_elem_01_metadata; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_01_metadata ON public.storage_elem_01_files USING gin (metadata_json);


--
-- Name: idx_storage_elem_01_search_vector; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_01_search_vector ON public.storage_elem_01_files USING gin (search_vector);


--
-- Name: idx_storage_elem_01_user_date; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_01_user_date ON public.storage_elem_01_files USING btree (created_by_id, created_at);


--
-- Name: idx_storage_elem_01_wal_data; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_01_wal_data ON public.storage_elem_01_wal USING gin (operation_data);


--
-- Name: idx_storage_elem_01_wal_file; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_01_wal_file ON public.storage_elem_01_wal USING btree (file_id, started_at);


--
-- Name: idx_storage_elem_01_wal_status_time; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_01_wal_status_time ON public.storage_elem_01_wal USING btree (status, started_at);


--
-- Name: idx_storage_elem_02_filename; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_02_filename ON public.storage_elem_02_files USING btree (original_filename);


--
-- Name: idx_storage_elem_02_metadata; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_02_metadata ON public.storage_elem_02_files USING gin (metadata_json);


--
-- Name: idx_storage_elem_02_search_vector; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_02_search_vector ON public.storage_elem_02_files USING gin (search_vector);


--
-- Name: idx_storage_elem_02_user_date; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_02_user_date ON public.storage_elem_02_files USING btree (created_by_id, created_at);


--
-- Name: idx_storage_elem_02_wal_data; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_02_wal_data ON public.storage_elem_02_wal USING gin (operation_data);


--
-- Name: idx_storage_elem_02_wal_file; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_02_wal_file ON public.storage_elem_02_wal USING btree (file_id, started_at);


--
-- Name: idx_storage_elem_02_wal_status_time; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX idx_storage_elem_02_wal_status_time ON public.storage_elem_02_wal USING btree (status, started_at);


--
-- Name: ix_storage_elem_01_files_created_by_id; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_01_files_created_by_id ON public.storage_elem_01_files USING btree (created_by_id);


--
-- Name: ix_storage_elem_01_files_created_by_username; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_01_files_created_by_username ON public.storage_elem_01_files USING btree (created_by_username);


--
-- Name: ix_storage_elem_01_files_file_id; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_01_files_file_id ON public.storage_elem_01_files USING btree (file_id);


--
-- Name: ix_storage_elem_01_files_original_filename; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_01_files_original_filename ON public.storage_elem_01_files USING btree (original_filename);


--
-- Name: ix_storage_elem_01_files_storage_filename; Type: INDEX; Schema: public; Owner: artstore
--

CREATE UNIQUE INDEX ix_storage_elem_01_files_storage_filename ON public.storage_elem_01_files USING btree (storage_filename);


--
-- Name: ix_storage_elem_01_wal_file_id; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_01_wal_file_id ON public.storage_elem_01_wal USING btree (file_id);


--
-- Name: ix_storage_elem_01_wal_operation_type; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_01_wal_operation_type ON public.storage_elem_01_wal USING btree (operation_type);


--
-- Name: ix_storage_elem_01_wal_status; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_01_wal_status ON public.storage_elem_01_wal USING btree (status);


--
-- Name: ix_storage_elem_01_wal_user_id; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_01_wal_user_id ON public.storage_elem_01_wal USING btree (user_id);


--
-- Name: ix_storage_elem_02_files_created_by_id; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_02_files_created_by_id ON public.storage_elem_02_files USING btree (created_by_id);


--
-- Name: ix_storage_elem_02_files_created_by_username; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_02_files_created_by_username ON public.storage_elem_02_files USING btree (created_by_username);


--
-- Name: ix_storage_elem_02_files_file_id; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_02_files_file_id ON public.storage_elem_02_files USING btree (file_id);


--
-- Name: ix_storage_elem_02_files_original_filename; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_02_files_original_filename ON public.storage_elem_02_files USING btree (original_filename);


--
-- Name: ix_storage_elem_02_files_storage_filename; Type: INDEX; Schema: public; Owner: artstore
--

CREATE UNIQUE INDEX ix_storage_elem_02_files_storage_filename ON public.storage_elem_02_files USING btree (storage_filename);


--
-- Name: ix_storage_elem_02_wal_file_id; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_02_wal_file_id ON public.storage_elem_02_wal USING btree (file_id);


--
-- Name: ix_storage_elem_02_wal_operation_type; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_02_wal_operation_type ON public.storage_elem_02_wal USING btree (operation_type);


--
-- Name: ix_storage_elem_02_wal_status; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_02_wal_status ON public.storage_elem_02_wal USING btree (status);


--
-- Name: ix_storage_elem_02_wal_user_id; Type: INDEX; Schema: public; Owner: artstore
--

CREATE INDEX ix_storage_elem_02_wal_user_id ON public.storage_elem_02_wal USING btree (user_id);


--
-- PostgreSQL database dump complete
--

\unrestrict fqO6kFJM2c0dTfyiEyTQVjzR0QK3optP2LLuDbKhT3ysHhyAhiMuFmZ2fnCXvVX

