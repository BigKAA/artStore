/**
 * ArtStore Admin UI - Login Page Component
 * Компонент страницы входа с OAuth 2.0 Client Credentials authentication
 */
import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Store } from '@ngrx/store';
import { Router, ActivatedRoute } from '@angular/router';
import { Subject, takeUntil, filter } from 'rxjs';

import { AppState } from '../../store/app.state';
import { AuthActions } from '../../store/auth/auth.actions';
import {
  selectAuthLoading,
  selectAuthError,
  selectIsAuthenticated,
} from '../../store/auth/auth.selectors';

/**
 * Login Page Component
 *
 * Функциональность:
 * - Reactive форма с валидацией client_id и client_secret
 * - Интеграция с NgRx store для управления состоянием аутентификации
 * - Автоматический redirect после успешного входа
 * - Отображение ошибок и loading состояний
 * - Bootstrap 5 responsive дизайн
 */
@Component({
  selector: 'app-login',
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './login.html',
  styleUrl: './login.scss',
  standalone: true,
})
export class LoginComponent implements OnInit, OnDestroy {
  private fb = inject(FormBuilder);
  private store = inject(Store<AppState>);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private destroy$ = new Subject<void>();

  /**
   * Return URL для redirect после успешного входа
   */
  private returnUrl = '/dashboard';

  /**
   * Reactive форма для входа
   */
  loginForm!: FormGroup;

  /**
   * Флаг отображения пароля (client_secret)
   */
  showPassword = false;

  /**
   * Observable для loading состояния
   */
  loading$ = this.store.select(selectAuthLoading);

  /**
   * Observable для ошибок аутентификации
   */
  error$ = this.store.select(selectAuthError);

  /**
   * Observable для статуса аутентификации
   */
  isAuthenticated$ = this.store.select(selectIsAuthenticated);

  ngOnInit(): void {
    // Получить returnUrl из query parameters
    this.returnUrl = this.route.snapshot.queryParams['returnUrl'] || '/dashboard';

    this.initForm();
    this.setupAuthRedirect();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  /**
   * Инициализация reactive формы с валидацией
   */
  private initForm(): void {
    this.loginForm = this.fb.group({
      clientId: [
        '',
        [
          Validators.required,
          Validators.minLength(3),
          Validators.maxLength(100),
        ],
      ],
      clientSecret: [
        '',
        [
          Validators.required,
          Validators.minLength(8),
          Validators.maxLength(200),
        ],
      ],
      rememberMe: [true],
    });
  }

  /**
   * Настройка автоматического redirect после успешной аутентификации
   */
  private setupAuthRedirect(): void {
    this.isAuthenticated$
      .pipe(
        takeUntil(this.destroy$),
        filter((isAuth) => isAuth === true)
      )
      .subscribe(() => {
        // Redirect на requested URL или dashboard после успешного входа
        this.router.navigate([this.returnUrl]);
      });
  }

  /**
   * Обработчик submit формы входа
   */
  onSubmit(): void {
    // Проверить валидность формы
    if (this.loginForm.invalid) {
      // Mark all fields as touched для отображения ошибок
      Object.keys(this.loginForm.controls).forEach((key) => {
        this.loginForm.get(key)?.markAsTouched();
      });
      return;
    }

    // Получить значения из формы
    const { clientId, clientSecret } = this.loginForm.value;

    // Dispatch login action
    this.store.dispatch(
      AuthActions.login({
        clientId,
        clientSecret,
      })
    );
  }

  /**
   * Переключить отображение пароля (client_secret)
   */
  togglePasswordVisibility(): void {
    this.showPassword = !this.showPassword;
  }

  /**
   * Проверить, имеет ли поле ошибку валидации
   */
  hasError(fieldName: string, errorType: string): boolean {
    const field = this.loginForm.get(fieldName);
    return !!(field && field.hasError(errorType) && field.touched);
  }

  /**
   * Получить текст ошибки валидации для поля
   */
  getErrorMessage(fieldName: string): string {
    const field = this.loginForm.get(fieldName);

    if (!field || !field.touched) {
      return '';
    }

    if (field.hasError('required')) {
      return `${fieldName === 'clientId' ? 'Client ID' : 'Client Secret'} is required`;
    }

    if (field.hasError('minlength')) {
      const minLength = field.getError('minlength').requiredLength;
      return `Minimum length is ${minLength} characters`;
    }

    if (field.hasError('maxlength')) {
      const maxLength = field.getError('maxlength').requiredLength;
      return `Maximum length is ${maxLength} characters`;
    }

    return '';
  }

  /**
   * Проверить, должно ли поле отображаться с ошибкой
   */
  isFieldInvalid(fieldName: string): boolean {
    const field = this.loginForm.get(fieldName);
    return !!(field && field.invalid && field.touched);
  }

  /**
   * Проверить, должно ли поле отображаться как валидное
   */
  isFieldValid(fieldName: string): boolean {
    const field = this.loginForm.get(fieldName);
    return !!(field && field.valid && field.touched);
  }
}
