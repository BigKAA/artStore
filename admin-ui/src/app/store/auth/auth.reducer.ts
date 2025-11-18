/**
 * ArtStore Admin UI - Authentication Reducer
 * NgRx reducer для управления состоянием аутентификации
 */

import { createReducer, on } from '@ngrx/store';
import { AuthState, initialAuthState } from './auth.state';
import * as AuthActions from './auth.actions';

/**
 * Auth reducer
 * Обрабатывает все auth actions и обновляет state
 */
export const authReducer = createReducer(
  initialAuthState,

  // Login actions
  on(AuthActions.login, (state) => ({
    ...state,
    loading: true,
    error: null,
  })),

  on(AuthActions.loginSuccess, (state, { accessToken, refreshToken, user }) => ({
    ...state,
    accessToken,
    refreshToken: refreshToken ?? null,
    currentUser: user,
    isAuthenticated: true,
    loading: false,
    error: null,
  })),

  on(AuthActions.loginFailure, (state, { error }) => ({
    ...state,
    loading: false,
    error,
    isAuthenticated: false,
  })),

  // Logout action
  on(AuthActions.logout, () => ({
    ...initialAuthState,
  })),

  // Refresh token actions
  on(AuthActions.refreshToken, (state) => ({
    ...state,
    loading: true,
  })),

  on(AuthActions.refreshTokenSuccess, (state, { accessToken }) => ({
    ...state,
    accessToken,
    loading: false,
    error: null,
  })),

  on(AuthActions.refreshTokenFailure, (state, { error }) => ({
    ...state,
    loading: false,
    error,
    // При ошибке обновления токена - выходим
    accessToken: null,
    refreshToken: null,
    currentUser: null,
    isAuthenticated: false,
  })),

  // Restore session actions
  on(AuthActions.restoreSession, (state) => ({
    ...state,
    loading: true,
  })),

  on(AuthActions.restoreSessionSuccess, (state, { accessToken, refreshToken, user }) => ({
    ...state,
    accessToken,
    refreshToken: refreshToken ?? null,
    currentUser: user,
    isAuthenticated: true,
    loading: false,
    error: null,
  })),

  on(AuthActions.restoreSessionFailure, (state) => ({
    ...state,
    loading: false,
  }))
);
