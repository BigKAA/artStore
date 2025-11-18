/**
 * ArtStore Admin UI - Application Routes
 * Конфигурация маршрутизации с защитой аутентификацией
 */
import { Routes } from '@angular/router';

import { authGuard } from './guards/auth-guard';
import { LoginComponent } from './pages/login/login';
import { DashboardComponent } from './pages/dashboard/dashboard';

/**
 * Application Routes
 *
 * Маршруты:
 * - /login (публичный) - страница входа
 * - /dashboard (защищенный) - главная страница админ панели
 * - / (redirect) - автоматический redirect на dashboard или login
 */
export const routes: Routes = [
  // Default route - redirect на dashboard (guard перенаправит на login если не авторизован)
  {
    path: '',
    redirectTo: '/dashboard',
    pathMatch: 'full',
  },

  // Login page (публичный маршрут)
  {
    path: 'login',
    component: LoginComponent,
    title: 'Login - ArtStore Admin',
  },

  // Dashboard (защищенный маршрут)
  {
    path: 'dashboard',
    component: DashboardComponent,
    canActivate: [authGuard],
    title: 'Dashboard - ArtStore Admin',
  },

  // Wildcard route - redirect на dashboard
  {
    path: '**',
    redirectTo: '/dashboard',
  },
];
