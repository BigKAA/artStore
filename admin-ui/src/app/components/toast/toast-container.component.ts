/**
 * ToastContainerComponent - Контейнер для отображения toast уведомлений
 *
 * Отображает уведомления поверх всех элементов интерфейса (z-index: 1100).
 * Модальные окна Bootstrap имеют z-index: 1050, поэтому toast будет всегда виден.
 */
import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NotificationService, NOTIFICATION_CONFIG, Notification } from '../../services/notification.service';

@Component({
  selector: 'app-toast-container',
  standalone: true,
  imports: [CommonModule],
  template: `
    <!-- Toast Container - позиционируется в правом верхнем углу поверх всего -->
    <div
      class="toast-container position-fixed top-0 end-0 p-3"
      style="z-index: 1100;"
      aria-live="polite"
      aria-atomic="true">

      @for (notification of notificationService.notifications(); track notification.id) {
        <div
          class="toast show"
          role="alert"
          aria-live="assertive"
          aria-atomic="true"
          [class.border-0]="true">

          <!-- Toast Header -->
          <div
            class="toast-header"
            [class]="getHeaderClass(notification)">
            <i class="bi me-2" [class]="getIconClass(notification)"></i>
            <strong class="me-auto">{{ getTitle(notification) }}</strong>
            <small>{{ getTimeAgo(notification) }}</small>
            <button
              type="button"
              class="btn-close"
              [class.btn-close-white]="isLightText(notification)"
              aria-label="Закрыть"
              (click)="dismiss(notification.id)">
            </button>
          </div>

          <!-- Toast Body -->
          <div class="toast-body">
            {{ notification.message }}
          </div>
        </div>
      }
    </div>
  `,
  styles: [`
    /* Анимация появления toast */
    .toast {
      animation: slideIn 0.3s ease-out;
      margin-bottom: 0.5rem;
      min-width: 300px;
      max-width: 450px;
      box-shadow: 0 0.5rem 1rem rgba(0, 0, 0, 0.15);
    }

    @keyframes slideIn {
      from {
        transform: translateX(100%);
        opacity: 0;
      }
      to {
        transform: translateX(0);
        opacity: 1;
      }
    }

    /* Стиль для toast-body с улучшенной читаемостью */
    .toast-body {
      background-color: #fff;
      padding: 0.75rem 1rem;
      font-size: 0.9rem;
      line-height: 1.4;
    }

    /* Стили заголовков */
    .toast-header {
      padding: 0.5rem 0.75rem;
    }

    .toast-header.bg-danger,
    .toast-header.bg-success,
    .toast-header.bg-info {
      color: white;
    }

    .toast-header.bg-warning {
      color: #212529;
    }
  `]
})
export class ToastContainerComponent {
  // Инжектируем сервис уведомлений
  protected readonly notificationService = inject(NotificationService);

  /**
   * Получить класс для header toast
   */
  getHeaderClass(notification: Notification): string {
    const config = NOTIFICATION_CONFIG[notification.type];
    return `${config.bgClass} ${config.textClass}`;
  }

  /**
   * Получить класс иконки
   */
  getIconClass(notification: Notification): string {
    return NOTIFICATION_CONFIG[notification.type].icon;
  }

  /**
   * Нужен ли белый цвет для close button
   */
  isLightText(notification: Notification): boolean {
    return notification.type !== 'warning';
  }

  /**
   * Получить заголовок уведомления
   */
  getTitle(notification: Notification): string {
    if (notification.title) {
      return notification.title;
    }

    // Заголовки по умолчанию
    switch (notification.type) {
      case 'success': return 'Успешно';
      case 'error': return 'Ошибка';
      case 'warning': return 'Внимание';
      case 'info': return 'Информация';
    }
  }

  /**
   * Получить относительное время
   */
  getTimeAgo(notification: Notification): string {
    const seconds = Math.floor((new Date().getTime() - notification.timestamp.getTime()) / 1000);

    if (seconds < 5) return 'только что';
    if (seconds < 60) return `${seconds} сек. назад`;

    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} мин. назад`;

    return notification.timestamp.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  }

  /**
   * Закрыть уведомление
   */
  dismiss(id: number): void {
    this.notificationService.dismiss(id);
  }
}
