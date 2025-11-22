/**
 * ArtStore Admin UI - Authentication Guard
 * Functional guard для защиты маршрутов, требующих аутентификации
 */
import { inject } from '@angular/core';
import { Router, CanActivateFn, ActivatedRouteSnapshot, RouterStateSnapshot } from '@angular/router';
import { Store } from '@ngrx/store';
import { map, take } from 'rxjs/operators';

import { AppState } from '../store/app.state';
import { selectIsAuthenticated } from '../store/auth/auth.selectors';

/**
 * Auth Guard (Functional)
 *
 * Проверяет аутентификацию пользователя перед доступом к защищенным маршрутам.
 *
 * Функциональность:
 * - Проверка isAuthenticated из NgRx store
 * - Redirect на /login если пользователь не аутентифицирован
 * - Сохранение requested URL для redirect после успешного входа
 * - Поддержка RxJS observables для асинхронной проверки
 *
 * Usage в routing:
 * ```typescript
 * {
 *   path: 'dashboard',
 *   component: DashboardComponent,
 *   canActivate: [authGuard]
 * }
 * ```
 */
export const authGuard: CanActivateFn = (
  route: ActivatedRouteSnapshot,
  state: RouterStateSnapshot
) => {
  const store = inject(Store<AppState>);
  const router = inject(Router);

  return store.select(selectIsAuthenticated).pipe(
    take(1),
    map((isAuthenticated) => {
      if (isAuthenticated) {
        // Пользователь аутентифицирован - разрешить доступ
        return true;
      } else {
        // Пользователь НЕ аутентифицирован - redirect на login
        console.warn('Access denied: User not authenticated');

        // Сохранить requested URL для redirect после входа
        const returnUrl = state.url;

        // Redirect на login с returnUrl query parameter
        router.navigate(['/login'], {
          queryParams: { returnUrl },
        });

        return false;
      }
    })
  );
};
