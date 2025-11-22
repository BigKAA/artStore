/**
 * ArtStore Admin UI - Application Routes
 * Конфигурация маршрутизации с защитой аутентификацией
 */
import { Routes } from '@angular/router';

import { authGuard } from './guards/auth-guard';
import { LoginComponent } from './pages/login/login';
import { MainLayoutComponent } from './components/layout/main-layout';
import { DashboardComponent } from './pages/dashboard/dashboard';
import { AdminUsersComponent } from './pages/admin-users/admin-users';
import { ServiceAccountsComponent } from './pages/service-accounts/service-accounts';
import { StorageElementsComponent } from './pages/storage-elements/storage-elements';
import { FilesComponent } from './pages/files/files';

/**
 * Application Routes
 *
 * Маршруты:
 * - /login (публичный) - страница входа
 * - / (защищенный layout) - основной layout с sidebar и header
 *   - /dashboard - главная страница админ панели
 *   - /admin-users - управление пользователями
 *   - /storage-elements - управление элементами хранения
 *   - /files - управление файлами
 */
export const routes: Routes = [
  // Login page (публичный маршрут)
  {
    path: 'login',
    component: LoginComponent,
    title: 'Login - ArtStore Admin',
  },

  // Main layout с защищенными маршрутами
  {
    path: '',
    component: MainLayoutComponent,
    canActivate: [authGuard],
    children: [
      // Default route - redirect на dashboard
      {
        path: '',
        redirectTo: '/dashboard',
        pathMatch: 'full',
      },

      // Dashboard (главная страница)
      {
        path: 'dashboard',
        component: DashboardComponent,
        title: 'Dashboard - ArtStore Admin',
      },

      // Admin Users Management
      {
        path: 'admin-users',
        component: AdminUsersComponent,
        title: 'Admin Users - ArtStore Admin',
      },

      // Service Accounts Management
      {
        path: 'service-accounts',
        component: ServiceAccountsComponent,
        title: 'Service Accounts - ArtStore Admin',
      },

      // Storage Elements Management
      {
        path: 'storage-elements',
        component: StorageElementsComponent,
        title: 'Storage Elements - ArtStore Admin',
      },

      // Files Management
      {
        path: 'files',
        component: FilesComponent,
        title: 'Files - ArtStore Admin',
      },
    ],
  },

  // Wildcard route - redirect на dashboard
  {
    path: '**',
    redirectTo: '/dashboard',
  },
];
