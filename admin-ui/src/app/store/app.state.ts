/**
 * ArtStore Admin UI - Root State Interface
 * Определяет структуру глобального состояния приложения
 */

import { AuthState } from './auth/auth.state';
import { UiState } from './ui/ui.state';

/**
 * Корневое состояние приложения
 * Объединяет все feature states в единую структуру
 */
export interface AppState {
  /** Состояние аутентификации и текущего пользователя */
  auth: AuthState;

  /** Состояние UI (theme, sidebar, notifications) */
  ui: UiState;
}
