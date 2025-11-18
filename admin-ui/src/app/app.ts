/**
 * ArtStore Admin UI - Root Application Component
 * Корневой компонент приложения с восстановлением сессии
 */
import { Component, signal, OnInit, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { Store } from '@ngrx/store';

import { AppState } from './store/app.state';
import { AuthActions } from './store/auth/auth.actions';

/**
 * Root App Component
 *
 * Функциональность:
 * - Инициализация приложения
 * - Автоматическое восстановление сессии из localStorage при старте
 * - Routing outlet для отображения страниц
 */
@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.scss',
  standalone: true,
})
export class App implements OnInit {
  private store = inject(Store<AppState>);

  protected readonly title = signal('artstore-admin-ui');

  ngOnInit(): void {
    // Dispatch restoreSession action при старте приложения
    // Это попытается восстановить аутентификацию из localStorage
    this.store.dispatch(AuthActions.restoreSession());
  }
}
