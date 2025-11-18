/**
 * ArtStore Admin UI - UI Reducer
 * NgRx reducer для управления состоянием UI
 */

import { createReducer, on } from '@ngrx/store';
import { UiState, initialUiState } from './ui.state';
import * as UiActions from './ui.actions';

/**
 * Генерирует уникальный ID для уведомления
 */
function generateNotificationId(): string {
  return `notif-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * UI reducer
 * Обрабатывает все UI actions и обновляет state
 */
export const uiReducer = createReducer(
  initialUiState,

  // Theme actions
  on(UiActions.toggleTheme, (state) => ({
    ...state,
    theme: state.theme === 'light' ? 'dark' : 'light',
  })),

  on(UiActions.setTheme, (state, { theme }) => ({
    ...state,
    theme,
  })),

  // Sidebar actions
  on(UiActions.toggleSidebar, (state) => ({
    ...state,
    sidebarOpen: !state.sidebarOpen,
  })),

  on(UiActions.openSidebar, (state) => ({
    ...state,
    sidebarOpen: true,
  })),

  on(UiActions.closeSidebar, (state) => ({
    ...state,
    sidebarOpen: false,
  })),

  // Notification actions
  on(UiActions.addNotification, (state, { notification }) => ({
    ...state,
    notifications: [
      ...state.notifications,
      {
        ...notification,
        id: generateNotificationId(),
        timestamp: Date.now(),
      },
    ],
  })),

  on(UiActions.removeNotification, (state, { id }) => ({
    ...state,
    notifications: state.notifications.filter((n) => n.id !== id),
  })),

  on(UiActions.clearNotifications, (state) => ({
    ...state,
    notifications: [],
  })),

  // Global loading actions
  on(UiActions.showGlobalLoading, (state) => ({
    ...state,
    globalLoading: true,
  })),

  on(UiActions.hideGlobalLoading, (state) => ({
    ...state,
    globalLoading: false,
  })),

  // Language action
  on(UiActions.setLanguage, (state, { language }) => ({
    ...state,
    language,
  }))
);
