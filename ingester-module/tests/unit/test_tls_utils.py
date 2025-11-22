"""
Unit tests для TLS utilities.

Sprint 22 Phase 2: Comprehensive test coverage для mTLS configuration utils.
Target: 85%+ statement coverage.
"""

import ssl
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.tls_utils import create_ssl_context


@pytest.fixture
def mock_tls_settings_disabled():
    """
    Mock TLS settings with TLS disabled.

    Returns:
        MagicMock: Settings object with TLS disabled
    """
    settings = MagicMock()
    settings.tls.enabled = False
    return settings


@pytest.fixture
def mock_tls_settings_full_mtls(tmp_path):
    """
    Mock TLS settings with full mTLS configuration.

    Creates temporary certificate files для тестирования.

    Args:
        tmp_path: Pytest temporary directory fixture

    Returns:
        MagicMock: Settings with full mTLS config
    """
    # Create temporary certificate files
    ca_cert = tmp_path / "ca-cert.pem"
    client_cert = tmp_path / "client-cert.pem"
    client_key = tmp_path / "client-key.pem"

    # Write minimal PEM content (not real certs, just for file existence)
    ca_cert.write_text("-----BEGIN CERTIFICATE-----\nFAKE CA CERT\n-----END CERTIFICATE-----")
    client_cert.write_text("-----BEGIN CERTIFICATE-----\nFAKE CLIENT CERT\n-----END CERTIFICATE-----")
    client_key.write_text("-----BEGIN PRIVATE KEY-----\nFAKE KEY\n-----END PRIVATE KEY-----")

    settings = MagicMock()
    settings.tls.enabled = True
    settings.tls.ca_cert_file = str(ca_cert)
    settings.tls.cert_file = str(client_cert)
    settings.tls.key_file = str(client_key)
    settings.tls.protocol_version = "TLSv1.3"
    settings.tls.ciphers = "TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256"

    return settings


@pytest.fixture
def mock_tls_settings_ca_only(tmp_path):
    """
    Mock TLS settings with only CA certificate (no client cert).

    Args:
        tmp_path: Pytest temporary directory fixture

    Returns:
        MagicMock: Settings with CA cert only
    """
    ca_cert = tmp_path / "ca-cert.pem"
    ca_cert.write_text("-----BEGIN CERTIFICATE-----\nFAKE CA CERT\n-----END CERTIFICATE-----")

    settings = MagicMock()
    settings.tls.enabled = True
    settings.tls.ca_cert_file = str(ca_cert)
    settings.tls.cert_file = None
    settings.tls.key_file = None
    settings.tls.protocol_version = "TLSv1.3"
    settings.tls.ciphers = None

    return settings


@pytest.fixture
def mock_tls_settings_client_only(tmp_path):
    """
    Mock TLS settings with only client certificate (no CA cert).

    Args:
        tmp_path: Pytest temporary directory fixture

    Returns:
        MagicMock: Settings with client cert only
    """
    client_cert = tmp_path / "client-cert.pem"
    client_key = tmp_path / "client-key.pem"

    client_cert.write_text("-----BEGIN CERTIFICATE-----\nFAKE CLIENT CERT\n-----END CERTIFICATE-----")
    client_key.write_text("-----BEGIN PRIVATE KEY-----\nFAKE KEY\n-----END PRIVATE KEY-----")

    settings = MagicMock()
    settings.tls.enabled = True
    settings.tls.ca_cert_file = None
    settings.tls.cert_file = str(client_cert)
    settings.tls.key_file = str(client_key)
    settings.tls.protocol_version = "TLSv1.2"
    settings.tls.ciphers = None

    return settings


# ================================================================================
# TLS Disabled Scenarios
# ================================================================================

def test_create_ssl_context_when_tls_disabled(mock_tls_settings_disabled):
    """
    Test SSL context creation when TLS is disabled.

    Scenario: TLS_ENABLED=false в конфигурации
    Expected: Returns None, no SSL context created
    """
    with patch('app.core.tls_utils.settings', mock_tls_settings_disabled):
        context = create_ssl_context()

        # Verify no context created
        assert context is None


# ================================================================================
# Full mTLS Configuration
# ================================================================================

def test_create_ssl_context_full_mtls(mock_tls_settings_full_mtls):
    """
    Test SSL context creation with full mTLS configuration.

    Scenario: TLS enabled с CA cert + client cert + TLS 1.3 + custom ciphers
    Expected: SSL context created with all security features
    """
    with patch('app.core.tls_utils.settings', mock_tls_settings_full_mtls):
        # Mock SSL operations to avoid real certificate validation
        with patch('ssl.create_default_context') as mock_create_context:

            mock_context = MagicMock()  # Don't spec with already-mocked SSLContext
            mock_create_context.return_value = mock_context

            context = create_ssl_context()

            # Verify context created
            assert context is not None
            assert context == mock_context

            # Verify SSL context created with SERVER_AUTH purpose
            mock_create_context.assert_called_once_with(ssl.Purpose.SERVER_AUTH)

            # Verify CA certificate loaded
            mock_context.load_verify_locations.assert_called_once_with(
                cafile=mock_tls_settings_full_mtls.tls.ca_cert_file
            )

            # Verify client certificate loaded
            mock_context.load_cert_chain.assert_called_once_with(
                certfile=mock_tls_settings_full_mtls.tls.cert_file,
                keyfile=mock_tls_settings_full_mtls.tls.key_file
            )

            # Verify TLS 1.3 configured
            assert mock_context.minimum_version == ssl.TLSVersion.TLSv1_3

            # Verify cipher suites configured
            mock_context.set_ciphers.assert_called_once_with(
                mock_tls_settings_full_mtls.tls.ciphers
            )


# ================================================================================
# Partial Certificate Configurations
# ================================================================================

def test_create_ssl_context_ca_certificate_only(mock_tls_settings_ca_only):
    """
    Test SSL context with only CA certificate (no client cert).

    Scenario: Server validation enabled, mTLS disabled
    Expected: SSL context created, CA loaded, no client cert, warning logged
    """
    with patch('app.core.tls_utils.settings', mock_tls_settings_ca_only):
        with patch('ssl.create_default_context') as mock_create_context:
            mock_context = MagicMock(spec=ssl.SSLContext)
            mock_create_context.return_value = mock_context

            context = create_ssl_context()

            # Verify context created
            assert context is not None

            # Verify CA certificate loaded
            mock_context.load_verify_locations.assert_called_once()

            # Verify NO client certificate loaded
            mock_context.load_cert_chain.assert_not_called()

            # Verify TLS 1.3 configured
            assert mock_context.minimum_version == ssl.TLSVersion.TLSv1_3


def test_create_ssl_context_client_certificate_only(mock_tls_settings_client_only):
    """
    Test SSL context with only client certificate (no CA cert).

    Scenario: mTLS enabled, server validation disabled (insecure!)
    Expected: SSL context created, client cert loaded, no CA, warning logged
    """
    with patch('app.core.tls_utils.settings', mock_tls_settings_client_only):
        with patch('ssl.create_default_context') as mock_create_context:
            mock_context = MagicMock(spec=ssl.SSLContext)
            mock_create_context.return_value = mock_context

            context = create_ssl_context()

            # Verify context created
            assert context is not None

            # Verify NO CA certificate loaded
            mock_context.load_verify_locations.assert_not_called()

            # Verify client certificate loaded
            mock_context.load_cert_chain.assert_called_once()

            # Verify TLS 1.2 configured
            assert mock_context.minimum_version == ssl.TLSVersion.TLSv1_2


# ================================================================================
# TLS Protocol Version Tests
# ================================================================================

def test_create_ssl_context_tls_v1_3(mock_tls_settings_full_mtls):
    """
    Test SSL context with TLS 1.3 protocol version.

    Scenario: TLS_PROTOCOL_VERSION=TLSv1.3
    Expected: minimum_version set to TLSv1_3
    """
    mock_tls_settings_full_mtls.tls.protocol_version = "TLSv1.3"

    with patch('app.core.tls_utils.settings', mock_tls_settings_full_mtls):
        with patch('ssl.create_default_context') as mock_create_context:
            mock_context = MagicMock(spec=ssl.SSLContext)
            mock_create_context.return_value = mock_context

            create_ssl_context()

            # Verify TLS 1.3 minimum version
            assert mock_context.minimum_version == ssl.TLSVersion.TLSv1_3


def test_create_ssl_context_tls_v1_2(mock_tls_settings_client_only):
    """
    Test SSL context with TLS 1.2 protocol version.

    Scenario: TLS_PROTOCOL_VERSION=TLSv1.2
    Expected: minimum_version set to TLSv1_2
    """
    mock_tls_settings_client_only.tls.protocol_version = "TLSv1.2"

    with patch('app.core.tls_utils.settings', mock_tls_settings_client_only):
        with patch('ssl.create_default_context') as mock_create_context:
            mock_context = MagicMock(spec=ssl.SSLContext)
            mock_create_context.return_value = mock_context

            create_ssl_context()

            # Verify TLS 1.2 minimum version
            assert mock_context.minimum_version == ssl.TLSVersion.TLSv1_2


def test_create_ssl_context_unknown_protocol_version(mock_tls_settings_ca_only):
    """
    Test SSL context with unknown TLS protocol version.

    Scenario: TLS_PROTOCOL_VERSION=TLSv2.0 (invalid)
    Expected: Warning logged, default TLS version used
    """
    mock_tls_settings_ca_only.tls.protocol_version = "TLSv2.0"

    with patch('app.core.tls_utils.settings', mock_tls_settings_ca_only):
        with patch('ssl.create_default_context') as mock_create_context:
            mock_context = MagicMock(spec=ssl.SSLContext)
            mock_create_context.return_value = mock_context

            context = create_ssl_context()

            # Verify context still created despite unknown version
            assert context is not None

            # minimum_version не устанавливается для unknown protocol
            # (остается default TLS 1.2+)


# ================================================================================
# Cipher Suite Tests
# ================================================================================

def test_create_ssl_context_with_custom_ciphers(mock_tls_settings_full_mtls):
    """
    Test SSL context with custom cipher suites.

    Scenario: TLS_CIPHERS configured with AEAD ciphers
    Expected: Cipher suites set successfully
    """
    cipher_string = "TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256"
    mock_tls_settings_full_mtls.tls.ciphers = cipher_string

    with patch('app.core.tls_utils.settings', mock_tls_settings_full_mtls):
        with patch('ssl.create_default_context') as mock_create_context:
            mock_context = MagicMock(spec=ssl.SSLContext)
            mock_create_context.return_value = mock_context

            create_ssl_context()

            # Verify ciphers configured
            mock_context.set_ciphers.assert_called_once_with(cipher_string)


def test_create_ssl_context_invalid_ciphers(mock_tls_settings_full_mtls):
    """
    Test SSL context with invalid cipher suites.

    Scenario: TLS_CIPHERS содержит некорректные cipher suites
    Expected: SSLError caught, warning logged, default ciphers используются
    """
    mock_tls_settings_full_mtls.tls.ciphers = "INVALID_CIPHER_SUITE"

    with patch('app.core.tls_utils.settings', mock_tls_settings_full_mtls):
        with patch('ssl.create_default_context') as mock_create_context:
            mock_context = MagicMock(spec=ssl.SSLContext)
            mock_create_context.return_value = mock_context

            # Simulate SSLError when setting invalid ciphers
            mock_context.set_ciphers.side_effect = ssl.SSLError("Invalid cipher suite")

            context = create_ssl_context()

            # Verify context still created despite cipher error
            assert context is not None

            # Verify set_ciphers was attempted
            mock_context.set_ciphers.assert_called_once()


# ================================================================================
# Missing Configuration Tests
# ================================================================================

def test_create_ssl_context_no_certificates():
    """
    Test SSL context when TLS enabled but no certificates configured.

    Scenario: TLS_ENABLED=true но нет cert/key/ca файлов
    Expected: SSL context created, warnings logged о missing certs
    """
    settings = MagicMock()
    settings.tls.enabled = True
    settings.tls.ca_cert_file = None
    settings.tls.cert_file = None
    settings.tls.key_file = None
    settings.tls.protocol_version = "TLSv1.3"
    settings.tls.ciphers = None

    with patch('app.core.tls_utils.settings', settings):
        with patch('ssl.create_default_context') as mock_create_context:
            mock_context = MagicMock(spec=ssl.SSLContext)
            mock_create_context.return_value = mock_context

            context = create_ssl_context()

            # Verify context created (но insecure без certs)
            assert context is not None

            # Verify NO certificates loaded
            mock_context.load_verify_locations.assert_not_called()
            mock_context.load_cert_chain.assert_not_called()

            # TLS 1.3 все равно настроен
            assert mock_context.minimum_version == ssl.TLSVersion.TLSv1_3
