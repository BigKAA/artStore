/**
 * ArtStore Admin UI - Authentication Actions
 * NgRx actions для управления аутентификацией
 */

import { createAction, props } from '@ngrx/store';
import { User } from './auth.state';

/**
 * Попытка входа пользователя
 */
export const login = createAction(
  '[Auth] Login',
  props<{ clientId: string; clientSecret: string }>()
);

/**
 * Успешный вход
 */
export const loginSuccess = createAction(
  '[Auth] Login Success',
  props<{ accessToken: string; refreshToken?: string | null; user: User | null }>()
);

/**
 * Ошибка входа
 */
export const loginFailure = createAction(
  '[Auth] Login Failure',
  props<{ error: string }>()
);

/**
 * Выход пользователя
 */
export const logout = createAction('[Auth] Logout');

/**
 * Обновление access token
 */
export const refreshToken = createAction('[Auth] Refresh Token');

/**
 * Успешное обновление token
 */
export const refreshTokenSuccess = createAction(
  '[Auth] Refresh Token Success',
  props<{ accessToken: string; refreshToken?: string | null }>()
);

/**
 * Ошибка обновления token
 */
export const refreshTokenFailure = createAction(
  '[Auth] Refresh Token Failure',
  props<{ error: string }>()
);

/**
 * Восстановление сессии из localStorage
 */
export const restoreSession = createAction('[Auth] Restore Session');

/**
 * Успешное восстановление сессии
 */
export const restoreSessionSuccess = createAction(
  '[Auth] Restore Session Success',
  props<{ accessToken: string; refreshToken?: string | null; user: User | null }>()
);

/**
 * Ошибка восстановления сессии
 */
export const restoreSessionFailure = createAction('[Auth] Restore Session Failure');

/**
 * Namespace export для удобства использования
 */
export const AuthActions = {
  login,
  loginSuccess,
  loginFailure,
  logout,
  refreshToken,
  refreshTokenSuccess,
  refreshTokenFailure,
  restoreSession,
  restoreSessionSuccess,
  restoreSessionFailure,
};
