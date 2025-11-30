/**
 * ArtStore Admin UI - Files Component
 * Управление файлами в системе: поиск, загрузка, скачивание
 */
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpEventType } from '@angular/common/http';
import { FilesService } from './services/files.service';
import {
  FileMetadata,
  SearchRequest,
  SearchResponse
} from './models';
import { NotificationService } from '../../services/notification.service';

@Component({
  selector: 'app-files',
  imports: [CommonModule, FormsModule],
  templateUrl: './files.html',
  styleUrl: './files.scss',
  standalone: true,
})
export class FilesComponent implements OnInit {
  // Данные файлов
  files: FileMetadata[] = [];
  totalCount: number = 0;

  // Пагинация
  currentPage: number = 1;
  pageSize: number = 20;

  // Поиск и фильтры
  searchQuery: string = '';
  selectedFileType: string = '';
  dateFrom: string = '';
  dateTo: string = '';

  // UI состояние
  loading: boolean = false;
  showUploadModal: boolean = false;
  uploadProgress: number = 0;

  // Upload modal fields
  selectedFile: File | null = null;
  uploadDescription: string = '';

  // Math для template
  Math = Math;

  constructor(
    private filesService: FilesService,
    private notification: NotificationService
  ) {}

  ngOnInit(): void {
    this.loadFiles();
  }

  /**
   * Загрузка списка файлов с текущими фильтрами
   */
  loadFiles(): void {
    this.loading = true;

    const request: SearchRequest = {
      query: this.searchQuery || '',  // Empty string returns all files
      file_extension: this.selectedFileType || undefined,
      created_after: this.dateFrom ? new Date(this.dateFrom) : undefined,
      created_before: this.dateTo ? new Date(this.dateTo) : undefined,
      mode: 'partial',
      limit: this.pageSize,
      offset: (this.currentPage - 1) * this.pageSize,
      sort_by: 'created_at',
      sort_order: 'desc'
    };

    this.filesService.searchFiles(request).subscribe({
      next: (response: SearchResponse) => {
        this.files = response.results;
        this.totalCount = response.total_count;
        this.loading = false;
      },
      error: (err) => {
        this.notification.error('Ошибка при загрузке файлов: ' + (err.error?.detail || err.message));
        this.loading = false;
      }
    });
  }

  /**
   * Поиск по запросу
   */
  onSearch(): void {
    this.currentPage = 1;
    this.loadFiles();
  }

  /**
   * Применение фильтров
   */
  onApplyFilters(): void {
    this.currentPage = 1;
    this.loadFiles();
  }

  /**
   * Сброс фильтров
   */
  onResetFilters(): void {
    this.searchQuery = '';
    this.selectedFileType = '';
    this.dateFrom = '';
    this.dateTo = '';
    this.currentPage = 1;
    this.loadFiles();
  }

  /**
   * Смена страницы
   */
  onPageChange(page: number): void {
    if (page < 1 || page > this.totalPages) {
      return;
    }
    this.currentPage = page;
    this.loadFiles();
  }

  /**
   * Открытие modal для загрузки файла
   */
  openUploadModal(): void {
    this.showUploadModal = true;
    this.uploadProgress = 0;
    this.selectedFile = null;
    this.uploadDescription = '';
  }

  /**
   * Закрытие modal загрузки
   */
  closeUploadModal(): void {
    this.showUploadModal = false;
    this.uploadProgress = 0;
    this.selectedFile = null;
    this.uploadDescription = '';
  }

  /**
   * Выбор файла в upload modal
   */
  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      this.selectedFile = input.files[0];
    }
  }

  /**
   * Загрузка файла
   */
  onFileUpload(): void {
    if (!this.selectedFile) {
      this.notification.error('Выберите файл для загрузки');
      return;
    }

    const uploadRequest = {
      file: this.selectedFile,
      description: this.uploadDescription || undefined,
      storage_mode: 'edit' as const,
      compress: false,
      compression_algorithm: 'gzip' as const
    };

    this.filesService.uploadFile(uploadRequest).subscribe({
      next: (event) => {
        if (event.type === HttpEventType.UploadProgress) {
          // Обновление прогресса загрузки
          this.uploadProgress = Math.round(
            (event.loaded / (event.total || event.loaded)) * 100
          );
        } else if (event.type === HttpEventType.Response) {
          // Загрузка завершена
          this.notification.success(`Файл "${this.selectedFile?.name}" успешно загружен`);
          this.closeUploadModal();
          this.loadFiles(); // Обновить список файлов
        }
      },
      error: (err) => {
        this.notification.error('Ошибка при загрузке файла: ' + (err.error?.detail || err.message));
        this.uploadProgress = 0;
      }
    });
  }

  /**
   * Скачивание файла
   */
  onDownloadFile(file: FileMetadata): void {
    this.filesService.downloadFile(file.id).subscribe({
      next: (blob: Blob) => {
        this.filesService.triggerBrowserDownload(blob, file.filename);
        this.notification.success(`Файл "${file.filename}" успешно загружен`);
      },
      error: (err) => {
        this.notification.error(`Ошибка при скачивании файла "${file.filename}": ` + (err.error?.detail || err.message));
      }
    });
  }

  /**
   * Форматирование размера файла
   */
  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  }

  /**
   * Форматирование даты
   */
  formatDate(date: Date): string {
    const d = new Date(date);
    return d.toLocaleDateString('ru-RU') + ' ' + d.toLocaleTimeString('ru-RU');
  }

  /**
   * Вычисление total pages для pagination
   */
  get totalPages(): number {
    return Math.ceil(this.totalCount / this.pageSize);
  }

  /**
   * Получение массива страниц для отображения в pagination
   */
  getPageNumbers(): number[] {
    const pages: number[] = [];
    const maxPagesToShow = 5;

    let startPage = Math.max(1, this.currentPage - Math.floor(maxPagesToShow / 2));
    let endPage = Math.min(this.totalPages, startPage + maxPagesToShow - 1);

    // Adjust startPage if endPage is at limit
    if (endPage - startPage < maxPagesToShow - 1) {
      startPage = Math.max(1, endPage - maxPagesToShow + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
      pages.push(i);
    }

    return pages;
  }
}
