/**
 * ArtStore Admin UI - Sidebar Component
 * Навигационное меню для админ панели
 */
import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';

/**
 * Интерфейс элемента навигации
 */
interface NavItem {
  path: string;
  icon: string;
  label: string;
  badge?: string;
  badgeClass?: string;
}

/**
 * Sidebar Component
 *
 * Боковое навигационное меню с:
 * - Списком разделов админ панели
 * - Активным состоянием для текущего раздела
 * - Адаптивным поведением для мобильных
 */
@Component({
  selector: 'app-sidebar',
  imports: [CommonModule, RouterModule],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss',
  standalone: true,
})
export class SidebarComponent {
  /**
   * Состояние sidebar (свернут/развернут)
   */
  @Input() collapsed = false;

  /**
   * Event при клике по ссылке (для закрытия sidebar на мобильных)
   */
  @Output() linkClick = new EventEmitter<void>();

  /**
   * Навигационные элементы
   */
  navItems: NavItem[] = [
    {
      path: '/dashboard',
      icon: 'bi-speedometer2',
      label: 'Dashboard',
    },
    {
      path: '/admin-users',
      icon: 'bi-people-fill',
      label: 'Admin Users',
    },
    {
      path: '/storage-elements',
      icon: 'bi-hdd-stack-fill',
      label: 'Storage Elements',
    },
    {
      path: '/files',
      icon: 'bi-file-earmark-fill',
      label: 'Files',
    },
  ];

  constructor(private router: Router) {}

  /**
   * Проверить, активен ли данный маршрут
   */
  isActive(path: string): boolean {
    return this.router.url === path || this.router.url.startsWith(path + '/');
  }

  /**
   * Обработать клик по навигационной ссылке
   */
  onLinkClick(): void {
    this.linkClick.emit();
  }
}
