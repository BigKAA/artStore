"""
TLS/mTLS utility functions для Ingester Module.

Централизованная конфигурация TLS 1.3 и mutual TLS authentication
для всех inter-service HTTP connections (Ingester → Admin Module, Ingester → Storage Element).

Sprint 21: Security Enhancement
Sprint 23: Prometheus metrics instrumentation для certificate monitoring
"""

import logging
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.hazmat.backends import default_backend

from app.core.config import settings
from app.core.tls_metrics import (
    tls_certificate_expiry_days,
    tls_certificate_validation_total,
)

logger = logging.getLogger(__name__)


def _track_certificate_expiry(cert_path: str, cert_type: str) -> None:
    """
    Track certificate expiration metrics.

    Reads X.509 certificate, extracts expiry date, and updates Prometheus gauge
    with days until expiration.

    Args:
        cert_path: Path to certificate file (.pem format)
        cert_type: "ca" | "client" for metric labeling

    Metrics updated:
        - tls_certificate_expiry_days: Days until expiration (negative if expired)

    Example:
        >>> _track_certificate_expiry("/app/tls/ca-cert.pem", "ca")
        # Updates metric: tls_certificate_expiry_days{cert_type="ca", subject="..."} = 365
    """
    try:
        with open(cert_path, 'rb') as f:
            cert_data = f.read()

        # Parse X.509 certificate
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())

        # Calculate days until expiration
        now = datetime.now(timezone.utc)
        expiry = cert.not_valid_after_utc
        days_until_expiry = (expiry - now).days

        # Extract subject for label (RFC 4514 format)
        subject = cert.subject.rfc4514_string()

        # Update Prometheus metric
        tls_certificate_expiry_days.labels(
            cert_type=cert_type,
            subject=subject
        ).set(days_until_expiry)

        # Log certificate status
        if days_until_expiry < 0:
            logger.error(
                f"Certificate {cert_type} has EXPIRED",
                extra={
                    "cert_type": cert_type,
                    "subject": subject,
                    "expired_days_ago": abs(days_until_expiry),
                    "expiry": expiry.isoformat()
                }
            )
            tls_certificate_validation_total.labels(result="expired").inc()
        elif days_until_expiry < 7:
            logger.warning(
                f"Certificate {cert_type} expires in {days_until_expiry} days - CRITICAL",
                extra={
                    "cert_type": cert_type,
                    "subject": subject,
                    "days_until_expiry": days_until_expiry,
                    "expiry": expiry.isoformat()
                }
            )
        elif days_until_expiry < 30:
            logger.warning(
                f"Certificate {cert_type} expires in {days_until_expiry} days - action required",
                extra={
                    "cert_type": cert_type,
                    "subject": subject,
                    "days_until_expiry": days_until_expiry,
                    "expiry": expiry.isoformat()
                }
            )
        else:
            logger.info(
                f"Certificate {cert_type} expires in {days_until_expiry} days",
                extra={
                    "cert_type": cert_type,
                    "subject": subject,
                    "days_until_expiry": days_until_expiry,
                    "expiry": expiry.isoformat()
                }
            )
            tls_certificate_validation_total.labels(result="valid").inc()

    except FileNotFoundError:
        logger.error(
            f"Certificate file not found: {cert_path}",
            extra={"cert_type": cert_type, "cert_path": cert_path}
        )
    except Exception as e:
        logger.error(
            f"Failed to track certificate expiry for {cert_type}",
            extra={
                "cert_type": cert_type,
                "cert_path": cert_path,
                "error": str(e)
            }
        )


def create_ssl_context() -> Optional[ssl.SSLContext]:
    """
    Create SSL context для mTLS communication.

    Создает SSL context с поддержкой:
    - TLS 1.3 (или TLS 1.2 по конфигурации)
    - Mutual TLS authentication (client certificates)
    - Secure cipher suites
    - CA certificate verification

    Returns:
        ssl.SSLContext if TLS enabled, None otherwise

    Security considerations:
    - Требует валидные TLS сертификаты (cert_file, key_file, ca_cert_file)
    - Использует TLS 1.3 по умолчанию (TLS 1.2 minimum fallback)
    - AEAD cipher suites only (AES-GCM, ChaCha20-Poly1305)
    - Mutual authentication через client certificates

    Configuration:
        TLS_ENABLED=true
        TLS_CERT_FILE=/app/tls/client-cert.pem
        TLS_KEY_FILE=/app/tls/client-key.pem
        TLS_CA_CERT_FILE=/app/tls/ca-cert.pem
        TLS_PROTOCOL_VERSION=TLSv1.3
        TLS_CIPHERS=TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256

    Example:
        ```python
        ssl_context = create_ssl_context()
        if ssl_context:
            client = httpx.AsyncClient(verify=ssl_context)
        ```
    """
    if not settings.tls.enabled:
        logger.debug("TLS disabled, skipping SSL context creation")
        return None

    logger.info("Creating SSL context for mTLS communication")

    # Создание SSL context для client-side TLS
    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

    # CA certificate для server validation
    if settings.tls.ca_cert_file:
        ssl_context.load_verify_locations(cafile=settings.tls.ca_cert_file)
        logger.info(
            "Loaded CA certificate",
            extra={"ca_cert": settings.tls.ca_cert_file}
        )

        # Track CA certificate expiry metrics
        _track_certificate_expiry(settings.tls.ca_cert_file, "ca")
    else:
        logger.warning(
            "No CA certificate configured - server validation disabled! "
            "This is insecure for production. Set TLS_CA_CERT_FILE."
        )

    # Client certificate для mTLS (mutual TLS authentication)
    if settings.tls.cert_file and settings.tls.key_file:
        ssl_context.load_cert_chain(
            certfile=settings.tls.cert_file,
            keyfile=settings.tls.key_file
        )
        logger.info(
            "Loaded client certificate for mTLS",
            extra={
                "cert_file": settings.tls.cert_file,
                "key_file": settings.tls.key_file
            }
        )

        # Track client certificate expiry metrics
        _track_certificate_expiry(settings.tls.cert_file, "client")
    else:
        logger.warning(
            "No client certificate configured - mTLS disabled. "
            "For mutual TLS authentication, set TLS_CERT_FILE and TLS_KEY_FILE."
        )

    # TLS protocol version (minimum)
    if settings.tls.protocol_version == "TLSv1.3":
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
        logger.info("TLS 1.3 minimum protocol version configured")
    elif settings.tls.protocol_version == "TLSv1.2":
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        logger.info("TLS 1.2 minimum protocol version configured")
    else:
        logger.warning(
            f"Unknown TLS protocol version: {settings.tls.protocol_version}. "
            "Using default (TLS 1.2+)."
        )

    # Cipher suites (TLS 1.3 AEAD only для production security)
    if settings.tls.ciphers:
        try:
            ssl_context.set_ciphers(settings.tls.ciphers)
            logger.info(
                "Cipher suites configured",
                extra={"ciphers": settings.tls.ciphers}
            )
        except ssl.SSLError as e:
            logger.error(
                "Failed to configure cipher suites",
                extra={
                    "ciphers": settings.tls.ciphers,
                    "error": str(e)
                }
            )
            # Fall back to default ciphers
            logger.warning("Using default cipher suites")

    logger.info(
        "SSL context created successfully",
        extra={
            "protocol": settings.tls.protocol_version,
            "mtls_enabled": bool(settings.tls.cert_file and settings.tls.key_file),
            "ca_verification": bool(settings.tls.ca_cert_file)
        }
    )

    return ssl_context
