/**
 * ArtStore Admin UI - JWT Authentication Interceptor
 * HTTP Interceptor для автоматического добавления JWT token к запросам
 */
import {
  HttpInterceptorFn,
  HttpErrorResponse,
  HttpEvent,
  HttpRequest,
  HttpHandlerFn,
} from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { Store } from '@ngrx/store';
import { catchError, switchMap, throwError, Observable } from 'rxjs';

import { AuthService } from './auth.service';
import { AppState } from '../../store/app.state';
import { AuthActions } from '../../store/auth/auth.actions';
import { UiActions } from '../../store/ui/ui.actions';

/**
 * JWT Authentication Interceptor (Functional)
 *
 * Автоматически добавляет Authorization header с Bearer token ко всем HTTP запросам
 *
 * Функциональность:
 * - Добавление Bearer token ко всем запросам (кроме login/refresh endpoints)
 * - Обработка 401 Unauthorized ответов
 * - Автоматический retry после успешного token refresh
 * - Logout при неудачном refresh
 * - Интеграция с NgRx store для state management
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const router = inject(Router);
  const store = inject(Store<AppState>);

  // Список endpoints, которые не требуют авторизации
  const publicEndpoints = [
    '/api/v1/admin-auth/login',
    '/api/v1/admin-auth/refresh',
    '/api/auth/token',
    '/api/auth/refresh'
  ];

  // Проверить, является ли запрос к публичному endpoint
  const isPublicEndpoint = publicEndpoints.some((endpoint) =>
    req.url.includes(endpoint)
  );

  // Если публичный endpoint - пропустить добавление токена
  if (isPublicEndpoint) {
    return next(req);
  }

  // Получить access token
  const accessToken = authService.getAccessToken();

  // Если токена нет - пропустить (пользователь не авторизован)
  if (!accessToken) {
    return next(req);
  }

  // Клонировать запрос и добавить Authorization header
  const authReq = req.clone({
    setHeaders: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  // Отправить запрос и обработать ошибки
  return next(authReq).pipe(
    catchError((error: HttpErrorResponse) => {
      // Обработать 401 Unauthorized
      if (error.status === 401) {
        return handle401Error(authReq, next, authService, router, store);
      }

      // Обработать 403 Forbidden
      if (error.status === 403) {
        console.error('Access denied (403):', error);
        store.dispatch(
          UiActions.addNotification({
            notification: {
              type: 'error',
              title: 'Access Denied',
              message: 'You do not have permission to perform this action',
              autoHide: 5000,
            },
          })
        );
      }

      // Для остальных ошибок - пробросить дальше
      return throwError(() => error);
    })
  );
};

/**
 * Обработать 401 Unauthorized ответ
 *
 * Попытаться refresh token и retry оригинального запроса
 *
 * @param req - Оригинальный HTTP запрос
 * @param next - HttpHandler для retry запроса
 * @param authService - AuthService для refresh token
 * @param router - Router для navigation
 * @param store - NgRx Store для dispatch actions
 * @returns Observable с результатом retry или ошибкой
 */
function handle401Error(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
  authService: AuthService,
  router: Router,
  store: Store<AppState>
): Observable<HttpEvent<unknown>> {
  console.log('[AuthInterceptor] 401 Unauthorized detected, attempting token refresh');

  // Проверить, есть ли refresh token
  const refreshToken = authService.getRefreshToken();

  if (!refreshToken) {
    // Нет refresh token - dispatch logout action
    console.error('[AuthInterceptor] No refresh token available, logout required');

    store.dispatch(
      UiActions.addNotification({
        notification: {
          type: 'warning',
          title: 'Session Expired',
          message: 'Please login again to continue',
          autoHide: 5000,
        },
      })
    );

    // Dispatch logout через NgRx
    store.dispatch(AuthActions.logout());

    // Redirect на login page
    router.navigate(['/login']);

    return throwError(() => new Error('Authentication required'));
  }

  // Попытаться refresh token
  return authService.refreshToken().pipe(
    switchMap((tokenResponse) => {
      console.log('[AuthInterceptor] Token refresh successful, retrying original request');

      // Refresh успешен - dispatch refresh success action
      store.dispatch(
        AuthActions.refreshTokenSuccess({
          accessToken: tokenResponse.access_token,
          refreshToken: tokenResponse.refresh_token || refreshToken,
        })
      );

      // Получить новый access token
      const newAccessToken = tokenResponse.access_token;

      // Клонировать запрос с новым токеном
      const retryReq = req.clone({
        setHeaders: {
          Authorization: `Bearer ${newAccessToken}`,
        },
      });

      // Retry оригинального запроса
      return next(retryReq);
    }),
    catchError((refreshError) => {
      // Refresh неудачен - dispatch logout action
      console.error('[AuthInterceptor] Token refresh failed, logout required:', refreshError);

      store.dispatch(
        UiActions.addNotification({
          notification: {
            type: 'error',
            title: 'Session Expired',
            message: 'Your session has expired. Please login again.',
            autoHide: 5000,
          },
        })
      );

      // Dispatch logout через NgRx
      store.dispatch(AuthActions.logout());

      // Redirect на login page
      router.navigate(['/login']);

      return throwError(() => new Error('Session expired, please login again'));
    })
  );
}
