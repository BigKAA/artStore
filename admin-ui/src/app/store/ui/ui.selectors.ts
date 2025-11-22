/**
 * ArtStore Admin UI - UI Selectors
 * NgRx selectors для выборки UI данных из state
 */

import { createFeatureSelector, createSelector } from '@ngrx/store';
import { UiState } from './ui.state';

/**
 * Feature selector для UI state
 */
export const selectUiState = createFeatureSelector<UiState>('ui');

/**
 * Selector: текущая тема
 */
export const selectTheme = createSelector(selectUiState, (state) => state.theme);

/**
 * Selector: флаг dark mode
 */
export const selectIsDarkMode = createSelector(
  selectTheme,
  (theme) => theme === 'dark'
);

/**
 * Selector: состояние sidebar
 */
export const selectSidebarOpen = createSelector(
  selectUiState,
  (state) => state.sidebarOpen
);

/**
 * Selector: все уведомления
 */
export const selectNotifications = createSelector(
  selectUiState,
  (state) => state.notifications
);

/**
 * Selector: количество уведомлений
 */
export const selectNotificationCount = createSelector(
  selectNotifications,
  (notifications) => notifications.length
);

/**
 * Selector: есть ли уведомления
 */
export const selectHasNotifications = createSelector(
  selectNotificationCount,
  (count) => count > 0
);

/**
 * Selector: global loading состояние
 */
export const selectGlobalLoading = createSelector(
  selectUiState,
  (state) => state.globalLoading
);

/**
 * Selector: текущий язык интерфейса
 */
export const selectLanguage = createSelector(
  selectUiState,
  (state) => state.language
);
