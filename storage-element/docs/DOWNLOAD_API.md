# File Download API Documentation

Comprehensive HTTP Range requests (RFC 7233) implementation для эффективной загрузки файлов.

## Endpoint

```
GET /api/v1/files/{file_id}/download
```

## Features

- ✅ **Full file download** (200 OK)
- ✅ **Single range download** (206 Partial Content)
- ✅ **Multiple ranges download** (206 Partial Content, multipart/byteranges)
- ✅ **Resumable downloads** (через Range requests)
- ✅ **Conditional requests** (ETag, If-Modified-Since)
- ✅ **Streaming support** для больших файлов
- ✅ **Path traversal protection**

## HTTP Headers Support

### Request Headers

| Header | Description | Example |
|--------|-------------|---------|
| `Range` | Specify byte range(s) to download | `bytes=0-1023` |
| `If-None-Match` | Conditional request with ETag | `"abc123def456"` |
| `If-Modified-Since` | Conditional request with date | `Wed, 21 Oct 2015 07:28:00 GMT` |

### Response Headers

| Header | Description | Example |
|--------|-------------|---------|
| `Content-Type` | MIME type of file | `application/pdf` |
| `Content-Length` | Size of content | `1024` |
| `Content-Range` | Byte range being sent | `bytes 0-1023/5000` |
| `Content-Disposition` | Suggested filename | `attachment; filename="report.pdf"` |
| `Accept-Ranges` | Server supports ranges | `bytes` |
| `ETag` | Entity tag for caching | `"abc123def456"` |
| `Last-Modified` | Last modification time | `Wed, 21 Oct 2015 07:28:00 GMT` |

## Usage Examples

### 1. Full File Download

**Request:**
```http
GET /api/v1/files/123e4567-e89b-12d3-a456-426614174000/download HTTP/1.1
Host: storage.example.com
```

**Response:**
```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Length: 1048576
Content-Disposition: attachment; filename="annual_report_2024.pdf"
Accept-Ranges: bytes
ETag: "abc123def456"
Last-Modified: Wed, 21 Oct 2015 07:28:00 GMT

[File content 1MB]
```

### 2. Single Range Download

**Request:**
```http
GET /api/v1/files/123e4567-e89b-12d3-a456-426614174000/download HTTP/1.1
Host: storage.example.com
Range: bytes=0-1023
```

**Response:**
```http
HTTP/1.1 206 Partial Content
Content-Type: application/pdf
Content-Length: 1024
Content-Range: bytes 0-1023/1048576
Content-Disposition: attachment; filename="annual_report_2024.pdf"
Accept-Ranges: bytes
ETag: "abc123def456"

[First 1KB of file]
```

### 3. Multiple Ranges Download

**Request:**
```http
GET /api/v1/files/123e4567-e89b-12d3-a456-426614174000/download HTTP/1.1
Host: storage.example.com
Range: bytes=0-1023,4096-8191
```

**Response:**
```http
HTTP/1.1 206 Partial Content
Content-Type: multipart/byteranges; boundary=RANGE_SEPARATOR

--RANGE_SEPARATOR
Content-Type: application/pdf
Content-Range: bytes 0-1023/1048576

[First range content]
--RANGE_SEPARATOR
Content-Type: application/pdf
Content-Range: bytes 4096-8191/1048576

[Second range content]
--RANGE_SEPARATOR--
```

### 4. Suffix Range (Last N Bytes)

**Request:**
```http
GET /api/v1/files/123e4567-e89b-12d3-a456-426614174000/download HTTP/1.1
Host: storage.example.com
Range: bytes=-500
```

**Response:**
```http
HTTP/1.1 206 Partial Content
Content-Range: bytes 1048076-1048575/1048576

[Last 500 bytes]
```

### 5. Open-Ended Range

**Request:**
```http
GET /api/v1/files/123e4567-e89b-12d3-a456-426614174000/download HTTP/1.1
Host: storage.example.com
Range: bytes=1000-
```

**Response:**
```http
HTTP/1.1 206 Partial Content
Content-Range: bytes 1000-1048575/1048576

[From byte 1000 to end]
```

### 6. Conditional Request (ETag)

**Request:**
```http
GET /api/v1/files/123e4567-e89b-12d3-a456-426614174000/download HTTP/1.1
Host: storage.example.com
If-None-Match: "abc123def456"
```

**Response (file unchanged):**
```http
HTTP/1.1 304 Not Modified
```

### 7. Conditional Request (Modified Since)

**Request:**
```http
GET /api/v1/files/123e4567-e89b-12d3-a456-426614174000/download HTTP/1.1
Host: storage.example.com
If-Modified-Since: Wed, 21 Oct 2015 07:28:00 GMT
```

**Response (file not modified):**
```http
HTTP/1.1 304 Not Modified
```

## Range Request Formats

### Valid Range Formats

```http
Range: bytes=0-1023              # Single range
Range: bytes=0-1023,2048-4095    # Multiple ranges
Range: bytes=-500                # Last 500 bytes
Range: bytes=1000-               # From byte 1000 to end
Range: bytes=0-0                 # First byte only
```

### Invalid Range Formats

```http
Range: bytes=500-100             # Start > End → 416 Range Not Satisfiable
Range: bytes=5000-               # Start >= file_size → 416
Range: bytes=abc-def             # Non-numeric → 416
Range: invalid                   # Bad format → 416
```

## Error Responses

### 400 Bad Request

Invalid file_id format:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "detail": "Invalid file_id format"
}
```

### 403 Forbidden

Path traversal attempt detected:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "detail": "Access denied"
}
```

### 404 Not Found

File не существует в базе данных:

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "detail": "File 123e4567-e89b-12d3-a456-426614174000 not found"
}
```

File не существует на диске:

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "detail": "File not found on storage"
}
```

### 416 Range Not Satisfiable

Invalid или unsatisfiable range:

```http
HTTP/1.1 416 Range Not Satisfiable
Content-Range: bytes */1048576

{
  "detail": "Range not satisfiable"
}
```

## Resumable Download Example

Client может возобновить загрузку после обрыва соединения:

**Initial Request:**
```http
GET /api/v1/files/{file_id}/download HTTP/1.1
Range: bytes=0-
```

**Connection drops after 512KB...**

**Resume Request:**
```http
GET /api/v1/files/{file_id}/download HTTP/1.1
Range: bytes=524288-
```

Server продолжит отправку с байта 524288.

## Performance Considerations

### Streaming Benefits

- **Memory Efficient**: Файлы стримятся chunks по 64KB, не загружаются в память целиком
- **Large Files**: Поддерживает файлы любого размера без OOM errors
- **Concurrent Downloads**: Multiple clients могут скачивать одновременно

### Caching Strategies

**ETag Validation:**
- Client сохраняет ETag из первого запроса
- Последующие запросы включают `If-None-Match`
- Server возвращает 304 если файл не изменился

**Last-Modified Validation:**
- Client сохраняет `Last-Modified` timestamp
- Последующие запросы включают `If-Modified-Since`
- Server сравнивает timestamps

### CDN Integration

Response headers оптимизированы для CDN:

```http
Accept-Ranges: bytes          # CDN knows server supports ranges
ETag: "abc123"                # CDN can cache and validate
Last-Modified: ...            # Additional cache validation
Content-Disposition: ...      # Proper filename for downloads
```

## Security Features

### Path Traversal Protection

Service проверяет, что file path находится внутри storage_base:

```python
# ❌ Blocked
storage_path = "../../../etc"
storage_filename = "passwd"

# ❌ Blocked
storage_path = "2024/01/01"
storage_filename = "../../../../../../etc/passwd"

# ✅ Allowed
storage_path = "2024/01/01/12"
storage_filename = "report_user1_20240101T120000_abc123.pdf"
```

### Access Control

- JWT validation (через Admin Module)
- File permissions check (planned)
- Rate limiting (planned)

## Implementation Details

### Service Layer

[FileDownloadService](cci:1://file:///home/artur/Projects/artStore/storage-element/app/services/file_download.py:0:0-0:0):
- Range parsing and validation
- File streaming with chunks
- ETag generation
- Path traversal protection
- Multipart range formatting

### API Layer

[Download Endpoint](cci:1://file:///home/artur/Projects/artStore/storage-element/app/api/v1/files.py:252:0-447:0):
- Request header processing
- Conditional request handling
- Response header generation
- Error handling
- Logging

## Testing

Comprehensive test suite в [test_file_download.py](cci:1://file:///home/artur/Projects/artStore/storage-element/tests/test_file_download.py:0:0-0:0):

**16 Unit Tests (все passed):**
- Path traversal protection
- ETag generation
- Range parsing (single, multiple, suffix, open-ended)
- Range validation
- File streaming
- Multipart ranges

**8 Integration Tests (skipped - требуют full stack):**
- Full upload-download cycle
- Resumable downloads
- Concurrent downloads
- Large file performance

Run tests:
```bash
pytest tests/test_file_download.py -v
```

## Future Enhancements

- [ ] **Bandwidth throttling** для rate limiting
- [ ] **CDN pre-warming** для популярных файлов
- [ ] **Digital signature verification** перед download
- [ ] **Access logs** для audit trail
- [ ] **Download analytics** (count, bandwidth usage)
- [ ] **Compression on-the-fly** (gzip, brotli для text files)
