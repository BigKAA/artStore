/**
 * ArtStore Admin UI - Search Request Model
 * Модель запроса для поиска файлов
 */

/**
 * Режим поиска файлов
 */
export type SearchMode = 'exact' | 'partial' | 'fulltext';

/**
 * Поле для сортировки
 */
export type SortField = 'created_at' | 'updated_at' | 'file_size' | 'filename' | 'relevance';

/**
 * Порядок сортировки
 */
export type SortOrder = 'asc' | 'desc';

/**
 * Запрос на поиск файлов с фильтрацией
 */
export interface SearchRequest {
  // Основные поля поиска
  query?: string;
  filename?: string;
  file_extension?: string;
  tags?: string[];

  // Фильтры
  username?: string;
  min_size?: number;
  max_size?: number;
  created_after?: Date;
  created_before?: Date;

  // Режим и параметры поиска
  mode: SearchMode;
  limit: number;
  offset: number;

  // Сортировка
  sort_by: SortField;
  sort_order: SortOrder;
}
