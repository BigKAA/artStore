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
import { catchError, switchMap, throwError, Observable } from 'rxjs';

import { AuthService } from './auth.service';

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
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);

  // Список endpoints, которые не требуют авторизации
  const publicEndpoints = ['/api/auth/token', '/api/auth/refresh'];

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
        return handle401Error(authReq, next, authService);
      }

      // Обработать 403 Forbidden
      if (error.status === 403) {
        console.error('Access denied (403):', error);
        // TODO: Можно добавить уведомление пользователю
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
 * @returns Observable с результатом retry или ошибкой
 */
function handle401Error(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
  authService: AuthService
): Observable<HttpEvent<unknown>> {
  // Проверить, есть ли refresh token
  const refreshToken = authService.getRefreshToken();

  if (!refreshToken) {
    // Нет refresh token - logout и redirect на login
    console.error('No refresh token available, logout required');
    authService.logout();
    // TODO: Redirect на login page через Router
    return throwError(() => new Error('Authentication required'));
  }

  // Попытаться refresh token
  return authService.refreshToken().pipe(
    switchMap((tokenResponse) => {
      // Refresh успешен - получить новый access token
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
      // Refresh неудачен - logout и redirect на login
      console.error('Token refresh failed, logout required:', refreshError);
      authService.logout();
      // TODO: Redirect на login page через Router
      return throwError(() => new Error('Session expired, please login again'));
    })
  );
}
