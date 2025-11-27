/**
 * Storage Elements Service
 *
 * Сервис для взаимодействия с API управления Storage Elements.
 * Предоставляет методы для:
 * - Auto-discovery Storage Elements по URL
 * - Синхронизация данных Storage Elements
 * - Получения списка Storage Elements с фильтрацией и пагинацией
 * - Получения детальной информации о Storage Element
 * - Получения сводной статистики
 * - CRUD операции
 *
 * Sprint 19 Phase 2: Auto-discovery и Sync implementation
 *
 * ВАЖНО: Mode Storage Element определяется ТОЛЬКО его конфигурацией при запуске.
 *        Изменить mode можно только через изменение конфигурации и перезапуск storage element.
 *        Admin Module НЕ МОЖЕТ изменять mode через API.
 */

import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

/**
 * Режимы работы Storage Element
 * ВАЖНО: Mode определяется ТОЛЬКО конфигурацией storage element при запуске
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

/**
 * Request для discovery Storage Element
 */
export interface StorageElementDiscoverRequest {
  api_url: string;
}

/**
 * Response от discovery endpoint
 * Содержит информацию о storage element до его регистрации
 */
export interface StorageElementDiscoverResponse {
  // Данные от storage element
  name: string;
  display_name: string;
  version: string;
  mode: string;
  storage_type: string;
  base_path: string;
  capacity_bytes: number;
  used_bytes: number;
  file_count: number;
  status: string;
  api_url: string;

  // Computed fields
  capacity_gb: number;
  used_gb: number;
  usage_percent: number | null;

  // Флаги для UI
  already_registered: boolean;
  existing_id: number | null;
}

/**
 * Request для создания Storage Element с auto-discovery
 * ВАЖНО: mode, storage_type, base_path, capacity_bytes получаются автоматически
 */
export interface StorageElementCreateRequest {
  api_url: string;                      // ОБЯЗАТЕЛЬНО - URL для auto-discovery
  name?: string;                        // Опционально - если не указано, из discovery
  description?: string;                 // Опционально
  api_key?: string;                     // Опционально
  retention_days?: number;              // Опционально
  is_replicated?: boolean;              // Default: false
  replica_count?: number;               // Default: 0
}

/**
 * Request для обновления Storage Element
 * ВАЖНО: mode НЕ может быть изменен через API
 */
export interface StorageElementUpdateRequest {
  name?: string;
  description?: string;
  api_url?: string;
  api_key?: string;
  status?: StorageStatus;
  retention_days?: number;
  replica_count?: number;
  // mode УДАЛЕН - изменяется только через конфигурацию storage element
}

/**
 * Response для sync операции
 */
export interface StorageElementSyncResponse {
  storage_element_id: number;
  name: string;
  success: boolean;
  changes: string[];
  error_message: string | null;
  synced_at: string | null;
}

/**
 * Response для массовой синхронизации
 */
export interface StorageElementSyncAllResponse {
  total: number;
  synced: number;
  failed: number;
  results: StorageElementSyncResponse[];
}

@Injectable({
  providedIn: 'root'
})
export class StorageElementsService {
  private apiUrl = `${environment.apiUrl}/storage-elements`;

  constructor(private http: HttpClient) {}

  // =============================================================================
  // Discovery и Sync методы
  // =============================================================================

  /**
   * Discovery Storage Element по URL
   *
   * Выполняет запрос к storage element для получения информации
   * без регистрации в системе. Используется для preview перед добавлением.
   *
   * @param apiUrl URL API storage element
   * @returns Observable с информацией о storage element
   */
  discoverStorageElement(apiUrl: string): Observable<StorageElementDiscoverResponse> {
    return this.http.post<StorageElementDiscoverResponse>(
      `${this.apiUrl}/discover`,
      { api_url: apiUrl }
    );
  }

  /**
   * Синхронизация одного Storage Element
   *
   * Выполняет запрос к storage element и обновляет данные в БД.
   * Синхронизируются: mode, capacity_bytes, used_bytes, file_count, status.
   *
   * @param id ID storage element
   * @returns Observable с результатом синхронизации
   */
  syncStorageElement(id: number): Observable<StorageElementSyncResponse> {
    return this.http.post<StorageElementSyncResponse>(
      `${this.apiUrl}/sync/${id}`,
      {}
    );
  }

  /**
   * Массовая синхронизация всех Storage Elements
   *
   * @param onlyOnline Синхронизировать только ONLINE (default: true)
   * @returns Observable со сводкой синхронизации
   */
  syncAllStorageElements(onlyOnline: boolean = true): Observable<StorageElementSyncAllResponse> {
    let params = new HttpParams().set('only_online', onlyOnline.toString());
    return this.http.post<StorageElementSyncAllResponse>(
      `${this.apiUrl}/sync-all`,
      {},
      { params }
    );
  }

  // =============================================================================
  // CRUD методы
  // =============================================================================

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
   * Создание нового Storage Element с auto-discovery
   *
   * При создании выполняется автоматический discovery storage element
   * для получения: mode, storage_type, base_path, capacity_bytes.
   *
   * @param data Данные для создания (обязательно api_url)
   * @returns Observable созданного Storage Element
   */
  createStorageElement(data: StorageElementCreateRequest): Observable<StorageElement> {
    return this.http.post<StorageElement>(this.apiUrl, data);
  }

  /**
   * Обновление Storage Element
   *
   * ВАЖНО: mode НЕ может быть изменен через API.
   * Для изменения mode необходимо изменить конфигурацию
   * storage element и перезапустить его.
   *
   * @param id ID storage element
   * @param data Данные для обновления (без mode)
   * @returns Observable обновленного Storage Element
   */
  updateStorageElement(id: number, data: StorageElementUpdateRequest): Observable<StorageElement> {
    return this.http.put<StorageElement>(`${this.apiUrl}/${id}`, data);
  }

  /**
   * Удаление Storage Element
   */
  deleteStorageElement(id: number): Observable<void> {
    return this.http.delete<void>(`${this.apiUrl}/${id}`);
  }

  // =============================================================================
  // Вспомогательные функции
  // =============================================================================

  /**
   * Форматирование размера
   */
  formatSize(gb: number | null): string {
    if (gb === null) return 'N/A';
    if (gb < 0.01) return '<0.01 GB';
    if (gb < 1) return `${gb.toFixed(2)} GB`;
    if (gb < 1024) return `${gb.toFixed(1)} GB`;
    return `${(gb / 1024).toFixed(2)} TB`;
  }

  /**
   * Форматирование процента использования
   */
  formatUsagePercent(percent: number | null): string {
    if (percent === null) return 'N/A';
    return `${percent.toFixed(1)}%`;
  }

  /**
   * Получение badge класса для статуса
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
   * Получение badge класса для режима
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
   * Получение описания режима
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
   * Получение описания статуса
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

  /**
   * Получение описания типа хранилища
   */
  getStorageTypeDescription(storageType: StorageType): string {
    switch (storageType) {
      case StorageType.LOCAL:
        return 'Local Storage';
      case StorageType.S3:
        return 'S3 Compatible';
      default:
        return storageType;
    }
  }

  /**
   * Проверка - можно ли редактировать mode через UI
   * (Ответ всегда false - mode только через конфигурацию)
   */
  canEditMode(): boolean {
    return false;
  }

  /**
   * Получение подсказки почему mode нельзя изменить
   */
  getModeEditHint(): string {
    return 'Mode определяется конфигурацией storage element при запуске. ' +
           'Для изменения mode необходимо изменить конфигурацию и перезапустить storage element.';
  }
}
