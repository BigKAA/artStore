/**
 * ArtStore Admin UI - Main Layout Component
 * Основной layout для всех защищенных страниц с sidebar и header
 */
import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { Store } from '@ngrx/store';

import { AppState } from '../../store/app.state';
import { selectCurrentUser } from '../../store/auth/auth.selectors';
import { SidebarComponent } from './sidebar';
import { HeaderComponent } from './header';

/**
 * Main Layout Component
 *
 * Структура:
 * - Sidebar (слева, фиксированный)
 * - Header (сверху, фиксированный)
 * - Main Content (router-outlet)
 */
@Component({
  selector: 'app-main-layout',
  imports: [CommonModule, RouterModule, SidebarComponent, HeaderComponent],
  templateUrl: './main-layout.html',
  styleUrl: './main-layout.scss',
  standalone: true,
})
export class MainLayoutComponent implements OnInit {
  private store = inject(Store<AppState>);

  /**
   * Флаг состояния sidebar (открыт/закрыт на мобильных)
   */
  sidebarCollapsed = false;

  /**
   * Observable текущего пользователя
   */
  currentUser$ = this.store.select(selectCurrentUser);

  ngOnInit(): void {
    // Определить начальное состояние sidebar на основе размера экрана
    this.checkScreenSize();

    // Слушать изменения размера экрана
    window.addEventListener('resize', () => this.checkScreenSize());
  }

  /**
   * Проверить размер экрана и установить состояние sidebar
   */
  private checkScreenSize(): void {
    // На экранах < 768px sidebar должен быть свернут по умолчанию
    if (window.innerWidth < 768) {
      this.sidebarCollapsed = true;
    }
  }

  /**
   * Переключить состояние sidebar
   */
  toggleSidebar(): void {
    this.sidebarCollapsed = !this.sidebarCollapsed;
  }

  /**
   * Закрыть sidebar (используется на мобильных после клика по ссылке)
   */
  closeSidebar(): void {
    if (window.innerWidth < 768) {
      this.sidebarCollapsed = true;
    }
  }

  /**
   * Проверить, должен ли отображаться overlay
   */
  shouldShowOverlay(): boolean {
    return !this.sidebarCollapsed && window.innerWidth < 768;
  }
}
