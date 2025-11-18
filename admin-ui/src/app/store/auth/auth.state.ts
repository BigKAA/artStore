/**
 * ArtStore Admin UI - Authentication State
 * Состояние аутентификации и текущего пользователя
 */

/**
 * Информация о текущем пользователе
 */
export interface User {
  /** ID пользователя */
  id: string;

  /** Имя пользователя */
  username: string;

  /** Email */
  email: string;

  /** Роль пользователя (ADMIN, USER, etc.) */
  role: string;

  /** Отображаемое имя */
  displayName?: string;
}

/**
 * Состояние аутентификации
 */
export interface AuthState {
  /** JWT access token */
  accessToken: string | null;

  /** JWT refresh token */
  refreshToken: string | null;

  /** Текущий пользователь (null если не авторизован) */
  currentUser: User | null;

  /** Флаг загрузки (при попытке аутентификации) */
  loading: boolean;

  /** Сообщение об ошибке */
  error: string | null;

  /** Флаг - пользователь авторизован */
  isAuthenticated: boolean;
}

/**
 * Начальное состояние аутентификации
 */
export const initialAuthState: AuthState = {
  accessToken: null,
  refreshToken: null,
  currentUser: null,
  loading: false,
  error: null,
  isAuthenticated: false,
};
