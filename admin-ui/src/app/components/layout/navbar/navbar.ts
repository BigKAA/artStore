/**
 * ArtStore Admin UI - Navbar Component
 * Верхняя навигационная панель с профилем пользователя и настройками
 */
import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Store } from '@ngrx/store';
import { Observable } from 'rxjs';

import { AppState } from '../../../store/app.state';
import * as UiActions from '../../../store/ui/ui.actions';
import * as AuthActions from '../../../store/auth/auth.actions';
import {
  selectCurrentUser,
  selectUserDisplayName,
  selectIsAuthenticated,
} from '../../../store/auth/auth.selectors';
import { selectTheme, selectSidebarOpen } from '../../../store/ui/ui.selectors';
import { User } from '../../../store/auth/auth.state';
import { Theme } from '../../../store/ui/ui.state';

@Component({
  selector: 'app-navbar',
  imports: [CommonModule],
  templateUrl: './navbar.html',
  styleUrl: './navbar.scss',
  standalone: true,
})
export class Navbar {
  /** NgRx Store */
  private store = inject(Store<AppState>);

  /** Наблюдаемые данные из store */
  currentUser$: Observable<User | null> = this.store.select(selectCurrentUser);
  displayName$: Observable<string> = this.store.select(selectUserDisplayName);
  isAuthenticated$: Observable<boolean> = this.store.select(selectIsAuthenticated);
  currentTheme$: Observable<Theme> = this.store.select(selectTheme);
  sidebarOpen$: Observable<boolean> = this.store.select(selectSidebarOpen);

  /**
   * Переключить sidebar
   */
  toggleSidebar(): void {
    this.store.dispatch(UiActions.toggleSidebar());
  }

  /**
   * Переключить тему (light/dark)
   */
  toggleTheme(): void {
    this.store.dispatch(UiActions.toggleTheme());
  }

  /**
   * Выход пользователя
   */
  logout(): void {
    this.store.dispatch(AuthActions.logout());
  }
}
