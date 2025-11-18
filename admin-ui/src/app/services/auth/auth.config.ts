/**
 * ArtStore Admin UI - Authentication Configuration
 * Конфигурация для работы с Admin Module API
 */

/**
 * Интерфейс конфигурации аутентификации
 */
export interface AuthConfig {
  /** Базовый URL Admin Module API */
  apiBaseUrl: string;

  /** Endpoint для получения токена (OAuth 2.0 Client Credentials) */
  tokenEndpoint: string;

  /** Endpoint для refresh токена */
  refreshEndpoint: string;

  /** Endpoint для получения информации о текущем пользователе */
  userInfoEndpoint: string;

  /** Время жизни access token в секундах (по умолчанию 30 минут) */
  accessTokenExpiry: number;

  /** Время жизни refresh token в секундах (по умолчанию 7 дней) */
  refreshTokenExpiry: number;

  /** За сколько секунд до истечения токена начинать refresh */
  refreshBeforeExpiry: number;

  /** Хранить ли токены в localStorage (иначе только в памяти) */
  persistTokens: boolean;

  /** Ключ для хранения access token в localStorage */
  accessTokenKey: string;

  /** Ключ для хранения refresh token в localStorage */
  refreshTokenKey: string;
}

/**
 * Дефолтная конфигурация аутентификации
 *
 * ВАЖНО: В production apiBaseUrl должен быть получен из environment variables
 */
export const defaultAuthConfig: AuthConfig = {
  // API Base URL (должен быть настроен через environment)
  apiBaseUrl: 'http://localhost:8000',

  // OAuth 2.0 Client Credentials endpoint
  tokenEndpoint: '/api/auth/token',

  // Token refresh endpoint
  refreshEndpoint: '/api/auth/refresh',

  // User info endpoint (для получения данных о пользователе)
  userInfoEndpoint: '/api/auth/me',

  // Время жизни токенов (согласно CLAUDE.md)
  accessTokenExpiry: 1800,  // 30 minutes
  refreshTokenExpiry: 604800,  // 7 days

  // Refresh token за 5 минут до истечения
  refreshBeforeExpiry: 300,  // 5 minutes

  // Хранить токены в localStorage для persistence между сессиями
  persistTokens: true,

  // Ключи для localStorage
  accessTokenKey: 'artstore_access_token',
  refreshTokenKey: 'artstore_refresh_token',
};

/**
 * OAuth 2.0 Client Credentials Request
 */
export interface LoginRequest {
  /** Client ID service account */
  client_id: string;

  /** Client Secret service account */
  client_secret: string;
}

/**
 * OAuth 2.0 Token Response
 */
export interface TokenResponse {
  /** JWT access token */
  access_token: string;

  /** Token type (всегда "Bearer") */
  token_type: 'Bearer';

  /** Время жизни токена в секундах */
  expires_in: number;

  /** Refresh token (опционально) */
  refresh_token?: string;
}

/**
 * User Info Response
 */
export interface UserInfoResponse {
  /** User ID */
  id: string;

  /** Username (из JWT sub) */
  username: string;

  /** Email */
  email: string;

  /** Role (admin, user, etc.) */
  role: string;

  /** Display name (опционально) */
  displayName?: string;

  /** Account type (admin_user, service_account) */
  type: string;
}

/**
 * Decoded JWT Payload
 */
export interface JwtPayload {
  /** Subject (username) */
  sub: string;

  /** Account type */
  type: string;

  /** Role */
  role: string;

  /** JWT ID */
  jti: string;

  /** Issued at (timestamp) */
  iat: number;

  /** Expiration time (timestamp) */
  exp: number;

  /** Not before (timestamp) */
  nbf: number;
}
