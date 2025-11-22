/**
 * ArtStore Admin UI - Sidebar Component
 * Боковая навигационная панель с меню
 */
import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { Store } from '@ngrx/store';
import { Observable } from 'rxjs';

import { AppState } from '../../../store/app.state';
import { selectSidebarOpen } from '../../../store/ui/ui.selectors';

interface MenuItem {
  label: string;
  icon: string;
  route: string;
  badge?: number;
}

@Component({
  selector: 'app-sidebar',
  imports: [CommonModule, RouterLink, RouterLinkActive],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss',
  standalone: true,
})
export class Sidebar {
  /** NgRx Store */
  private store = inject(Store<AppState>);

  /** Sidebar открыт/закрыт */
  sidebarOpen$: Observable<boolean> = this.store.select(selectSidebarOpen);

  /** Меню items */
  menuItems: MenuItem[] = [
    { label: 'Дашборд', icon: 'bi-house', route: '/dashboard' },
    { label: 'Файлы', icon: 'bi-folder', route: '/files' },
    { label: 'Пользователи', icon: 'bi-people', route: '/users' },
    { label: 'Service Accounts', icon: 'bi-key', route: '/service-accounts' },
    { label: 'Storage Elements', icon: 'bi-hdd', route: '/storage-elements' },
    { label: 'Статистика', icon: 'bi-bar-chart', route: '/statistics' },
    { label: 'Настройки', icon: 'bi-gear', route: '/settings' },
  ];
}
