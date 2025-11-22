/**
 * ArtStore Admin UI - Header Component
 * Верхняя панель с user info и действиями
 */
import { Component, Input, Output, EventEmitter, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Store } from '@ngrx/store';

import { AppState } from '../../store/app.state';
import { AuthActions } from '../../store/auth/auth.actions';
import { User } from '../../store/auth/auth.state';

/**
 * Header Component
 *
 * Верхняя панель с:
 * - Кнопкой toggle sidebar
 * - Информацией о пользователе
 * - Dropdown меню с logout
 */
@Component({
  selector: 'app-header',
  imports: [CommonModule],
  templateUrl: './header.html',
  styleUrl: './header.scss',
  standalone: true,
})
export class HeaderComponent {
  private store = inject(Store<AppState>);

  /**
   * Текущий пользователь
   */
  @Input() user: User | null = null;

  /**
   * Event для toggle sidebar
   */
  @Output() toggleSidebar = new EventEmitter<void>();

  /**
   * Состояние user dropdown
   */
  userDropdownOpen = false;

  /**
   * Toggle sidebar
   */
  onToggleSidebar(): void {
    this.toggleSidebar.emit();
  }

  /**
   * Toggle user dropdown
   */
  toggleUserDropdown(): void {
    this.userDropdownOpen = !this.userDropdownOpen;
  }

  /**
   * Закрыть user dropdown
   */
  closeUserDropdown(): void {
    this.userDropdownOpen = false;
  }

  /**
   * Logout
   */
  onLogout(): void {
    console.log('[HeaderComponent] onLogout() called');
    this.closeUserDropdown();
    console.log('[HeaderComponent] Dropdown closed');
    // Dispatch logout action - навигация будет выполнена в logout effect
    this.store.dispatch(AuthActions.logout());
    console.log('[HeaderComponent] Logout action dispatched');
  }

  /**
   * Получить инициалы пользователя
   */
  getUserInitials(): string {
    if (!this.user) return '?';

    if (this.user.displayName) {
      const parts = this.user.displayName.split(' ');
      if (parts.length >= 2) {
        return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
      }
      return this.user.displayName[0].toUpperCase();
    }

    return this.user.username?.[0]?.toUpperCase() || '?';
  }

  /**
   * Получить отображаемое имя пользователя
   */
  getUserDisplayName(): string {
    if (!this.user) return 'Unknown User';
    return this.user.displayName || this.user.username || 'Unknown User';
  }

  /**
   * Получить роль пользователя для отображения
   */
  getUserRoleLabel(): string {
    if (!this.user || !this.user.role) return 'User';

    const roleLabels: Record<string, string> = {
      super_admin: 'Super Administrator',
      admin: 'Administrator',
      user: 'User',
    };

    return roleLabels[this.user.role] || this.user.role;
  }
}
