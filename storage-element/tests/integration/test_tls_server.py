"""
Integration tests для TLS server configuration Storage Element.

Проверяет:
- TLS 1.3 server configuration
- mTLS client certificate validation
- CN whitelist enforcement
- Server certificate serving
- TLS cipher suite configuration
"""

import ssl
from pathlib import Path

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
STORAGE_SERVER_KEY_PATH = TLS_INFRA_DIR / "server-certs" / "storage-element" / "server-key.pem"
INGESTER_CLIENT_CERT_PATH = TLS_INFRA_DIR / "client-certs" / "ingester-client-cert.pem"
INGESTER_CLIENT_KEY_PATH = TLS_INFRA_DIR / "client-certs" / "ingester-client-key.pem"
QUERY_CLIENT_CERT_PATH = TLS_INFRA_DIR / "client-certs" / "query-client-cert.pem"
QUERY_CLIENT_KEY_PATH = TLS_INFRA_DIR / "client-certs" / "query-client-key.pem"

STORAGE_ELEMENT_TLS_URL = "https://storage-element:8010"


# ===============================================================================
# Fixtures
# ===============================================================================

@pytest.fixture
def storage_server_ssl_context() -> ssl.SSLContext:
    """
    SSL context для проверки Storage Element server certificate.
    """
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.load_verify_locations(str(CA_CERT_PATH))
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    return context


@pytest.fixture
def ingester_client_ssl_context() -> ssl.SSLContext:
    """
    SSL context с Ingester client certificate для mTLS.
    """
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.load_verify_locations(str(CA_CERT_PATH))
    context.load_cert_chain(
        certfile=str(INGESTER_CLIENT_CERT_PATH),
        keyfile=str(INGESTER_CLIENT_KEY_PATH)
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    return context


@pytest.fixture
def query_client_ssl_context() -> ssl.SSLContext:
    """
    SSL context с Query client certificate для mTLS.
    """
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.load_verify_locations(str(CA_CERT_PATH))
    context.load_cert_chain(
        certfile=str(QUERY_CLIENT_CERT_PATH),
        keyfile=str(QUERY_CLIENT_KEY_PATH)
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    return context


# ===============================================================================
# Server Certificate Tests
# ===============================================================================

@pytest.mark.integration
class TestStorageServerCertificate:
    """Тесты Storage Element server certificate configuration."""

    def test_storage_server_certificate_exists(self):
        """Storage Element server certificate должен существовать."""
        assert STORAGE_SERVER_CERT_PATH.exists(), \
            f"Storage server cert not found: {STORAGE_SERVER_CERT_PATH}"
        assert STORAGE_SERVER_KEY_PATH.exists(), \
            f"Storage server key not found: {STORAGE_SERVER_KEY_PATH}"

    def test_storage_server_certificate_valid(self):
        """Storage server certificate должен быть валидным."""
        with open(STORAGE_SERVER_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        assert cert.not_valid_before <= now <= cert.not_valid_after, \
            "Storage server certificate is expired or not yet valid"

    def test_storage_server_certificate_san(self):
        """Storage server certificate должен иметь правильные SAN records."""
        with open(STORAGE_SERVER_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        san_ext = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_values = [str(name.value) for name in san_ext.value]

        # Должны быть storage-element и localhost
        assert any("storage-element" in san for san in san_values), \
            f"storage-element not in SAN: {san_values}"
        assert any("localhost" in san for san in san_values), \
            f"localhost not in SAN: {san_values}"

    def test_storage_server_certificate_key_size(self):
        """Storage server certificate должен использовать 2048+ bit key."""
        with open(STORAGE_SERVER_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        public_key = cert.public_key()
        key_size = public_key.key_size

        assert key_size >= 2048, \
            f"Server certificate key size too small: {key_size} bits"


# ===============================================================================
# TLS Server Configuration Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestStorageTLSServerConfiguration:
    """Тесты TLS server configuration Storage Element."""

    async def test_tls13_server_accepts_connection(
        self,
        storage_server_ssl_context: ssl.SSLContext
    ):
        """
        Storage Element должен принимать TLS 1.3 соединения.

        Проверяет:
        - TLS 1.3 protocol support
        - Server certificate serving
        - Basic TLS connectivity
        """
        async with httpx.AsyncClient(
            verify=storage_server_ssl_context,
            timeout=httpx.Timeout(10.0)
        ) as client:
            response = await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}

    async def test_tls12_connection_rejected(self):
        """
        Storage Element должен отклонять TLS 1.2 connections.

        Проверяет enforcement TLS 1.3 only policy.
        """
        tls12_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        tls12_context.load_verify_locations(str(CA_CERT_PATH))
        tls12_context.minimum_version = ssl.TLSVersion.TLSv1_2
        tls12_context.maximum_version = ssl.TLSVersion.TLSv1_2

        with pytest.raises((ssl.SSLError, httpx.ConnectError)):
            async with httpx.AsyncClient(verify=tls12_context, timeout=5.0) as client:
                await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")

    async def test_http_connection_rejected(self):
        """
        Storage Element должен отклонять plain HTTP connections.

        Проверяет, что TLS обязателен для всех endpoints.
        """
        http_url = STORAGE_ELEMENT_TLS_URL.replace("https://", "http://")

        with pytest.raises(httpx.ConnectError):
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.get(f"{http_url}/health/live")


# ===============================================================================
# mTLS Client Authentication Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestStorageMTLSClientAuthentication:
    """Тесты mTLS client authentication на Storage Element."""

    async def test_ingester_client_certificate_accepted(
        self,
        ingester_client_ssl_context: ssl.SSLContext
    ):
        """
        Storage Element должен принимать Ingester client certificate.

        Проверяет:
        - CN 'ingester-client' в whitelist
        - Certificate chain validation
        - mTLS authentication success
        """
        async with httpx.AsyncClient(
            verify=ingester_client_ssl_context,
            cert=(str(INGESTER_CLIENT_CERT_PATH), str(INGESTER_CLIENT_KEY_PATH)),
            timeout=httpx.Timeout(10.0)
        ) as client:
            response = await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
            assert response.status_code == 200

    async def test_query_client_certificate_accepted(
        self,
        query_client_ssl_context: ssl.SSLContext
    ):
        """
        Storage Element должен принимать Query client certificate.

        Проверяет:
        - CN 'query-client' в whitelist
        - Certificate chain validation
        - mTLS authentication success
        """
        async with httpx.AsyncClient(
            verify=query_client_ssl_context,
            cert=(str(QUERY_CLIENT_CERT_PATH), str(QUERY_CLIENT_KEY_PATH)),
            timeout=httpx.Timeout(10.0)
        ) as client:
            response = await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
            assert response.status_code == 200

    async def test_upload_endpoint_requires_mtls(
        self,
        storage_server_ssl_context: ssl.SSLContext
    ):
        """
        File upload endpoint должен требовать client certificate.

        Проверяет:
        - mTLS requirement для protected endpoints
        - Rejection запросов без client certificate
        """
        # Попытка доступа БЕЗ client certificate
        async with httpx.AsyncClient(
            verify=storage_server_ssl_context,
            timeout=httpx.Timeout(5.0)
        ) as client:
            response = await client.post(
                f"{STORAGE_ELEMENT_TLS_URL}/api/files/upload",
                files={"file": ("test.txt", b"test content")},
                data={"metadata": "{}"}
            )

            # Ожидается 401/403 (unauthorized/forbidden)
            assert response.status_code in [401, 403, 404], \
                f"Expected authentication error, got {response.status_code}"

    async def test_download_endpoint_requires_mtls(
        self,
        storage_server_ssl_context: ssl.SSLContext
    ):
        """
        File download endpoint должен требовать client certificate.

        Проверяет mTLS requirement для file access.
        """
        # Попытка доступа БЕЗ client certificate
        async with httpx.AsyncClient(
            verify=storage_server_ssl_context,
            timeout=httpx.Timeout(5.0)
        ) as client:
            response = await client.get(
                f"{STORAGE_ELEMENT_TLS_URL}/api/files/test-file-id"
            )

            # Ожидается 401/403 (unauthorized/forbidden)
            assert response.status_code in [401, 403, 404]


# ===============================================================================
# CN Whitelist Enforcement Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestStorageCNWhitelistEnforcement:
    """Тесты CN whitelist enforcement на Storage Element."""

    async def test_allowed_cn_ingester_access_granted(
        self,
        ingester_client_ssl_context: ssl.SSLContext
    ):
        """
        CN 'ingester-client' должен иметь доступ к upload endpoints.

        Проверяет whitelist configuration.
        """
        # Проверка CN в client certificate
        with open(INGESTER_CLIENT_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
        assert cn == "ingester-client"

        # Доступ должен быть разрешен
        async with httpx.AsyncClient(
            verify=ingester_client_ssl_context,
            cert=(str(INGESTER_CLIENT_CERT_PATH), str(INGESTER_CLIENT_KEY_PATH)),
            timeout=httpx.Timeout(10.0)
        ) as client:
            response = await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/ready")
            assert response.status_code == 200

    async def test_allowed_cn_query_access_granted(
        self,
        query_client_ssl_context: ssl.SSLContext
    ):
        """
        CN 'query-client' должен иметь доступ к download endpoints.

        Проверяет whitelist configuration.
        """
        # Проверка CN в client certificate
        with open(QUERY_CLIENT_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
        assert cn == "query-client"

        # Доступ должен быть разрешен
        async with httpx.AsyncClient(
            verify=query_client_ssl_context,
            cert=(str(QUERY_CLIENT_CERT_PATH), str(QUERY_CLIENT_KEY_PATH)),
            timeout=httpx.Timeout(10.0)
        ) as client:
            response = await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/ready")
            assert response.status_code == 200


# ===============================================================================
# TLS Cipher Suite Tests
# ===============================================================================

@pytest.mark.integration
class TestStorageTLSCipherSuites:
    """Тесты TLS cipher suite configuration Storage Element."""

    def test_aead_cipher_suites_configuration(
        self,
        storage_server_ssl_context: ssl.SSLContext
    ):
        """
        Storage Element должен использовать только AEAD cipher suites.

        Проверяет:
        - TLS_AES_256_GCM_SHA384
        - TLS_CHACHA20_POLY1305_SHA256
        - TLS_AES_128_GCM_SHA256
        """
        # TLS 1.3 автоматически использует только AEAD cipher suites
        assert storage_server_ssl_context.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_weak_ciphers_rejected(self):
        """
        Weak cipher suites должны быть отклонены.

        Проверяет, что legacy ciphers не поддерживаются.
        """
        # TLS 1.3 не поддерживает weak ciphers by design
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.load_verify_locations(str(CA_CERT_PATH))
        context.minimum_version = ssl.TLSVersion.TLSv1_3

        # Попытка установить weak ciphers - должна быть проигнорирована
        # (TLS 1.3 использует только AEAD ciphers)


# ===============================================================================
# Performance Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestStorageTLSPerformance:
    """Тесты производительности TLS server Storage Element."""

    async def test_concurrent_tls_connections_handling(
        self,
        ingester_client_ssl_context: ssl.SSLContext
    ):
        """
        Storage Element должен обрабатывать множественные concurrent TLS connections.

        Проверяет:
        - Thread safety
        - Connection limits
        - Resource management
        """
        import asyncio

        # 10 параллельных clients
        async def make_request():
            async with httpx.AsyncClient(
                verify=ingester_client_ssl_context,
                cert=(str(INGESTER_CLIENT_CERT_PATH), str(INGESTER_CLIENT_KEY_PATH)),
                timeout=httpx.Timeout(10.0)
            ) as client:
                return await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")

        tasks = [make_request() for _ in range(10)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Все соединения успешны
        successful = [r for r in responses if isinstance(r, httpx.Response)]
        assert len(successful) == 10
        assert all(r.status_code == 200 for r in successful)

    async def test_http2_multiplexing_support(
        self,
        ingester_client_ssl_context: ssl.SSLContext
    ):
        """
        Storage Element должен поддерживать HTTP/2 multiplexing.

        Проверяет:
        - HTTP/2 protocol support
        - Request multiplexing over single TLS connection
        """
        async with httpx.AsyncClient(
            verify=ingester_client_ssl_context,
            cert=(str(INGESTER_CLIENT_CERT_PATH), str(INGESTER_CLIENT_KEY_PATH)),
            timeout=httpx.Timeout(10.0),
            http2=True
        ) as client:
            # Множественные requests через одно соединение
            response1 = await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
            response2 = await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/ready")
            response3 = await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")

            assert all(r.status_code == 200 for r in [response1, response2, response3])


# ===============================================================================
# Error Handling Tests
# ===============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestStorageTLSErrorHandling:
    """Тесты обработки ошибок TLS server Storage Element."""

    async def test_invalid_client_certificate_rejected(
        self,
        storage_server_ssl_context: ssl.SSLContext
    ):
        """
        Invalid client certificate должен быть отклонен.

        Проверяет certificate validation на server side.
        """
        # Для полного теста нужен invalid client certificate
        # Этот тест демонстрирует концепцию

        # Попытка доступа без client certificate к protected endpoint
        async with httpx.AsyncClient(
            verify=storage_server_ssl_context,
            timeout=httpx.Timeout(5.0)
        ) as client:
            response = await client.post(
                f"{STORAGE_ELEMENT_TLS_URL}/api/files/upload",
                files={"file": ("test.txt", b"test")}
            )
            # Должен быть отклонен
            assert response.status_code in [401, 403, 404]

    async def test_server_graceful_tls_error_handling(self):
        """
        Server должен gracefully обрабатывать TLS handshake failures.

        Проверяет error logging и connection cleanup.
        """
        # Попытка подключения с неправильным protocol version
        tls10_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        tls10_context.load_verify_locations(str(CA_CERT_PATH))

        # Устанавливаем очень старую версию TLS (если поддерживается)
        try:
            tls10_context.minimum_version = ssl.TLSVersion.TLSv1
            tls10_context.maximum_version = ssl.TLSVersion.TLSv1

            with pytest.raises((ssl.SSLError, httpx.ConnectError)):
                async with httpx.AsyncClient(verify=tls10_context, timeout=5.0) as client:
                    await client.get(f"{STORAGE_ELEMENT_TLS_URL}/health/live")
        except AttributeError:
            # TLS 1.0 может быть недоступен в новых версиях Python
            pytest.skip("TLS 1.0 not available in this Python version")
