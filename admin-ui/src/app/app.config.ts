import { ApplicationConfig, provideBrowserGlobalErrorListeners, provideZoneChangeDetection, isDevMode } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideStore } from '@ngrx/store';
import { provideStoreDevtools } from '@ngrx/store-devtools';
import { provideEffects } from '@ngrx/effects';

import { routes } from './app.routes';
import { authReducer } from './store/auth/auth.reducer';
import { uiReducer } from './store/ui/ui.reducer';

/**
 * ArtStore Admin UI Application Configuration
 * Конфигурация Angular приложения с NgRx state management
 */
export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),

    // NgRx Store configuration
    provideStore({
      auth: authReducer,
      ui: uiReducer,
    }),

    // NgRx Effects (пока без effects, будут добавлены позже)
    provideEffects([]),

    // NgRx DevTools (только в development режиме)
    provideStoreDevtools({
      maxAge: 25, // Сохраняем последние 25 состояний
      logOnly: !isDevMode(), // В production только логи
      autoPause: true, // Автопауза при неактивности
      trace: false, // Отключаем трассировку для производительности
      traceLimit: 75, // Максимум 75 stack frames
    }),
  ]
};
