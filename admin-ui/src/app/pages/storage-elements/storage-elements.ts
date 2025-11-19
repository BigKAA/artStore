/**
 * Storage Elements Component
 *
 * Компонент для просмотра и мониторинга Storage Elements.
 * Функциональность:
 * - Отображение списка Storage Elements с метриками
 * - Фильтрация по mode, status, storage_type
 * - Поиск по name или api_url
 * - Детальный просмотр Storage Element
 * - Сводная статистика системы
 * - Пагинация
 *
 * Sprint 18 Phase 2: Read-only implementation (CRUD в Sprint 19)
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
}
