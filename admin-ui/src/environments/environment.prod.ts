/**
 * ArtStore Admin UI - Environment Configuration
 * Production Environment
 */
export const environment = {
  production: true,
  apiUrl: '/api/v1',
  // Ingester Module для загрузки файлов (production URL через reverse proxy)
  ingesterModuleUrl: '/ingester',
  // Query Module для поиска и скачивания файлов (production URL через reverse proxy)
  queryModuleUrl: '/query',
};
