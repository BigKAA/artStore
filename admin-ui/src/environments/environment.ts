/**
 * ArtStore Admin UI - Environment Configuration
 * Development Environment
 */
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000/api/v1',
  // Ingester Module для загрузки файлов
  ingesterModuleUrl: 'http://localhost:8020',
  // Query Module для поиска и скачивания файлов
  queryModuleUrl: 'http://localhost:8030',
};
