/**
 * ArtStore Admin UI - File Metadata Model
 * Модели данных для файловых метаданных
 */

/**
 * Метаданные файла в системе
 */
export interface FileMetadata {
  id: string;
  filename: string;
  storage_filename: string;
  file_size: number;
  mime_type?: string;
  sha256_hash: string;
  username: string;
  tags: string[];
  description?: string;
  created_at: Date;
  updated_at: Date;
  storage_element_id: string;
  relevance_score?: number;
}

/**
 * Ответ на поиск файлов
 */
export interface SearchResponse {
  results: FileMetadata[];
  total_count: number;
  limit: number;
  offset: number;
  has_more: boolean;
}
