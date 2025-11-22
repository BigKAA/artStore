"""
Query Module - Custom Exceptions.

?@545;O5B A?5F8D8G=K5 8A:;NG5=8O 4;O Query Module.
5@0@E8G5A:0O AB@C:BC@0 4;O B>G=>3> error handling.
"""

from typing import Optional


class QueryException(Exception):
    """07>2>5 8A:;NG5=85 4;O Query Module."""

    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


# Authentication Exceptions
class AuthenticationException(QueryException):
    """07>2>5 8A:;NG5=85 0CB5=B8D8:0F88."""
    pass


class InvalidTokenException(AuthenticationException):
    """520;84=K9 JWT B>:5=."""
    pass


class TokenExpiredException(AuthenticationException):
    """AB5:H89 JWT B>:5=."""
    pass


class InsufficientPermissionsException(AuthenticationException):
    """54>AB0B>G=> ?@02 4;O >?5@0F88."""
    pass


# Search Exceptions
class SearchException(QueryException):
    """07>2>5 8A:;NG5=85 ?>8A:0."""
    pass


class InvalidSearchQueryException(SearchException):
    """520;84=K9 ?>8A:>2K9 70?@>A."""
    pass


class SearchTimeoutException(SearchException):
    """@52KH5= timeout ?>8A:0."""
    pass


class TooManyResultsException(SearchException):
    """!;8H:>< <=>3> @57C;LB0B>2 ?>8A:0."""
    pass


# Download Exceptions
class DownloadException(QueryException):
    """07>2>5 8A:;NG5=85 A:0G820=8O D09;>2."""
    pass


class FileNotFoundException(DownloadException):
    """$09; =5 =0945=."""
    pass


class StorageElementUnavailableException(DownloadException):
    """Storage Element =54>ABC?5=."""
    pass


class RangeNotSatisfiableException(DownloadException):
    """520;84=K9 HTTP Range 70?@>A."""
    pass


class DownloadInterruptedException(DownloadException):
    """!:0G820=85 ?@5@20=>."""
    pass


# Cache Exceptions
class CacheException(QueryException):
    """07>2>5 8A:;NG5=85 :5H8@>20=8O."""
    pass


class CacheUnavailableException(CacheException):
    """Cache =54>ABC?5= (Redis 8;8 Local)."""
    pass


class CacheCorruptedException(CacheException):
    """0==K5 2 :5H5 ?>2@5645=K."""
    pass


# Service Discovery Exceptions
class ServiceDiscoveryException(QueryException):
    """H81:0 Service Discovery."""
    pass


class StorageElementNotFoundException(ServiceDiscoveryException):
    """Storage Element =5 =0945= 2 Service Discovery."""
    pass


# Circuit Breaker Exceptions
class CircuitBreakerOpenException(QueryException):
    """Circuit Breaker >B:@KB, A5@28A =54>ABC?5=."""
    pass


# Database Exceptions
class DatabaseException(QueryException):
    """07>2>5 8A:;NG5=85 @01>BK A ."""
    pass


class DatabaseConnectionException(DatabaseException):
    """H81:0 ?>4:;NG5=8O : ."""
    pass


class QueryExecutionException(DatabaseException):
    """H81:0 2K?>;=5=8O SQL 70?@>A0."""
    pass
