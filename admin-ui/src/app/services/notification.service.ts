/**
 * NotificationService - Сервис для отображения toast уведомлений
 *
 * Обеспечивает показ уведомлений поверх всех элементов, включая модальные окна.
 * Использует Bootstrap Toast компоненты с высоким z-index.
 */
import { Injectable, signal, computed } from '@angular/core';

/**
 * Тип уведомления - определяет цвет и иконку
 */
export type NotificationType = 'success' | 'error' | 'warning' | 'info';

/**
 * Интерфейс уведомления
 */
export interface Notification {
  id: number;
  type: NotificationType;
  message: string;
  title?: string;
  duration: number; // миллисекунды, 0 = не исчезает автоматически
  timestamp: Date;
}

/**
 * Конфигурация иконок и цветов для типов уведомлений
 */
export const NOTIFICATION_CONFIG: Record<NotificationType, { icon: string; bgClass: string; textClass: string }> = {
  success: {
    icon: 'bi-check-circle-fill',
    bgClass: 'bg-success',
    textClass: 'text-white'
  },
  error: {
    icon: 'bi-exclamation-triangle-fill',
    bgClass: 'bg-danger',
    textClass: 'text-white'
  },
  warning: {
    icon: 'bi-exclamation-circle-fill',
    bgClass: 'bg-warning',
    textClass: 'text-dark'
  },
  info: {
    icon: 'bi-info-circle-fill',
    bgClass: 'bg-info',
    textClass: 'text-white'
  }
};

/**
 * Сервис уведомлений
 *
 * Использование:
 * ```typescript
 * constructor(private notification: NotificationService) {}
 *
 * // Показать ошибку
 * this.notification.error('Пользователь уже существует');
 *
 * // Показать успех
 * this.notification.success('Пользователь создан');
 *
 * // Показать с заголовком
 * this.notification.error('Детали ошибки', 'Ошибка валидации');
 * ```
 */
@Injectable({
  providedIn: 'root'
})
export class NotificationService {
  // Счетчик для уникальных ID
  private nextId = 1;

  // Signal для хранения активных уведомлений
  private _notifications = signal<Notification[]>([]);

  // Публичный readonly доступ к уведомлениям
  readonly notifications = this._notifications.asReadonly();

  // Computed: есть ли активные уведомления
  readonly hasNotifications = computed(() => this._notifications().length > 0);

  /**
   * Показать уведомление об ошибке
   * @param message - текст сообщения
   * @param title - заголовок (опционально)
   * @param duration - длительность показа в мс (по умолчанию 8000мс для ошибок)
   */
  error(message: string, title?: string, duration: number = 8000): void {
    this.show('error', message, title, duration);
  }

  /**
   * Показать уведомление об успехе
   * @param message - текст сообщения
   * @param title - заголовок (опционально)
   * @param duration - длительность показа в мс (по умолчанию 5000мс)
   */
  success(message: string, title?: string, duration: number = 5000): void {
    this.show('success', message, title, duration);
  }

  /**
   * Показать предупреждение
   * @param message - текст сообщения
   * @param title - заголовок (опционально)
   * @param duration - длительность показа в мс (по умолчанию 6000мс)
   */
  warning(message: string, title?: string, duration: number = 6000): void {
    this.show('warning', message, title, duration);
  }

  /**
   * Показать информационное уведомление
   * @param message - текст сообщения
   * @param title - заголовок (опционально)
   * @param duration - длительность показа в мс (по умолчанию 5000мс)
   */
  info(message: string, title?: string, duration: number = 5000): void {
    this.show('info', message, title, duration);
  }

  /**
   * Показать уведомление
   * @param type - тип уведомления
   * @param message - текст сообщения
   * @param title - заголовок (опционально)
   * @param duration - длительность показа в мс (0 = не исчезает)
   */
  show(type: NotificationType, message: string, title?: string, duration: number = 5000): void {
    const notification: Notification = {
      id: this.nextId++,
      type,
      message,
      title,
      duration,
      timestamp: new Date()
    };

    // Добавляем уведомление в начало списка (новые сверху)
    this._notifications.update(notifications => [notification, ...notifications]);

    // Автоматическое удаление через указанное время
    if (duration > 0) {
      setTimeout(() => {
        this.dismiss(notification.id);
      }, duration);
    }
  }

  /**
   * Закрыть уведомление по ID
   * @param id - ID уведомления
   */
  dismiss(id: number): void {
    this._notifications.update(notifications =>
      notifications.filter(n => n.id !== id)
    );
  }

  /**
   * Закрыть все уведомления
   */
  dismissAll(): void {
    this._notifications.set([]);
  }
}
