/**
 * Storage Elements Component
 *
 * Компонент для управления Storage Elements.
 * Функциональность:
 * - Отображение списка Storage Elements с метриками
 * - Создание нового Storage Element
 * - Редактирование существующего Storage Element
 * - Удаление Storage Element
 * - Фильтрация по mode, status, storage_type
 * - Поиск по name или api_url
 * - Детальный просмотр Storage Element
 * - Сводная статистика системы
 * - Пагинация
 *
 * Sprint 19 Phase 2: Full CRUD implementation
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
  StorageElementsSummary
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
    this.page = 1; // Reset to first page
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
      // Показываем все страницы
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      // Показываем первую, последнюю и несколько вокруг текущей
      const halfWindow = Math.floor(maxPagesToShow / 2);
      let start = Math.max(1, this.page - halfWindow);
      let end = Math.min(totalPages, this.page + halfWindow);

      // Корректировка если в начале или в конце
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

  // ==================== CRUD Operations ====================

  /**
   * Открыть модал создания Storage Element
   */
  openCreateModal(): void {
    this.formData = {
      name: '',
      description: '',
      mode: StorageMode.EDIT,
      storage_type: StorageType.LOCAL,
      base_path: '',
      api_url: '',
      api_key: '',
      capacity_bytes: null,
      retention_days: null,
      is_replicated: false,
      replica_count: 0
    };
    this.formErrors = {};
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
  }

  /**
   * Создать Storage Element
   */
  createStorageElement(): void {
    if (!this.validateForm()) {
      return;
    }

    this.isSubmitting = true;
    this.error = null;

    // Преобразование capacity из GB в bytes если указано
    const requestData = { ...this.formData };
    if (requestData.capacity_gb) {
      requestData.capacity_bytes = Math.floor(requestData.capacity_gb * 1024 * 1024 * 1024);
      delete requestData.capacity_gb;
    }

    this.storageElementsService.createStorageElement(requestData).subscribe({
      next: (created) => {
        this.isSubmitting = false;
        this.successMessage = `Storage Element "${created.name}" created successfully`;
        this.closeCreateModal();
        this.loadStorageElements();
        this.loadSummary();

        // Очистить сообщение через 5 секунд
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
   */
  openEditModal(storageElement: StorageElement): void {
    this.selectedStorageElement = storageElement;
    this.formData = {
      name: storageElement.name,
      description: storageElement.description,
      mode: storageElement.mode,
      api_url: storageElement.api_url,
      api_key: '',
      status: storageElement.status,
      capacity_gb: storageElement.capacity_gb,
      retention_days: storageElement.retention_days,
      replica_count: storageElement.replica_count
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
   */
  updateStorageElement(): void {
    if (!this.selectedStorageElement || !this.validateForm(true)) {
      return;
    }

    this.isSubmitting = true;
    this.error = null;

    // Подготовка данных для обновления (только измененные поля)
    const updateData: any = {};
    if (this.formData.name !== this.selectedStorageElement.name) {
      updateData.name = this.formData.name;
    }
    if (this.formData.description !== this.selectedStorageElement.description) {
      updateData.description = this.formData.description;
    }
    if (this.formData.mode !== this.selectedStorageElement.mode) {
      updateData.mode = this.formData.mode;
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
    if (this.formData.capacity_gb !== this.selectedStorageElement.capacity_gb) {
      updateData.capacity_bytes = Math.floor((this.formData.capacity_gb || 0) * 1024 * 1024 * 1024);
    }
    if (this.formData.retention_days !== this.selectedStorageElement.retention_days) {
      updateData.retention_days = this.formData.retention_days;
    }
    if (this.formData.replica_count !== this.selectedStorageElement.replica_count) {
      updateData.replica_count = this.formData.replica_count;
    }

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

  /**
   * Валидация формы
   */
  validateForm(isEdit: boolean = false): boolean {
    this.formErrors = {};
    let isValid = true;

    // Валидация name
    if (!this.formData.name || this.formData.name.trim().length < 3) {
      this.formErrors.name = 'Name must be at least 3 characters';
      isValid = false;
    }

    // Валидация для создания (обязательные поля)
    if (!isEdit) {
      if (!this.formData.base_path || this.formData.base_path.trim().length === 0) {
        this.formErrors.base_path = 'Base path is required';
        isValid = false;
      }

      if (!this.formData.api_url || this.formData.api_url.trim().length === 0) {
        this.formErrors.api_url = 'API URL is required';
        isValid = false;
      }
    }

    // Валидация API URL формата
    if (this.formData.api_url && !this.formData.api_url.match(/^https?:\/\/.+/)) {
      this.formErrors.api_url = 'API URL must start with http:// or https://';
      isValid = false;
    }

    // Валидация capacity_gb
    if (this.formData.capacity_gb !== null && this.formData.capacity_gb !== undefined) {
      if (this.formData.capacity_gb < 0) {
        this.formErrors.capacity_gb = 'Capacity must be positive';
        isValid = false;
      }
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
}
