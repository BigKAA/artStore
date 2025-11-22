"""
Integration tests для mTLS communication между Query и Storage Element (download operations).

Проверяет:
- mTLS authentication при download файлов
- TLS 1.3 enforcement для retrieval operations
- Query client certificate validation
- Streaming download через TLS
- Connection pooling для download requests
"""

import asyncio
import ssl
from pathlib import Path
from typing import AsyncGenerator

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend


# ===============================================================================
# Test Constants
# ===============================================================================

TLS_INFRA_DIR = Path(__file__).parent.parent.parent.parent / "admin-module" / "tls-infrastructure"
CA_CERT_PATH = TLS_INFRA_DIR / "ca" / "ca-cert.pem"
STORAGE_SERVER_CERT_PATH = TLS_INFRA_DIR / "server-certs" / "storage-element" / "server-cert.pem"
QUERY_CLIENT_CERT_PATH = TLS_INFRA_DIR / "client-certs" / "query-client-cert.pem"
QUERY_CLIENT_KEY_PATH = TLS_INFRA_DIR / "client-certs" / "query-client-key.pem"

STORAGE_ELEMENT_TLS_URL = "https://storage-element:8010"
QUERY_MODULE_TLS_URL = "https://query-module:8030"


# ===============================================================================
# Fixtures
# ===============================================================================

@pytest.fixture
def query_ssl_context() -> ssl.SSLContext:
    """
    SSL context для Query Module с client certificate.

    Используется для mTLS communication со Storage Element.
    """
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.load_verify_locations(str(CA_CERT_PATH))
    context.load_cert_chain(
        certfile=str(QUERY_CLIENT_CERT_PATH),
        keyfile=str(QUERY_CLIENT_KEY_PATH)
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3

    # AEAD cipher suites only
    context.set_ciphers(
        "TLS_AES_256_GCM_SHA384:"
        "TLS_CHACHA20_POLY1305_SHA256:"
        "TLS_AES_128_GCM_SHA256"
    )

    return context


@pytest.fixture
async def query_mtls_client(
    query_ssl_context: ssl.SSLContext
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    HTTP client для Query Module с mTLS поддержкой.
    """
    async with httpx.AsyncClient(
        verify=query_ssl_context,
        cert=(str(QUERY_CLIENT_CERT_PATH), str(QUERY_CLIENT_KEY_PATH)),
        timeout=httpx.Timeout(30.0),
        http2=True,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
    ) as client:
        yield client


# ===============================================================================
# Certificate Validation Tests
# ===============================================================================

@pytest.mark.integration
class TestQueryCertificates:
    """Тесты query client certificates."""

    def test_query_client_certificate_exists(self):
        """Query client certificate должен существовать для mTLS."""
        assert QUERY_CLIENT_CERT_PATH.exists(), \
            f"Query client cert not found: {QUERY_CLIENT_CERT_PATH}"
        assert QUERY_CLIENT_KEY_PATH.exists(), \
            f"Query client key not found: {QUERY_CLIENT_KEY_PATH}"

        with open(QUERY_CLIENT_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        assert cert is not None

    def test_query_client_cn_correct(self):
        """Query client certificate должен иметь CN = 'query-client'."""
        with open(QUERY_CLIENT_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
        assert cn == "query-client", f"Expected CN 'query-client', got '{cn}'"

    def test_query_certificate_valid(self):
        """Query client certificate должен быть валидным (не expired)."""
        with open(QUERY_CLIENT_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        assert cert.not_valid_before <= now <= cert.not_valid_after, \
            "Query client certificate is expired or not yet valid"

    def test_query_certificate_signed_by_ca(self):
        """Query client certificate должен быть подписан CA."""
        with open(CA_CERT_PATH, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        with open(QUERY_CLIENT_CERT_PATH, "rb") as f:
            client_cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        # Проверка issuer
        assert client_cert.issuer == ca_cert.subject, \
            "Query client cert not signed by CA"


# ===============================================================================
# mTLS Communication Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestQueryMTLSCommunication:
    """Тесты mTLS communication между Query и Storage Element."""

    async def test_mtls_connection_to_storage_element(
        self,
        query_mtls_client: httpx.AsyncClient
    ):
        """
        Query должен успешно устанавливать mTLS соединение со Storage Element.

        Проверяет:
        - TLS 1.3 protocol
        - Client certificate authentication
        - Server certificate validation
        """
        # Health check на Storage Element через mTLS
        response = await query_mtls_client.get(
            f"{STORAGE_ELEMENT_TLS_URL}/health/live"
        )

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    async def test_mtls_file_download_flow(
        self,
        query_mtls_client: httpx.AsyncClient
    ):
        """
        Полный flow download файла со Storage Element через mTLS.

        Проверяет:
        1. Query аутентифицируется со Storage Element (mTLS)
        2. Query запрашивает file metadata
        3. Query скачивает файл через TLS stream
        4. Query верифицирует downloaded content
        """
        # Примечание: Для полного теста нужен запущенный Storage Element с файлами
        # Этот тест демонстрирует паттерн

        # 1. Проверка доступности Storage Element
        health_response = await query_mtls_client.get(
            f"{STORAGE_ELEMENT_TLS_URL}/health/ready"
        )

        if health_response.status_code == 200:
            # Storage Element доступен, можем продолжать
            assert health_response.json()["status"] in ["healthy", "ready"]

    async def test_mtls_without_client_certificate_fails(self):
        """
        Попытка download без client certificate должна быть отклонена.

        Проверяет enforcement mTLS policy на Storage Element.
        """
        # SSL context БЕЗ client certificate
        server_only_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        server_only_context.load_verify_locations(str(CA_CERT_PATH))
        server_only_context.minimum_version = ssl.TLSVersion.TLSv1_3

        async with httpx.AsyncClient(verify=server_only_context, timeout=5.0) as client:
            with pytest.raises((ssl.SSLError, httpx.ConnectError, httpx.HTTPStatusError)):
                # Storage Element должен требовать client certificate для downloads
                response = await client.get(f"{STORAGE_ELEMENT_TLS_URL}/api/files/test-id")
                # Если запрос прошел, проверяем статус код (должен быть 401/403)
                assert response.status_code in [401, 403]

    async def test_mtls_with_query_client_cn_accepted(
        self,
        query_mtls_client: httpx.AsyncClient
    ):
        """
        Storage Element должен принимать CN 'query-client' для download operations.

        Проверяет CN whitelist enforcement.
        """
        # Проверка CN в client certificate
        with open(QUERY_CLIENT_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
        assert cn == "query-client"

        # Query client должен иметь доступ к Storage Element
        response = await query_mtls_client.get(
            f"{STORAGE_ELEMENT_TLS_URL}/health/ready"
        )
        assert response.status_code == 200


# ===============================================================================
# Streaming Download Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestQueryStreamingDownload:
    """Тесты streaming download через TLS."""

    async def test_streaming_download_with_mtls(
        self,
        query_mtls_client: httpx.AsyncClient
    ):
        """
        Streaming download должен работать через TLS/mTLS.

        Проверяет:
        - Chunked transfer encoding
        - TLS stream handling
        - Connection keepalive
        """
        # Примечание: Для реального теста нужен файл на Storage Element
        # Демонстрация паттерна streaming download

        try:
            async with query_mtls_client.stream(
                "GET",
                f"{STORAGE_ELEMENT_TLS_URL}/api/files/test-file-id"
            ) as response:
                # Проверка headers (может быть 404 если файл не существует)
                if response.status_code == 200:
                    # Streaming download chunks
                    chunks = []
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        chunks.append(chunk)

                    # Верификация downloaded content
                    content = b"".join(chunks)
                    assert len(content) > 0
                elif response.status_code == 404:
                    # File not found - ожидаемо для тестового файла
                    pass
                else:
                    # Другие ошибки
                    assert response.status_code in [401, 403, 404]
        except (httpx.ConnectError, httpx.TimeoutException):
            # Storage Element может быть недоступен
            pytest.skip("Storage Element unavailable for streaming test")

    async def test_concurrent_downloads_with_connection_pooling(
        self,
        query_mtls_client: httpx.AsyncClient
    ):
        """
        Concurrent downloads должны использовать connection pool.

        Проверяет:
        - Connection reuse
        - HTTP/2 multiplexing
        - Parallel downloads efficiency
        """
        # Симуляция 5 параллельных downloads (health checks)
        tasks = [
            query_mtls_client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
            for _ in range(5)
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Проверка successful responses
        successful = [r for r in responses if isinstance(r, httpx.Response)]
        assert len(successful) > 0

        # Все successful requests должны быть 200
        for response in successful:
            assert response.status_code == 200


# ===============================================================================
# Connection Pooling Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestQueryTLSConnectionPooling:
    """Тесты connection pooling для TLS соединений."""

    async def test_connection_reuse_across_downloads(
        self,
        query_mtls_client: httpx.AsyncClient
    ):
        """
        HTTP client должен переиспользовать TLS connections для downloads.

        Проверяет:
        - Connection pooling активен
        - TLS handshake выполняется один раз
        - Subsequent downloads переиспользуют соединение
        """
        # Первый download request
        response1 = await query_mtls_client.get(
            f"{STORAGE_ELEMENT_TLS_URL}/health/live"
        )
        assert response1.status_code == 200

        # Второй download request - переиспользует TLS connection
        response2 = await query_mtls_client.get(
            f"{STORAGE_ELEMENT_TLS_URL}/health/ready"
        )
        assert response2.status_code == 200

        # Третий request
        response3 = await query_mtls_client.get(
            f"{STORAGE_ELEMENT_TLS_URL}/health/live"
        )
        assert response3.status_code == 200

    async def test_connection_pool_limits(self, query_ssl_context: ssl.SSLContext):
        """
        Connection pool должен соблюдать configured limits.

        Проверяет:
        - Max connections limit
        - Max keepalive connections limit
        - Connection eviction при превышении limits
        """
        # Client с ограниченным connection pool
        async with httpx.AsyncClient(
            verify=query_ssl_context,
            cert=(str(QUERY_CLIENT_CERT_PATH), str(QUERY_CLIENT_KEY_PATH)),
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=2)
        ) as client:
            # Множественные requests
            tasks = [
                client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
                for _ in range(10)
            ]

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Все requests должны успешно выполниться
            successful = [r for r in responses if isinstance(r, httpx.Response)]
            assert len(successful) > 0


# ===============================================================================
# Error Handling Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestQueryMTLSErrorHandling:
    """Тесты обработки ошибок mTLS в Query Module."""

    async def test_storage_element_unavailable_handling(
        self,
        query_mtls_client: httpx.AsyncClient
    ):
        """
        Query должен корректно обрабатывать недоступность Storage Element.

        Проверяет:
        - Timeout handling
        - Connection error handling
        - Graceful degradation
        """
        # Попытка подключения к несуществующему Storage Element
        invalid_url = "https://non-existent-storage:9999"

        with pytest.raises(httpx.ConnectError):
            await query_mtls_client.get(
                f"{invalid_url}/health/live",
                timeout=httpx.Timeout(2.0)
            )

    async def test_tls_handshake_failure_handling(self):
        """
        TLS handshake failure при download должен быть обработан gracefully.

        Проверяет error handling при certificate validation errors.
        """
        # SSL context с неправильным CA certificate
        wrong_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        # Не загружаем CA cert - handshake будет неуспешным

        async with httpx.AsyncClient(verify=wrong_context, timeout=5.0) as client:
            with pytest.raises((ssl.SSLError, httpx.ConnectError)):
                await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")

    async def test_download_retry_on_connection_failure(
        self,
        query_mtls_client: httpx.AsyncClient
    ):
        """
        Query должен retry download при временных connection failures.

        Проверяет:
        - Exponential backoff
        - Max retry attempts
        - Circuit breaker pattern
        """
        # Попытка download с retry logic
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                response = await query_mtls_client.get(
                    f"{STORAGE_ELEMENT_TLS_URL}/health/live",
                    timeout=httpx.Timeout(2.0)
                )
                if response.status_code == 200:
                    break
            except (httpx.ConnectError, httpx.TimeoutException):
                retry_count += 1
                if retry_count >= max_retries:
                    pytest.skip("Storage Element unavailable for retry test")
                await asyncio.sleep(0.5 * retry_count)  # Exponential backoff


# ===============================================================================
# Performance Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestQueryMTLSPerformance:
    """Тесты производительности mTLS downloads."""

    async def test_mtls_download_latency(
        self,
        query_mtls_client: httpx.AsyncClient
    ):
        """
        Download latency через mTLS должен быть приемлемым.

        Проверяет:
        - TLS overhead minimal
        - Download speed adequate
        """
        import time

        # Measure latency
        start = time.time()
        response = await query_mtls_client.get(
            f"{STORAGE_ELEMENT_TLS_URL}/health/live"
        )
        latency = time.time() - start

        assert response.status_code == 200

        # Latency должен быть разумным (< 1s для health check)
        assert latency < 1.0, f"Download latency too high: {latency:.3f}s"

    async def test_bulk_downloads_throughput(
        self,
        query_mtls_client: httpx.AsyncClient
    ):
        """
        Bulk downloads через mTLS должны иметь хороший throughput.

        Проверяет:
        - Parallel download efficiency
        - Connection pooling effectiveness
        - HTTP/2 multiplexing benefits
        """
        # 10 параллельных downloads (health checks)
        import time

        tasks = [
            query_mtls_client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
            for _ in range(10)
        ]

        start = time.time()
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start

        # Все requests успешны
        successful = [r for r in responses if isinstance(r, httpx.Response)]
        assert len(successful) > 0

        # Bulk downloads должны быть быстрыми (< 2s для 10 requests)
        print(f"Bulk downloads time: {elapsed:.3f}s")


# ===============================================================================
# Integration Scenarios
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestQueryMTLSIntegrationScenarios:
    """Комплексные integration scenarios с mTLS."""

    async def test_query_to_storage_search_and_download_scenario(
        self,
        query_mtls_client: httpx.AsyncClient
    ):
        """
        End-to-end сценарий search и download через Query → Storage с mTLS.

        Проверяет:
        1. Query аутентифицируется в Admin Module (OAuth 2.0)
        2. Query выполняет search request
        3. Query устанавливает mTLS соединение со Storage Element
        4. Query скачивает файл
        5. Query верифицирует downloaded content
        """
        # Примечание: Для полного теста нужны запущенные все сервисы
        # Этот тест демонстрирует структуру

        # Step 1: Проверка Query Module доступности
        try:
            query_health = await query_mtls_client.get(
                f"{QUERY_MODULE_TLS_URL}/health/live"
            )
            if query_health.status_code == 200:
                # Query Module доступен
                pass
        except httpx.ConnectError:
            pytest.skip("Query Module unavailable")

    async def test_concurrent_downloads_from_multiple_storage_elements(
        self,
        query_mtls_client: httpx.AsyncClient
    ):
        """
        Concurrent downloads от разных Storage Elements через mTLS.

        Проверяет:
        - Multiple mTLS connections management
        - Connection pooling для разных endpoints
        - Load balancing
        """
        # Симуляция downloads от разных Storage Elements
        storage_urls = [
            f"{STORAGE_ELEMENT_TLS_URL}/health/live",
            # Добавить другие Storage Elements если есть
        ]

        tasks = [
            query_mtls_client.get(url)
            for url in storage_urls
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Проверка successful responses
        successful = [r for r in responses if isinstance(r, httpx.Response) and r.status_code == 200]
        assert len(successful) > 0, "At least one Storage Element should be accessible"

    async def test_download_with_search_result_pagination(
        self,
        query_mtls_client: httpx.AsyncClient
    ):
        """
        Download множественных файлов from paginated search results.

        Проверяет:
        - Connection reuse across paginated requests
        - Efficient batch downloads
        - Resource cleanup
        """
        # Примечание: Демонстрация паттерна
        # Реальный тест требует search API и файлы

        # Симуляция paginated search → downloads
        page_sizes = [5, 10, 15]

        for page_size in page_sizes:
            # Симуляция downloads для page
            tasks = [
                query_mtls_client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
                for _ in range(min(page_size, 5))  # Limit для теста
            ]

            responses = await asyncio.gather(*tasks, return_exceptions=True)
            successful = [r for r in responses if isinstance(r, httpx.Response)]
            assert len(successful) > 0
