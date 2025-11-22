/**
 * ArtStore Admin UI - UI Actions
 * NgRx actions для управления UI состоянием
 */

import { createAction, props } from '@ngrx/store';
import { Theme, Notification } from './ui.state';

/**
 * Переключение темы
 */
export const toggleTheme = createAction('[UI] Toggle Theme');

/**
 * Установка конкретной темы
 */
export const setTheme = createAction('[UI] Set Theme', props<{ theme: Theme }>());

/**
 * Переключение sidebar
 */
export const toggleSidebar = createAction('[UI] Toggle Sidebar');

/**
 * Открытие sidebar
 */
export const openSidebar = createAction('[UI] Open Sidebar');

/**
 * Закрытие sidebar
 */
export const closeSidebar = createAction('[UI] Close Sidebar');

/**
 * Добавление уведомления
 */
export const addNotification = createAction(
  '[UI] Add Notification',
  props<{ notification: Omit<Notification, 'id' | 'timestamp'> }>()
);

/**
 * Удаление уведомления
 */
export const removeNotification = createAction(
  '[UI] Remove Notification',
  props<{ id: string }>()
);

/**
 * Очистка всех уведомлений
 */
export const clearNotifications = createAction('[UI] Clear Notifications');

/**
 * Показать global loading overlay
 */
export const showGlobalLoading = createAction('[UI] Show Global Loading');

/**
 * Скрыть global loading overlay
 */
export const hideGlobalLoading = createAction('[UI] Hide Global Loading');

/**
 * Изменение языка интерфейса
 */
export const setLanguage = createAction(
  '[UI] Set Language',
  props<{ language: string }>()
);

/**
 * Namespace export для удобства использования
 */
export const UiActions = {
  setTheme,
  toggleTheme,
  toggleSidebar,
  addNotification,
  removeNotification,
  clearNotifications,
  showGlobalLoading,
  hideGlobalLoading,
  setLanguage,
};
