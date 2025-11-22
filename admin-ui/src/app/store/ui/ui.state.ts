/**
 * ArtStore Admin UI - UI State
 * Состояние пользовательского интерфейса
 */

/**
 * Тип темы оформления
 */
export type Theme = 'light' | 'dark';

/**
 * Тип уведомления
 */
export type NotificationType = 'success' | 'error' | 'warning' | 'info';

/**
 * Уведомление
 */
export interface Notification {
  /** Уникальный ID уведомления */
  id: string;

  /** Тип уведомления */
  type: NotificationType;

  /** Заголовок уведомления */
  title: string;

  /** Текст уведомления */
  message: string;

  /** Время создания */
  timestamp: number;

  /** Автоматически скрыть через N миллисекунд (null = не скрывать) */
  autoHide?: number;
}

/**
 * Состояние UI
 */
export interface UiState {
  /** Текущая тема (light/dark) */
  theme: Theme;

  /** Sidebar открыт/закрыт */
  sidebarOpen: boolean;

  /** Список активных уведомлений */
  notifications: Notification[];

  /** Флаг - показывать ли loading overlay */
  globalLoading: boolean;

  /** Текущий язык интерфейса */
  language: string;
}

/**
 * Начальное состояние UI
 */
export const initialUiState: UiState = {
  theme: 'light',
  sidebarOpen: true,
  notifications: [],
  globalLoading: false,
  language: 'ru',
};
