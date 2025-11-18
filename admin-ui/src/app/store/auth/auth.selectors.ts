/**
 * ArtStore Admin UI - Authentication Selectors
 * NgRx selectors для выборки данных аутентификации из state
 */

import { createFeatureSelector, createSelector } from '@ngrx/store';
import { AuthState } from './auth.state';

/**
 * Feature selector для auth state
 */
export const selectAuthState = createFeatureSelector<AuthState>('auth');

/**
 * Selector: текущий пользователь
 */
export const selectCurrentUser = createSelector(
  selectAuthState,
  (state) => state.currentUser
);

/**
 * Selector: access token
 */
export const selectAccessToken = createSelector(
  selectAuthState,
  (state) => state.accessToken
);

/**
 * Selector: refresh token
 */
export const selectRefreshToken = createSelector(
  selectAuthState,
  (state) => state.refreshToken
);

/**
 * Selector: флаг аутентификации
 */
export const selectIsAuthenticated = createSelector(
  selectAuthState,
  (state) => state.isAuthenticated
);

/**
 * Selector: флаг загрузки
 */
export const selectAuthLoading = createSelector(
  selectAuthState,
  (state) => state.loading
);

/**
 * Selector: ошибка аутентификации
 */
export const selectAuthError = createSelector(
  selectAuthState,
  (state) => state.error
);

/**
 * Selector: роль пользователя
 */
export const selectUserRole = createSelector(
  selectCurrentUser,
  (user) => user?.role
);

/**
 * Selector: имя пользователя для отображения
 */
export const selectUserDisplayName = createSelector(
  selectCurrentUser,
  (user) => user?.displayName || user?.username || 'Unknown'
);

/**
 * Selector: является ли пользователь администратором
 */
export const selectIsAdmin = createSelector(
  selectUserRole,
  (role) => role === 'ADMIN' || role === 'SUPER_ADMIN'
);
