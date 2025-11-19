/**
 * Storage Elements Service
 *
 * Сервис для взаимодействия с API управления Storage Elements.
 * Предоставляет методы для:
 * - Получения списка Storage Elements с фильтрацией и пагинацией
 * - Получения детальной информации о Storage Element
 * - Получения сводной статистики
 *
 * Sprint 18 Phase 2: Read-only endpoints (CRUD в Sprint 19)
 */

import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

/**
 * Режимы работы Storage Element
 */
export enum StorageMode {
  EDIT = 'edit',  // Полные CRUD операции
  RW = 'rw',      // Чтение-запись, без удаления
  RO = 'ro',      // Только чтение
  AR = 'ar'       // Архивный режим
}

/**
 * Статусы Storage Element
 */
export enum StorageStatus {
  ONLINE = 'online',
  OFFLINE = 'offline',
  DEGRADED = 'degraded',
  MAINTENANCE = 'maintenance'
}

/**
 * Типы хранилища
 */
export enum StorageType {
  LOCAL = 'local',
  S3 = 's3'
}

/**
 * Storage Element интерфейс
 */
export interface StorageElement {
  id: number;
  name: string;
  description: string | null;
  mode: StorageMode;
  storage_type: StorageType;
  base_path: string;
  api_url: string;
  status: StorageStatus;
  capacity_bytes: number | null;
  used_bytes: number;
  file_count: number;
  retention_days: number | null;
  last_health_check: string | null;
  is_replicated: boolean;
  replica_count: number;
  created_at: string;
  updated_at: string;

  // Computed fields
  capacity_gb: number | null;
  used_gb: number;
  usage_percent: number | null;
  is_available: boolean;
  is_writable: boolean;
}

/**
 * Response для списка Storage Elements
 */
export interface StorageElementListResponse {
  total: number;
  items: StorageElement[];
  skip: number;
  limit: number;
}

/**
 * Summary статистика по Storage Elements
 */
export interface StorageElementsSummary {
  total_count: number;
  by_status: Record<StorageStatus, number>;
  by_mode: Record<StorageMode, number>;
  by_type: Record<StorageType, number>;
  total_capacity_gb: number;
  total_used_gb: number;
  total_files: number;
  average_usage_percent: number;
}

@Injectable({
  providedIn: 'root'
})
export class StorageElementsService {
  private apiUrl = `${environment.apiUrl}/storage-elements`;

  constructor(private http: HttpClient) {}

  /**
   * Получение списка Storage Elements с фильтрацией и пагинацией
   */
  getStorageElements(
    skip: number = 0,
    limit: number = 100,
    mode?: StorageMode,
    status?: StorageStatus,
    storageType?: StorageType,
    search?: string
  ): Observable<StorageElementListResponse> {
    let params = new HttpParams()
      .set('skip', skip.toString())
      .set('limit', limit.toString());

    if (mode) {
      params = params.set('mode', mode);
    }
    if (status) {
      params = params.set('status', status);
    }
    if (storageType) {
      params = params.set('storage_type', storageType);
    }
    if (search) {
      params = params.set('search', search);
    }

    return this.http.get<StorageElementListResponse>(this.apiUrl, { params });
  }

  /**
   * Получение Storage Element по ID
   */
  getStorageElementById(id: number): Observable<StorageElement> {
    return this.http.get<StorageElement>(`${this.apiUrl}/${id}`);
  }

  /**
   * Получение сводной статистики по Storage Elements
   */
  getStorageElementsSummary(): Observable<StorageElementsSummary> {
    return this.http.get<StorageElementsSummary>(`${this.apiUrl}/stats/summary`);
  }

  /**
   * Создание нового Storage Element
   */
  createStorageElement(data: any): Observable<StorageElement> {
    return this.http.post<StorageElement>(this.apiUrl, data);
  }

  /**
   * Обновление Storage Element
   */
  updateStorageElement(id: number, data: any): Observable<StorageElement> {
    return this.http.put<StorageElement>(`${this.apiUrl}/${id}`, data);
  }

  /**
   * Удаление Storage Element
   */
  deleteStorageElement(id: number): Observable<void> {
    return this.http.delete<void>(`${this.apiUrl}/${id}`);
  }

  /**
   * Вспомогательная функция: Форматирование размера
   */
  formatSize(gb: number | null): string {
    if (gb === null) return 'N/A';
    if (gb < 0.01) return '<0.01 GB';
    if (gb < 1) return `${gb.toFixed(2)} GB`;
    if (gb < 1024) return `${gb.toFixed(1)} GB`;
    return `${(gb / 1024).toFixed(2)} TB`;
  }

  /**
   * Вспомогательная функция: Форматирование процента использования
   */
  formatUsagePercent(percent: number | null): string {
    if (percent === null) return 'N/A';
    return `${percent.toFixed(1)}%`;
  }

  /**
   * Вспомогательная функция: Получение badge класса для статуса
   */
  getStatusBadgeClass(status: StorageStatus): string {
    switch (status) {
      case StorageStatus.ONLINE:
        return 'badge bg-success';
      case StorageStatus.OFFLINE:
        return 'badge bg-danger';
      case StorageStatus.DEGRADED:
        return 'badge bg-warning';
      case StorageStatus.MAINTENANCE:
        return 'badge bg-secondary';
      default:
        return 'badge bg-secondary';
    }
  }

  /**
   * Вспомогательная функция: Получение badge класса для режима
   */
  getModeBadgeClass(mode: StorageMode): string {
    switch (mode) {
      case StorageMode.EDIT:
        return 'badge bg-primary';
      case StorageMode.RW:
        return 'badge bg-info';
      case StorageMode.RO:
        return 'badge bg-warning text-dark';
      case StorageMode.AR:
        return 'badge bg-secondary';
      default:
        return 'badge bg-secondary';
    }
  }

  /**
   * Вспомогательная функция: Получение описания режима
   */
  getModeDescription(mode: StorageMode): string {
    switch (mode) {
      case StorageMode.EDIT:
        return 'Edit (Full CRUD)';
      case StorageMode.RW:
        return 'Read-Write';
      case StorageMode.RO:
        return 'Read-Only';
      case StorageMode.AR:
        return 'Archive';
      default:
        return mode;
    }
  }

  /**
   * Вспомогательная функция: Получение описания статуса
   */
  getStatusDescription(status: StorageStatus): string {
    switch (status) {
      case StorageStatus.ONLINE:
        return 'Online';
      case StorageStatus.OFFLINE:
        return 'Offline';
      case StorageStatus.DEGRADED:
        return 'Degraded';
      case StorageStatus.MAINTENANCE:
        return 'Maintenance';
      default:
        return status;
    }
  }
}
