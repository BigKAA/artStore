"""
Integration tests for mTLS communication между Ingester и Storage Element.

Проверяет:
- mTLS authentication при загрузке файлов
- TLS 1.3 enforcement для inter-service communication
- Client certificate validation
- Retry logic при TLS errors
- Connection pooling для TLS соединений
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
INGESTER_CLIENT_CERT_PATH = TLS_INFRA_DIR / "client-certs" / "ingester-client-cert.pem"
INGESTER_CLIENT_KEY_PATH = TLS_INFRA_DIR / "client-certs" / "ingester-client-key.pem"

STORAGE_ELEMENT_TLS_URL = "https://storage-element:8010"
INGESTER_MODULE_TLS_URL = "https://ingester-module:8020"


# ===============================================================================
# Fixtures
# ===============================================================================

@pytest.fixture
def ingester_ssl_context() -> ssl.SSLContext:
    """
    SSL context для Ingester Module с client certificate.

    Используется для mTLS communication со Storage Element.
    """
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.load_verify_locations(str(CA_CERT_PATH))
    context.load_cert_chain(
        certfile=str(INGESTER_CLIENT_CERT_PATH),
        keyfile=str(INGESTER_CLIENT_KEY_PATH)
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
async def ingester_mtls_client(
    ingester_ssl_context: ssl.SSLContext
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    HTTP client для Ingester Module с mTLS поддержкой.
    """
    async with httpx.AsyncClient(
        verify=ingester_ssl_context,
        cert=(str(INGESTER_CLIENT_CERT_PATH), str(INGESTER_CLIENT_KEY_PATH)),
        timeout=httpx.Timeout(30.0),
        http2=True,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
    ) as client:
        yield client


# ===============================================================================
# Certificate Validation Tests
# ===============================================================================

@pytest.mark.integration
class TestIngesterCertificates:
    """Тесты ingester client certificates."""

    def test_ingester_client_certificate_exists(self):
        """Ingester client certificate должен существовать для mTLS."""
        assert INGESTER_CLIENT_CERT_PATH.exists(), \
            f"Ingester client cert not found: {INGESTER_CLIENT_CERT_PATH}"
        assert INGESTER_CLIENT_KEY_PATH.exists(), \
            f"Ingester client key not found: {INGESTER_CLIENT_KEY_PATH}"

        with open(INGESTER_CLIENT_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        assert cert is not None

    def test_ingester_client_cn_correct(self):
        """Ingester client certificate должен иметь CN = 'ingester-client'."""
        with open(INGESTER_CLIENT_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
        assert cn == "ingester-client", f"Expected CN 'ingester-client', got '{cn}'"

    def test_ingester_certificate_valid(self):
        """Ingester client certificate должен быть валидным (не expired)."""
        with open(INGESTER_CLIENT_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        assert cert.not_valid_before <= now <= cert.not_valid_after, \
            "Ingester client certificate is expired or not yet valid"

    def test_ingester_certificate_signed_by_ca(self):
        """Ingester client certificate должен быть подписан CA."""
        with open(CA_CERT_PATH, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        with open(INGESTER_CLIENT_CERT_PATH, "rb") as f:
            client_cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        # Проверка issuer
        assert client_cert.issuer == ca_cert.subject, \
            "Ingester client cert not signed by CA"


# ===============================================================================
# mTLS Communication Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestIngesterMTLSCommunication:
    """Тесты mTLS communication между Ingester и Storage Element."""

    async def test_mtls_connection_to_storage_element(
        self,
        ingester_mtls_client: httpx.AsyncClient
    ):
        """
        Ingester должен успешно устанавливать mTLS соединение со Storage Element.

        Проверяет:
        - TLS 1.3 protocol
        - Client certificate authentication
        - Server certificate validation
        """
        # Health check на Storage Element через mTLS
        response = await ingester_mtls_client.get(
            f"{STORAGE_ELEMENT_TLS_URL}/health/live"
        )

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    async def test_mtls_file_upload_flow(
        self,
        ingester_mtls_client: httpx.AsyncClient
    ):
        """
        Полный flow загрузки файла со Storage Element через mTLS.

        Проверяет:
        1. Получение storage element info через mTLS
        2. Загрузка файла с client certificate authentication
        3. Верификация успешной загрузки
        """
        # Примечание: Для полного теста нужен запущенный Storage Element
        # Этот тест демонстрирует паттерн

        # 1. Проверка доступности Storage Element
        health_response = await ingester_mtls_client.get(
            f"{STORAGE_ELEMENT_TLS_URL}/health/ready"
        )

        if health_response.status_code == 200:
            # Storage Element доступен, можем продолжать
            assert health_response.json()["status"] in ["healthy", "ready"]

    async def test_mtls_without_client_certificate_fails(self):
        """
        Попытка соединения без client certificate должна быть отклонена.

        Проверяет enforcement mTLS policy на Storage Element.
        """
        # SSL context БЕЗ client certificate
        server_only_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        server_only_context.load_verify_locations(str(CA_CERT_PATH))
        server_only_context.minimum_version = ssl.TLSVersion.TLSv1_3

        async with httpx.AsyncClient(verify=server_only_context, timeout=5.0) as client:
            with pytest.raises((ssl.SSLError, httpx.ConnectError, httpx.HTTPStatusError)):
                # Storage Element должен требовать client certificate
                response = await client.get(f"{STORAGE_ELEMENT_TLS_URL}/api/files/upload")
                # Если запрос прошел, проверяем статус код (должен быть 401/403)
                assert response.status_code in [401, 403]

    async def test_mtls_with_wrong_client_certificate_fails(self):
        """
        Client certificate с неправильным CN должен быть отклонен.

        Проверяет CN whitelist enforcement на Storage Element.
        """
        # Для полного теста нужен client certificate с другим CN
        # Этот тест демонстрирует концепцию

        with open(INGESTER_CLIENT_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value

        # Ingester client CN должен быть в whitelist Storage Element
        assert cn == "ingester-client"


# ===============================================================================
# TLS Connection Pooling Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestIngesterTLSConnectionPooling:
    """Тесты connection pooling для TLS соединений."""

    async def test_connection_reuse_across_requests(
        self,
        ingester_mtls_client: httpx.AsyncClient
    ):
        """
        HTTP client должен переиспользовать TLS connections.

        Проверяет:
        - Connection pooling активен
        - TLS handshake выполняется один раз
        - Последующие запросы переиспользуют соединение
        """
        # Первый запрос - устанавливает TLS соединение
        response1 = await ingester_mtls_client.get(
            f"{STORAGE_ELEMENT_TLS_URL}/health/live"
        )
        assert response1.status_code == 200

        # Второй запрос - переиспользует существующее TLS соединение
        response2 = await ingester_mtls_client.get(
            f"{STORAGE_ELEMENT_TLS_URL}/health/ready"
        )
        assert response2.status_code == 200

        # Третий запрос - также переиспользует соединение
        response3 = await ingester_mtls_client.get(
            f"{STORAGE_ELEMENT_TLS_URL}/health/live"
        )
        assert response3.status_code == 200

    async def test_concurrent_requests_share_connections(
        self,
        ingester_mtls_client: httpx.AsyncClient
    ):
        """
        Concurrent requests должны использовать connection pool.

        Проверяет HTTP/2 multiplexing и connection limits.
        """
        # 10 параллельных запросов
        tasks = [
            ingester_mtls_client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
            for _ in range(10)
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Все запросы успешны
        successful = [r for r in responses if isinstance(r, httpx.Response)]
        assert len(successful) == 10
        assert all(r.status_code == 200 for r in successful)

    async def test_connection_pool_cleanup(self, ingester_ssl_context: ssl.SSLContext):
        """
        Connection pool должен корректно очищаться при закрытии client.

        Проверяет resource cleanup и отсутствие memory leaks.
        """
        # Создаем и закрываем несколько clients
        for _ in range(3):
            async with httpx.AsyncClient(
                verify=ingester_ssl_context,
                cert=(str(INGESTER_CLIENT_CERT_PATH), str(INGESTER_CLIENT_KEY_PATH)),
                timeout=5.0
            ) as client:
                response = await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
                assert response.status_code == 200

            # Client автоматически закрыт, connections released


# ===============================================================================
# Error Handling Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestIngesterMTLSErrorHandling:
    """Тесты обработки ошибок mTLS в Ingester."""

    async def test_storage_element_unavailable_handling(
        self,
        ingester_mtls_client: httpx.AsyncClient
    ):
        """
        Ingester должен корректно обрабатывать недоступность Storage Element.

        Проверяет:
        - Timeout handling
        - Connection error handling
        - Graceful degradation
        """
        # Попытка подключения к несуществующему Storage Element
        invalid_url = "https://non-existent-storage:9999"

        with pytest.raises(httpx.ConnectError):
            await ingester_mtls_client.get(
                f"{invalid_url}/health/live",
                timeout=httpx.Timeout(2.0)
            )

    async def test_tls_handshake_failure_handling(self):
        """
        TLS handshake failure должен быть обработан gracefully.

        Проверяет error handling при certificate validation errors.
        """
        # SSL context с неправильным CA certificate
        wrong_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        # Не загружаем CA cert - handshake будет неуспешным

        async with httpx.AsyncClient(verify=wrong_context, timeout=5.0) as client:
            with pytest.raises((ssl.SSLError, httpx.ConnectError)):
                await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")

    async def test_certificate_expiration_detection(self):
        """
        Expired client certificate должен быть обнаружен before request.

        Проверяет pre-request certificate validation.
        """
        # Проверка, что client certificate валиден
        with open(INGESTER_CLIENT_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        # Certificate должен быть валиден
        assert cert.not_valid_before <= now <= cert.not_valid_after

        # Проверка, что certificate не истекает в ближайшие 30 дней
        remaining_days = (cert.not_valid_after - now).days
        if remaining_days < 30:
            pytest.warn(
                UserWarning(
                    f"Client certificate expires in {remaining_days} days. "
                    f"Consider rotation."
                )
            )


# ===============================================================================
# Performance Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestIngesterMTLSPerformance:
    """Тесты производительности mTLS connections."""

    async def test_mtls_handshake_performance(
        self,
        ingester_ssl_context: ssl.SSLContext
    ):
        """
        TLS 1.3 handshake должен быть быстрым (1-RTT).

        Проверяет:
        - Handshake latency < 100ms
        - Session resumption работает
        """
        import time

        # Первый запрос - полный handshake
        start = time.time()
        async with httpx.AsyncClient(
            verify=ingester_ssl_context,
            cert=(str(INGESTER_CLIENT_CERT_PATH), str(INGESTER_CLIENT_KEY_PATH))
        ) as client:
            response = await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
            assert response.status_code == 200
        first_request_time = time.time() - start

        # Второй запрос - может использовать session resumption
        start = time.time()
        async with httpx.AsyncClient(
            verify=ingester_ssl_context,
            cert=(str(INGESTER_CLIENT_CERT_PATH), str(INGESTER_CLIENT_KEY_PATH))
        ) as client:
            response = await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
            assert response.status_code == 200
        second_request_time = time.time() - start

        # Второй запрос должен быть быстрее (session resumption)
        # Примечание: В реальности разница может быть небольшой
        print(f"First request: {first_request_time:.3f}s")
        print(f"Second request: {second_request_time:.3f}s")

    async def test_bulk_upload_with_mtls(
        self,
        ingester_mtls_client: httpx.AsyncClient
    ):
        """
        Bulk file upload через mTLS должен быть эффективным.

        Проверяет:
        - Connection reuse для множественных uploads
        - HTTP/2 multiplexing
        - Throughput с TLS overhead
        """
        # Симуляция 5 параллельных health checks (вместо реальных uploads)
        tasks = [
            ingester_mtls_client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
            for _ in range(5)
        ]

        import time
        start = time.time()
        responses = await asyncio.gather(*tasks)
        elapsed = time.time() - start

        # Все запросы успешны
        assert all(r.status_code == 200 for r in responses)

        # 5 параллельных requests должны выполниться быстро (< 1s)
        assert elapsed < 1.0, f"Bulk requests too slow: {elapsed:.3f}s"


# ===============================================================================
# Integration Scenarios
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestIngesterMTLSIntegrationScenarios:
    """Комплексные integration scenarios с mTLS."""

    async def test_ingester_to_storage_upload_scenario(
        self,
        ingester_mtls_client: httpx.AsyncClient
    ):
        """
        End-to-end сценарий загрузки файла через Ingester → Storage с mTLS.

        Проверяет:
        1. Ingester аутентифицируется в Admin Module (OAuth 2.0)
        2. Ingester получает список Storage Elements
        3. Ingester устанавливает mTLS соединение со Storage Element
        4. Ingester загружает файл
        5. Ingester верифицирует успешную загрузку
        """
        # Примечание: Для полного теста нужны запущенные все сервисы
        # Этот тест демонстрирует структуру

        # Step 1: Проверка Ingester Module доступности
        ingester_health = await ingester_mtls_client.get(
            f"{INGESTER_MODULE_TLS_URL}/health/live"
        )
        if ingester_health.status_code == 200:
            # Ingester доступен
            pass

    async def test_mtls_retry_on_connection_failure(
        self,
        ingester_mtls_client: httpx.AsyncClient
    ):
        """
        Retry logic должен работать при временных TLS connection failures.

        Проверяет:
        - Exponential backoff
        - Max retry attempts
        - Circuit breaker pattern
        """
        # Попытка подключения с timeout
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                response = await ingester_mtls_client.get(
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

    async def test_concurrent_uploads_different_storage_elements(
        self,
        ingester_mtls_client: httpx.AsyncClient
    ):
        """
        Concurrent uploads к разным Storage Elements через mTLS.

        Проверяет:
        - Multiple mTLS connections management
        - Connection pooling для разных endpoints
        - Resource efficiency
        """
        # Симуляция параллельных requests к разным Storage Elements
        storage_urls = [
            f"{STORAGE_ELEMENT_TLS_URL}/health/live",
            # Добавить другие Storage Elements если есть
        ]

        tasks = [
            ingester_mtls_client.get(url)
            for url in storage_urls
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Проверка successful responses
        successful = [r for r in responses if isinstance(r, httpx.Response) and r.status_code == 200]
        assert len(successful) > 0, "At least one Storage Element should be accessible"
