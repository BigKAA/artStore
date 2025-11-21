/**
 * ArtStore Admin UI - Upload Request Model
 * Модель запроса для загрузки файлов
 */

/**
 * Режим хранения файла
 */
export type StorageMode = 'edit' | 'rw';

/**
 * Алгоритм сжатия
 */
export type CompressionAlgorithm = 'gzip' | 'brotli';

/**
 * Запрос на загрузку файла
 */
export interface UploadRequest {
  file: File;
  description?: string;
  storage_mode: StorageMode;
  compress: boolean;
  compression_algorithm: CompressionAlgorithm;
}

/**
 * Ответ на загрузку файла
 */
export interface UploadResponse {
  file_id: string;
  filename: string;
  file_size: number;
  sha256_hash: string;
  storage_element_id: string;
  created_at: Date;
}
