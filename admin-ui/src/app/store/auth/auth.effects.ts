/**
 * ArtStore Admin UI - Authentication Effects
 * NgRx Effects для интеграции AuthService с store
 */
import { inject, Injectable } from '@angular/core';
import { Router } from '@angular/router';
import { Actions, createEffect, ofType } from '@ngrx/effects';
import { Store } from '@ngrx/store';
import { of, EMPTY } from 'rxjs';
import {
  map,
  catchError,
  switchMap,
  tap,
  withLatestFrom,
  filter,
} from 'rxjs/operators';

import { AuthService } from '../../services/auth';
import { AuthActions } from './auth.actions';
import { UiActions } from '../ui/ui.actions';
import { AppState } from '../app.state';
import { selectAccessToken } from './auth.selectors';
import { User } from './auth.state';

/**
 * Authentication Effects
 *
 * Связывает NgRx actions с AuthService для выполнения side effects
 */
@Injectable()
export class AuthEffects {
  private actions$ = inject(Actions);
  private authService = inject(AuthService);
  private store = inject(Store<AppState>);
  private router = inject(Router);

  /**
   * Effect: Login
   *
   * Слушает login action, вызывает AuthService.login(),
   * и dispatch loginSuccess или loginFailure
   */
  login$ = createEffect(() =>
    this.actions$.pipe(
      ofType(AuthActions.login),
      switchMap(({ username, password }) =>
        this.authService.login(username, password).pipe(
          // После успешного login - получить user info
          switchMap((tokenResponse) =>
            this.authService.getUserInfo().pipe(
              map((userInfo) => {
                // Преобразовать UserInfoResponse в User
                const user: User = {
                  id: userInfo.id,
                  username: userInfo.username,
                  email: userInfo.email,
                  role: userInfo.role,
                  displayName: userInfo.displayName,
                };

                return AuthActions.loginSuccess({
                  accessToken: tokenResponse.access_token,
                  refreshToken: tokenResponse.refresh_token,
                  user,
                });
              }),
              catchError((error) => {
                console.error('Failed to get user info:', error);
                // Если не удалось получить user info - все равно считаем login успешным
                return of(
                  AuthActions.loginSuccess({
                    accessToken: tokenResponse.access_token,
                    refreshToken: tokenResponse.refresh_token,
                    user: null,
                  })
                );
              })
            )
          ),
          catchError((error) => {
            console.error('Login failed:', error);
            return of(
              AuthActions.loginFailure({
                error: error.message || 'Login failed',
              })
            );
          })
        )
      )
    )
  );

  /**
   * Effect: Login Success
   *
   * Показывает уведомление об успешном входе
   */
  loginSuccess$ = createEffect(() =>
    this.actions$.pipe(
      ofType(AuthActions.loginSuccess),
      map(({ user }) =>
        UiActions.addNotification({
          notification: {
            type: 'success',
            title: 'Login Successful',
            message: `Welcome, ${user?.displayName || user?.username || 'User'}!`,
            autoHide: 3000,
          },
        })
      )
    )
  );

  /**
   * Effect: Login Failure
   *
   * Показывает уведомление об ошибке входа
   */
  loginFailure$ = createEffect(() =>
    this.actions$.pipe(
      ofType(AuthActions.loginFailure),
      map(({ error }) =>
        UiActions.addNotification({
          notification: {
            type: 'error',
            title: 'Login Failed',
            message: error,
            autoHide: 5000,
          },
        })
      )
    )
  );

  /**
   * Effect: Refresh Token
   *
   * Слушает refreshToken action и вызывает AuthService.refreshToken()
   */
  refreshToken$ = createEffect(() =>
    this.actions$.pipe(
      ofType(AuthActions.refreshToken),
      switchMap(() =>
        this.authService.refreshToken().pipe(
          map((tokenResponse) =>
            AuthActions.refreshTokenSuccess({
              accessToken: tokenResponse.access_token,
              refreshToken: tokenResponse.refresh_token,
            })
          ),
          catchError((error) => {
            console.error('Token refresh failed:', error);
            return of(
              AuthActions.refreshTokenFailure({
                error: error.message || 'Token refresh failed',
              })
            );
          })
        )
      )
    )
  );

  /**
   * Effect: Refresh Token Failure
   *
   * При неудачном refresh - выполнить logout
   */
  refreshTokenFailure$ = createEffect(() =>
    this.actions$.pipe(
      ofType(AuthActions.refreshTokenFailure),
      map(() => AuthActions.logout())
    )
  );

  /**
   * Effect: Logout
   *
   * Очистить токены из AuthService, показать уведомление и перенаправить на login
   */
  logout$ = createEffect(
    () =>
      this.actions$.pipe(
        ofType(AuthActions.logout),
        tap(() => {
          console.log('[AuthEffects] Logout effect triggered');

          // Сначала очистить токены
          this.authService.logout();
          console.log('[AuthEffects] Tokens cleared');

          // Показать уведомление
          this.store.dispatch(
            UiActions.addNotification({
              notification: {
                type: 'info',
                title: 'Logged Out',
                message: 'You have been logged out successfully',
                autoHide: 3000,
              },
            })
          );
          console.log('[AuthEffects] Notification dispatched');

          // Перенаправить на login страницу
          this.router.navigate(['/login']);
          console.log('[AuthEffects] Navigation to /login triggered');
        })
      ),
    { dispatch: false }
  );

  /**
   * Effect: Restore Session
   *
   * При старте приложения - попытаться восстановить сессию из localStorage
   */
  restoreSession$ = createEffect(() =>
    this.actions$.pipe(
      ofType(AuthActions.restoreSession),
      switchMap(() => {
        const accessToken = this.authService.getAccessToken();
        const refreshToken = this.authService.getRefreshToken();

        // Проверить, есть ли сохраненные токены
        if (!accessToken) {
          console.log('No saved tokens found');
          return of(AuthActions.restoreSessionFailure());
        }

        // Проверить, валиден ли токен
        if (!this.authService.isTokenValid()) {
          console.log('Saved token is invalid');
          // Попытаться refresh если есть refresh token
          if (refreshToken) {
            return of(AuthActions.refreshToken());
          }
          return of(AuthActions.restoreSessionFailure());
        }

        // Токен валиден - получить user info
        return this.authService.getUserInfo().pipe(
          map((userInfo) => {
            const user: User = {
              id: userInfo.id,
              username: userInfo.username,
              email: userInfo.email,
              role: userInfo.role,
              displayName: userInfo.displayName,
            };

            return AuthActions.loginSuccess({
              accessToken,
              refreshToken,
              user,
            });
          }),
          catchError((error) => {
            console.error('Failed to restore session:', error);
            // При неудаче - попытаться refresh
            if (refreshToken) {
              return of(AuthActions.refreshToken());
            }
            return of(AuthActions.restoreSessionFailure());
          })
        );
      })
    )
  );

  /**
   * Effect: Auto Refresh Token
   *
   * Автоматически refresh токен когда он истекает
   */
  autoRefresh$ = createEffect(() =>
    this.authService.refreshTokenNeeded$.pipe(
      filter((needed) => needed),
      withLatestFrom(this.store.select(selectAccessToken)),
      filter(([, token]) => !!token),
      map(() => AuthActions.refreshToken())
    )
  );
}
