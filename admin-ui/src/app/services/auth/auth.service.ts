/**
 * ArtStore Admin UI - Authentication Service
 * Сервис для работы с аутентификацией через Admin Module API
 */
import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, throwError, of, BehaviorSubject, timer, Subscription } from 'rxjs';
import { map, catchError, tap, switchMap, take, filter } from 'rxjs/operators';

import {
  AuthConfig,
  defaultAuthConfig,
  LoginRequest,
  TokenResponse,
  UserInfoResponse,
  JwtPayload,
} from './auth.config';

/**
 * Authentication Service
 *
 * Основной сервис для работы с аутентификацией в ArtStore Admin UI
 *
 * Функциональность:
 * - OAuth 2.0 Client Credentials authentication
 * - JWT token management (access + refresh)
 * - Token persistence в localStorage
 * - **Proactive Silent Token Refresh** - автоматический refresh за 5 минут до истечения
 * - User info management
 *
 * Silent Refresh Implementation:
 * - При login/refresh планируется автоматический refresh
 * - Timer запускается за `refreshBeforeExpiry` секунд до истечения токена
 * - При startup проверяется существующий токен и планируется refresh
 * - Автоматическая подписка на refreshTokenNeeded$ выполняет refresh
 */
@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private http = inject(HttpClient);

  /** Конфигурация аутентификации */
  private config: AuthConfig = defaultAuthConfig;

  /** Subject для уведомления о необходимости refresh токена */
  private refreshTokenSubject$ = new BehaviorSubject<boolean>(false);

  /** Subscription для автоматического refresh токена */
  private refreshSubscription?: Subscription;

  /** Флаг для предотвращения одновременных refresh запросов */
  private isRefreshing = false;

  constructor() {
    // Инициализация silent refresh при запуске приложения
    this.initializeSilentRefresh();
  }

  /**
   * Выполнить login admin пользователя
   *
   * @param username - Admin username
   * @param password - Admin password
   * @returns Observable с token response
   */
  login(username: string, password: string): Observable<TokenResponse> {
    const url = `${this.config.apiBaseUrl}${this.config.tokenEndpoint}`;
    const body: LoginRequest = {
      username: username,
      password: password,
    };

    const headers = new HttpHeaders({
      'Content-Type': 'application/json',
    });

    return this.http.post<TokenResponse>(url, body, { headers }).pipe(
      tap((response) => {
        // Сохранить токены
        this.saveTokens(response.access_token, response.refresh_token);

        // Запланировать автоматический refresh
        this.scheduleTokenRefresh(response.expires_in);
      }),
      catchError((error) => {
        console.error('Login failed:', error);
        return throwError(() => this.formatError(error));
      })
    );
  }

  /**
   * Получить информацию о текущем пользователе
   *
   * @returns Observable с user info
   */
  getUserInfo(): Observable<UserInfoResponse> {
    const url = `${this.config.apiBaseUrl}${this.config.userInfoEndpoint}`;
    const token = this.getAccessToken();

    if (!token) {
      return throwError(() => new Error('No access token available'));
    }

    const headers = new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });

    return this.http.get<UserInfoResponse>(url, { headers }).pipe(
      catchError((error) => {
        console.error('Failed to get user info:', error);
        return throwError(() => this.formatError(error));
      })
    );
  }

  /**
   * Refresh access token используя refresh token
   *
   * @returns Observable с новым token response
   */
  refreshToken(): Observable<TokenResponse> {
    const url = `${this.config.apiBaseUrl}${this.config.refreshEndpoint}`;
    const refreshToken = this.getRefreshToken();

    if (!refreshToken) {
      return throwError(() => new Error('No refresh token available'));
    }

    const headers = new HttpHeaders({
      'Content-Type': 'application/json',
    });

    const body = { refresh_token: refreshToken };

    return this.http.post<TokenResponse>(url, body, { headers }).pipe(
      tap((response) => {
        // Обновить токены
        this.saveTokens(response.access_token, response.refresh_token);

        // Запланировать следующий refresh
        this.scheduleTokenRefresh(response.expires_in);
      }),
      catchError((error) => {
        console.error('Token refresh failed:', error);
        // При неудаче refresh - очистить все токены
        this.clearTokens();
        return throwError(() => this.formatError(error));
      })
    );
  }

  /**
   * Logout - очистить все токены и данные сессии
   */
  logout(): void {
    this.clearTokens();
  }

  /**
   * Получить access token из хранилища
   *
   * @returns Access token или null
   */
  getAccessToken(): string | null {
    if (this.config.persistTokens) {
      return localStorage.getItem(this.config.accessTokenKey);
    }
    // TODO: Реализовать хранение в памяти если persistTokens = false
    return null;
  }

  /**
   * Получить refresh token из хранилища
   *
   * @returns Refresh token или null
   */
  getRefreshToken(): string | null {
    if (this.config.persistTokens) {
      return localStorage.getItem(this.config.refreshTokenKey);
    }
    // TODO: Реализовать хранение в памяти если persistTokens = false
    return null;
  }

  /**
   * Проверить, валиден ли текущий access token
   *
   * @returns true если токен валиден
   */
  isTokenValid(): boolean {
    const token = this.getAccessToken();
    if (!token) {
      return false;
    }

    try {
      const payload = this.decodeToken(token);
      const now = Math.floor(Date.now() / 1000);

      // Проверить, что токен не истек и еще не активен (nbf)
      return payload.exp > now && payload.nbf <= now;
    } catch (error) {
      console.error('Failed to validate token:', error);
      return false;
    }
  }

  /**
   * Проверить, истекает ли токен скоро
   *
   * @returns true если токен истекает в течение refreshBeforeExpiry секунд
   */
  isTokenExpiringSoon(): boolean {
    const token = this.getAccessToken();
    if (!token) {
      return false;
    }

    try {
      const payload = this.decodeToken(token);
      const now = Math.floor(Date.now() / 1000);
      const expiresIn = payload.exp - now;

      return expiresIn <= this.config.refreshBeforeExpiry;
    } catch (error) {
      return false;
    }
  }

  /**
   * Декодировать JWT token и получить payload
   *
   * @param token - JWT token
   * @returns Decoded JWT payload
   * @throws Error если токен невалидный
   */
  decodeToken(token: string): JwtPayload {
    try {
      // JWT состоит из 3 частей: header.payload.signature
      const parts = token.split('.');
      if (parts.length !== 3) {
        throw new Error('Invalid JWT format');
      }

      // Декодировать payload (вторая часть)
      const payload = parts[1];
      const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
      return JSON.parse(decoded) as JwtPayload;
    } catch (error) {
      console.error('Failed to decode JWT:', error);
      throw new Error('Invalid JWT token');
    }
  }

  /**
   * Получить username из текущего токена
   *
   * @returns Username или null
   */
  getUsername(): string | null {
    const token = this.getAccessToken();
    if (!token) {
      return null;
    }

    try {
      const payload = this.decodeToken(token);
      return payload.sub;
    } catch (error) {
      return null;
    }
  }

  /**
   * Получить role из текущего токена
   *
   * @returns Role или null
   */
  getRole(): string | null {
    const token = this.getAccessToken();
    if (!token) {
      return null;
    }

    try {
      const payload = this.decodeToken(token);
      return payload.role;
    } catch (error) {
      return null;
    }
  }

  /**
   * Сохранить токены в хранилище
   *
   * @param accessToken - Access token
   * @param refreshToken - Refresh token (опционально)
   */
  private saveTokens(accessToken: string, refreshToken?: string): void {
    if (this.config.persistTokens) {
      localStorage.setItem(this.config.accessTokenKey, accessToken);
      if (refreshToken) {
        localStorage.setItem(this.config.refreshTokenKey, refreshToken);
      }
    }
    // TODO: Реализовать хранение в памяти если persistTokens = false
  }

  /**
   * Очистить все токены из хранилища
   */
  private clearTokens(): void {
    if (this.config.persistTokens) {
      localStorage.removeItem(this.config.accessTokenKey);
      localStorage.removeItem(this.config.refreshTokenKey);
    }
    // TODO: Очистить хранилище в памяти если persistTokens = false
  }

  /**
   * Запланировать автоматический refresh токена
   *
   * @param expiresIn - Время жизни токена в секундах
   */
  private scheduleTokenRefresh(expiresIn: number): void {
    // Refresh за refreshBeforeExpiry секунд до истечения
    const refreshDelay =
      (expiresIn - this.config.refreshBeforeExpiry) * 1000;

    if (refreshDelay > 0) {
      timer(refreshDelay)
        .pipe(
          take(1),
          switchMap(() => {
            // Уведомить о необходимости refresh
            this.refreshTokenSubject$.next(true);
            return of(null);
          })
        )
        .subscribe();
    }
  }

  /**
   * Форматировать ошибку для единообразного обработки
   *
   * @param error - Ошибка от HTTP запроса
   * @returns Форматированная ошибка
   */
  private formatError(error: any): Error {
    if (error.error?.detail) {
      return new Error(error.error.detail);
    }
    if (error.error?.message) {
      return new Error(error.error.message);
    }
    if (error.message) {
      return new Error(error.message);
    }
    return new Error('Authentication failed');
  }

  /**
   * Observable для отслеживания необходимости refresh токена
   *
   * @returns Observable<boolean>
   */
  get refreshTokenNeeded$(): Observable<boolean> {
    return this.refreshTokenSubject$.asObservable();
  }

  /**
   * Инициализация проактивного silent refresh
   *
   * Вызывается при запуске приложения в конструкторе.
   * - Проверяет существование токена в localStorage
   * - Если токен валиден - планирует refresh
   * - Подписывается на refreshTokenNeeded$ для автоматического refresh
   */
  private initializeSilentRefresh(): void {
    console.log('[AuthService] Initializing silent refresh mechanism');

    // Подписаться на события необходимости refresh
    this.refreshSubscription = this.refreshTokenNeeded$
      .pipe(
        filter((needsRefresh) => needsRefresh === true),
        switchMap(() => {
          console.log('[AuthService] Proactive refresh triggered');
          return this.performSilentRefresh();
        })
      )
      .subscribe({
        next: () => {
          console.log('[AuthService] Proactive refresh completed successfully');
          // Сбросить флаг
          this.refreshTokenSubject$.next(false);
        },
        error: (error) => {
          console.error('[AuthService] Proactive refresh failed:', error);
          // Сбросить флаг
          this.refreshTokenSubject$.next(false);
        },
      });

    // Проверить существующий токен при startup
    this.checkAndScheduleRefreshOnStartup();
  }

  /**
   * Проверить токен при startup и запланировать refresh если нужно
   *
   * Вызывается при инициализации для поддержки refresh после перезагрузки страницы
   */
  private checkAndScheduleRefreshOnStartup(): void {
    const token = this.getAccessToken();

    if (!token) {
      console.log('[AuthService] No token found on startup');
      return;
    }

    try {
      const payload = this.decodeToken(token);
      const now = Math.floor(Date.now() / 1000);
      const expiresIn = payload.exp - now;

      console.log(
        `[AuthService] Token found on startup, expires in ${expiresIn} seconds`
      );

      if (expiresIn > 0) {
        // Токен еще валиден - запланировать refresh
        this.scheduleTokenRefresh(expiresIn);
      } else {
        // Токен уже истек - попытаться refresh сразу
        console.log('[AuthService] Token expired on startup, attempting refresh');
        this.performSilentRefresh().subscribe({
          error: () => {
            // Если refresh не удался - очистить токены
            this.clearTokens();
          },
        });
      }
    } catch (error) {
      console.error('[AuthService] Failed to check token on startup:', error);
      this.clearTokens();
    }
  }

  /**
   * Выполнить silent refresh токена
   *
   * Проверяет флаг isRefreshing для предотвращения одновременных запросов
   *
   * @returns Observable с результатом refresh
   */
  private performSilentRefresh(): Observable<TokenResponse> {
    // Проверить, не выполняется ли уже refresh
    if (this.isRefreshing) {
      console.log('[AuthService] Refresh already in progress, skipping');
      return of({} as TokenResponse);
    }

    this.isRefreshing = true;

    return this.refreshToken().pipe(
      tap(() => {
        this.isRefreshing = false;
      }),
      catchError((error) => {
        this.isRefreshing = false;
        return throwError(() => error);
      })
    );
  }

  /**
   * Cleanup при уничтожении сервиса
   */
  ngOnDestroy(): void {
    if (this.refreshSubscription) {
      this.refreshSubscription.unsubscribe();
    }
  }
}
