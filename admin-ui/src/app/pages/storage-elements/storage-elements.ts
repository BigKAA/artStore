/**
 * Storage Elements Component
 *
 * Компонент для управления Storage Elements с auto-discovery.
 * Функциональность:
 * - Auto-discovery Storage Element по URL
 * - Создание Storage Element с автоматическим получением информации
 * - Синхронизация данных Storage Elements
 * - Отображение списка Storage Elements с метриками
 * - Редактирование существующего Storage Element (без mode!)
 * - Удаление Storage Element
 * - Фильтрация по mode, status, storage_type
 * - Поиск по name или api_url
 * - Детальный просмотр Storage Element
 * - Сводная статистика системы
 * - Пагинация
 *
 * ВАЖНО: Mode Storage Element определяется ТОЛЬКО его конфигурацией при запуске.
 *        Изменить mode можно только через изменение конфигурации и перезапуск storage element.
 *        Admin Module НЕ МОЖЕТ изменять mode через API.
 *
 * Sprint 19 Phase 2: Auto-discovery implementation
 */

import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  StorageElementsService,
  StorageElement,
  StorageMode,
  StorageStatus,
  StorageType,
  StorageElementsSummary,
  StorageElementDiscoverResponse,
  StorageElementSyncResponse,
  StorageElementCreateRequest
} from '../../services/storage-elements/storage-elements.service';

@Component({
  selector: 'app-storage-elements',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './storage-elements.html',
  styleUrl: './storage-elements.scss'
})
export class StorageElementsComponent implements OnInit {
  // Data
  storageElements: StorageElement[] = [];
  summary: StorageElementsSummary | null = null;
  selectedStorageElement: StorageElement | null = null;

  // Discovery
  discoveryResult: StorageElementDiscoverResponse | null = null;
  isDiscovering: boolean = false;
  discoveryError: string | null = null;

  // Sync
  syncResult: StorageElementSyncResponse | null = null;
  isSyncing: boolean = false;
  syncingElementId: number | null = null;
  isSyncingAll: boolean = false;

  // Filters
  modeFilter: StorageMode | '' = '';
  statusFilter: StorageStatus | '' = '';
  typeFilter: StorageType | '' = '';
  searchQuery: string = '';

  // Pagination
  page: number = 1;
  pageSize: number = 20;
  total: number = 0;

  // UI State
  isLoading: boolean = false;
  error: string | null = null;
  showDetailsModal: boolean = false;
  showCreateModal: boolean = false;
  showEditModal: boolean = false;
  showDeleteModal: boolean = false;
  showSyncResultModal: boolean = false;

  // CRUD State
  formData: any = {};
  formErrors: any = {};
  isSubmitting: boolean = false;
  successMessage: string | null = null;

  // Enums для template
  StorageMode = StorageMode;
  StorageStatus = StorageStatus;
  StorageType = StorageType;

  // Массивы для селектов
  modes = Object.values(StorageMode);
  statuses = Object.values(StorageStatus);
  types = Object.values(StorageType);

  // Math для template
  Math = Math;

  constructor(public storageElementsService: StorageElementsService) {}

  ngOnInit(): void {
    this.loadStorageElements();
    this.loadSummary();
  }

  /**
   * Загрузка списка Storage Elements
   */
  loadStorageElements(): void {
    this.isLoading = true;
    this.error = null;

    const skip = (this.page - 1) * this.pageSize;

    this.storageElementsService.getStorageElements(
      skip,
      this.pageSize,
      this.modeFilter || undefined,
      this.statusFilter || undefined,
      this.typeFilter || undefined,
      this.searchQuery || undefined
    ).subscribe({
      next: (response) => {
        this.storageElements = response.items;
        this.total = response.total;
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Failed to load Storage Elements:', err);
        this.error = 'Failed to load Storage Elements. Please try again.';
        this.isLoading = false;
      }
    });
  }

  /**
   * Загрузка сводной статистики
   */
  loadSummary(): void {
    this.storageElementsService.getStorageElementsSummary().subscribe({
      next: (summary) => {
        this.summary = summary;
      },
      error: (err) => {
        console.error('Failed to load summary:', err);
      }
    });
  }

  /**
   * Применить фильтры
   */
  applyFilters(): void {
    this.page = 1;
    this.loadStorageElements();
  }

  /**
   * Очистить фильтры
   */
  clearFilters(): void {
    this.modeFilter = '';
    this.statusFilter = '';
    this.typeFilter = '';
    this.searchQuery = '';
    this.page = 1;
    this.loadStorageElements();
  }

  /**
   * Изменение страницы
   */
  changePage(newPage: number): void {
    if (newPage < 1 || newPage > this.getTotalPages()) {
      return;
    }
    this.page = newPage;
    this.loadStorageElements();
  }

  /**
   * Получение общего количества страниц
   */
  getTotalPages(): number {
    return Math.ceil(this.total / this.pageSize);
  }

  /**
   * Открыть модал с деталями Storage Element
   */
  viewDetails(storageElement: StorageElement): void {
    this.selectedStorageElement = storageElement;
    this.showDetailsModal = true;
  }

  /**
   * Закрыть модал деталей
   */
  closeDetailsModal(): void {
    this.showDetailsModal = false;
    this.selectedStorageElement = null;
  }

  /**
   * Получение CSS класса для progress bar использования
   */
  getUsageProgressClass(percent: number | null): string {
    if (percent === null) return 'bg-secondary';
    if (percent < 60) return 'bg-success';
    if (percent < 80) return 'bg-warning';
    return 'bg-danger';
  }

  /**
   * Получение массива страниц для пагинации
   */
  getPageNumbers(): number[] {
    const totalPages = this.getTotalPages();
    const pages: number[] = [];
    const maxPagesToShow = 5;

    if (totalPages <= maxPagesToShow) {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      const halfWindow = Math.floor(maxPagesToShow / 2);
      let start = Math.max(1, this.page - halfWindow);
      let end = Math.min(totalPages, this.page + halfWindow);

      if (this.page <= halfWindow) {
        end = maxPagesToShow;
      } else if (this.page >= totalPages - halfWindow) {
        start = totalPages - maxPagesToShow + 1;
      }

      for (let i = start; i <= end; i++) {
        pages.push(i);
      }
    }

    return pages;
  }

  /**
   * Форматирование даты
   */
  formatDate(dateString: string | null): string {
    if (!dateString) return 'N/A';

    const date = new Date(dateString);
    return date.toLocaleString('ru-RU', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  /**
   * Относительное время с последней health check
   */
  getTimeSinceHealthCheck(dateString: string | null): string {
    if (!dateString) return 'Never';

    const now = new Date();
    const lastCheck = new Date(dateString);
    const diffMs = now.getTime() - lastCheck.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} min ago`;

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;

    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
  }

  // ==================== Discovery Operations ====================

  /**
   * Выполнить discovery по URL
   */
  discoverStorageElement(): void {
    if (!this.formData.api_url || this.formData.api_url.trim().length === 0) {
      this.discoveryError = 'Please enter Storage Element URL';
      return;
    }

    this.isDiscovering = true;
    this.discoveryError = null;
    this.discoveryResult = null;

    this.storageElementsService.discoverStorageElement(this.formData.api_url).subscribe({
      next: (result) => {
        this.discoveryResult = result;
        this.isDiscovering = false;

        // Если уже зарегистрирован - показываем предупреждение
        if (result.already_registered) {
          this.discoveryError = `This Storage Element is already registered (ID: ${result.existing_id})`;
        }
      },
      error: (err) => {
        console.error('Discovery failed:', err);
        this.discoveryError = err.error?.detail || 'Failed to discover Storage Element. Check URL and try again.';
        this.isDiscovering = false;
      }
    });
  }

  /**
   * Сбросить результат discovery
   */
  resetDiscovery(): void {
    this.discoveryResult = null;
    this.discoveryError = null;
  }

  // ==================== Sync Operations ====================

  /**
   * Синхронизировать один Storage Element
   */
  syncSingleStorageElement(storageElement: StorageElement): void {
    this.isSyncing = true;
    this.syncingElementId = storageElement.id;
    this.error = null;

    this.storageElementsService.syncStorageElement(storageElement.id).subscribe({
      next: (result) => {
        this.syncResult = result;
        this.isSyncing = false;
        this.syncingElementId = null;

        if (result.success) {
          if (result.changes.length > 0) {
            this.successMessage = `Synced "${result.name}": ${result.changes.length} changes`;
          } else {
            this.successMessage = `"${result.name}" is already up to date`;
          }
          this.loadStorageElements();
          this.loadSummary();
        } else {
          this.error = `Sync failed: ${result.error_message}`;
        }

        setTimeout(() => {
          this.successMessage = null;
        }, 5000);
      },
      error: (err) => {
        console.error('Sync failed:', err);
        this.error = err.error?.detail || 'Failed to sync Storage Element';
        this.isSyncing = false;
        this.syncingElementId = null;
      }
    });
  }

  /**
   * Синхронизировать все Storage Elements
   */
  syncAllStorageElements(): void {
    this.isSyncingAll = true;
    this.error = null;

    this.storageElementsService.syncAllStorageElements(true).subscribe({
      next: (result) => {
        this.isSyncingAll = false;
        this.successMessage = `Sync completed: ${result.synced} synced, ${result.failed} failed`;
        this.loadStorageElements();
        this.loadSummary();

        // Показать детальный результат если есть ошибки
        if (result.failed > 0) {
          const failedNames = result.results
            .filter(r => !r.success)
            .map(r => r.name)
            .join(', ');
          this.error = `Failed to sync: ${failedNames}`;
        }

        setTimeout(() => {
          this.successMessage = null;
        }, 5000);
      },
      error: (err) => {
        console.error('Sync all failed:', err);
        this.error = err.error?.detail || 'Failed to sync Storage Elements';
        this.isSyncingAll = false;
      }
    });
  }

  // ==================== CRUD Operations ====================

  /**
   * Открыть модал создания Storage Element
   * Новая версия с auto-discovery
   */
  openCreateModal(): void {
    this.formData = {
      api_url: '',
      name: '',
      description: '',
      api_key: '',
      retention_days: null,
      is_replicated: false,
      replica_count: 0
    };
    this.formErrors = {};
    this.discoveryResult = null;
    this.discoveryError = null;
    this.successMessage = null;
    this.showCreateModal = true;
  }

  /**
   * Закрыть модал создания
   */
  closeCreateModal(): void {
    this.showCreateModal = false;
    this.formData = {};
    this.formErrors = {};
    this.discoveryResult = null;
    this.discoveryError = null;
  }

  /**
   * Создать Storage Element с auto-discovery
   */
  createStorageElement(): void {
    if (!this.validateCreateForm()) {
      return;
    }

    this.isSubmitting = true;
    this.error = null;

    // Формируем request для создания с auto-discovery
    const requestData: StorageElementCreateRequest = {
      api_url: this.formData.api_url.trim()
    };

    // Добавляем опциональные поля если указаны
    if (this.formData.name && this.formData.name.trim()) {
      requestData.name = this.formData.name.trim();
    }
    if (this.formData.description && this.formData.description.trim()) {
      requestData.description = this.formData.description.trim();
    }
    if (this.formData.api_key && this.formData.api_key.trim()) {
      requestData.api_key = this.formData.api_key.trim();
    }
    if (this.formData.retention_days) {
      requestData.retention_days = this.formData.retention_days;
    }
    if (this.formData.is_replicated) {
      requestData.is_replicated = this.formData.is_replicated;
    }
    if (this.formData.replica_count > 0) {
      requestData.replica_count = this.formData.replica_count;
    }

    this.storageElementsService.createStorageElement(requestData).subscribe({
      next: (created) => {
        this.isSubmitting = false;
        this.successMessage = `Storage Element "${created.name}" created successfully`;
        this.closeCreateModal();
        this.loadStorageElements();
        this.loadSummary();

        setTimeout(() => {
          this.successMessage = null;
        }, 5000);
      },
      error: (err) => {
        console.error('Failed to create Storage Element:', err);
        this.error = err.error?.detail || 'Failed to create Storage Element';
        this.isSubmitting = false;
      }
    });
  }

  /**
   * Открыть модал редактирования Storage Element
   * ВАЖНО: mode НЕ редактируется!
   */
  openEditModal(storageElement: StorageElement): void {
    this.selectedStorageElement = storageElement;
    this.formData = {
      name: storageElement.name,
      description: storageElement.description || '',
      api_url: storageElement.api_url,
      api_key: '',
      status: storageElement.status,
      retention_days: storageElement.retention_days,
      replica_count: storageElement.replica_count
      // mode НЕ включен - редактирование через конфигурацию storage element
    };
    this.formErrors = {};
    this.successMessage = null;
    this.showEditModal = true;
  }

  /**
   * Закрыть модал редактирования
   */
  closeEditModal(): void {
    this.showEditModal = false;
    this.selectedStorageElement = null;
    this.formData = {};
    this.formErrors = {};
  }

  /**
   * Обновить Storage Element
   * ВАЖНО: mode НЕ может быть изменен через API!
   */
  updateStorageElement(): void {
    if (!this.selectedStorageElement || !this.validateEditForm()) {
      return;
    }

    this.isSubmitting = true;
    this.error = null;

    // Подготовка данных для обновления (только измененные поля, БЕЗ mode)
    const updateData: any = {};

    if (this.formData.name !== this.selectedStorageElement.name) {
      updateData.name = this.formData.name;
    }
    if (this.formData.description !== (this.selectedStorageElement.description || '')) {
      updateData.description = this.formData.description;
    }
    if (this.formData.api_url !== this.selectedStorageElement.api_url) {
      updateData.api_url = this.formData.api_url;
    }
    if (this.formData.api_key) {
      updateData.api_key = this.formData.api_key;
    }
    if (this.formData.status !== this.selectedStorageElement.status) {
      updateData.status = this.formData.status;
    }
    if (this.formData.retention_days !== this.selectedStorageElement.retention_days) {
      updateData.retention_days = this.formData.retention_days;
    }
    if (this.formData.replica_count !== this.selectedStorageElement.replica_count) {
      updateData.replica_count = this.formData.replica_count;
    }
    // mode НЕ включаем - изменяется только через конфигурацию storage element

    this.storageElementsService.updateStorageElement(this.selectedStorageElement.id, updateData).subscribe({
      next: (updated) => {
        this.isSubmitting = false;
        this.successMessage = `Storage Element "${updated.name}" updated successfully`;
        this.closeEditModal();
        this.loadStorageElements();
        this.loadSummary();

        setTimeout(() => {
          this.successMessage = null;
        }, 5000);
      },
      error: (err) => {
        console.error('Failed to update Storage Element:', err);
        this.error = err.error?.detail || 'Failed to update Storage Element';
        this.isSubmitting = false;
      }
    });
  }

  /**
   * Открыть модал подтверждения удаления
   */
  openDeleteModal(storageElement: StorageElement): void {
    this.selectedStorageElement = storageElement;
    this.successMessage = null;
    this.showDeleteModal = true;
  }

  /**
   * Закрыть модал удаления
   */
  closeDeleteModal(): void {
    this.showDeleteModal = false;
    this.selectedStorageElement = null;
  }

  /**
   * Удалить Storage Element
   */
  deleteStorageElement(): void {
    if (!this.selectedStorageElement) {
      return;
    }

    this.isSubmitting = true;
    this.error = null;

    this.storageElementsService.deleteStorageElement(this.selectedStorageElement.id).subscribe({
      next: () => {
        this.isSubmitting = false;
        this.successMessage = `Storage Element "${this.selectedStorageElement!.name}" deleted successfully`;
        this.closeDeleteModal();
        this.loadStorageElements();
        this.loadSummary();

        setTimeout(() => {
          this.successMessage = null;
        }, 5000);
      },
      error: (err) => {
        console.error('Failed to delete Storage Element:', err);
        this.error = err.error?.detail || 'Failed to delete Storage Element';
        this.isSubmitting = false;
      }
    });
  }

  // ==================== Validation ====================

  /**
   * Валидация формы создания (с auto-discovery)
   */
  validateCreateForm(): boolean {
    this.formErrors = {};
    let isValid = true;

    // Обязательно: api_url
    if (!this.formData.api_url || this.formData.api_url.trim().length === 0) {
      this.formErrors.api_url = 'API URL is required';
      isValid = false;
    } else if (!this.formData.api_url.match(/^https?:\/\/.+/)) {
      this.formErrors.api_url = 'API URL must start with http:// or https://';
      isValid = false;
    }

    // Опционально: name (если указано, минимум 3 символа)
    if (this.formData.name && this.formData.name.trim().length > 0 && this.formData.name.trim().length < 3) {
      this.formErrors.name = 'Name must be at least 3 characters';
      isValid = false;
    }

    // Валидация retention_days
    if (this.formData.retention_days !== null && this.formData.retention_days !== undefined) {
      if (this.formData.retention_days < 1) {
        this.formErrors.retention_days = 'Retention days must be at least 1';
        isValid = false;
      }
    }

    // Валидация replica_count
    if (this.formData.replica_count < 0) {
      this.formErrors.replica_count = 'Replica count cannot be negative';
      isValid = false;
    }

    return isValid;
  }

  /**
   * Валидация формы редактирования
   */
  validateEditForm(): boolean {
    this.formErrors = {};
    let isValid = true;

    // Валидация name
    if (!this.formData.name || this.formData.name.trim().length < 3) {
      this.formErrors.name = 'Name must be at least 3 characters';
      isValid = false;
    }

    // Валидация API URL
    if (this.formData.api_url && !this.formData.api_url.match(/^https?:\/\/.+/)) {
      this.formErrors.api_url = 'API URL must start with http:// or https://';
      isValid = false;
    }

    // Валидация retention_days
    if (this.formData.retention_days !== null && this.formData.retention_days !== undefined) {
      if (this.formData.retention_days < 1) {
        this.formErrors.retention_days = 'Retention days must be at least 1';
        isValid = false;
      }
    }

    // Валидация replica_count
    if (this.formData.replica_count < 0) {
      this.formErrors.replica_count = 'Replica count cannot be negative';
      isValid = false;
    }

    return isValid;
  }

  /**
   * Проверка - можно ли редактировать mode
   * Всегда false - mode только через конфигурацию storage element
   */
  canEditMode(): boolean {
    return this.storageElementsService.canEditMode();
  }

  /**
   * Получение подсказки почему mode нельзя изменить
   */
  getModeEditHint(): string {
    return this.storageElementsService.getModeEditHint();
  }
}
