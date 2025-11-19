/**
 * ArtStore Admin UI - Service Accounts Service
 * Сервис для взаимодействия с Service Accounts API
 */
import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

/**
 * Service Account роли
 */
export enum ServiceAccountRole {
  ADMIN = 'admin',
  USER = 'user',
  AUDITOR = 'auditor',
  READONLY = 'readonly'
}

/**
 * Service Account статусы
 */
export enum ServiceAccountStatus {
  ACTIVE = 'active',
  SUSPENDED = 'suspended',
  EXPIRED = 'expired',
  DELETED = 'deleted'
}

/**
 * Service Account интерфейс
 */
export interface ServiceAccount {
  id: string;
  name: string;
  description: string | null;
  client_id: string;
  role: ServiceAccountRole;
  status: ServiceAccountStatus;
  rate_limit: number;
  is_system: boolean;
  secret_expires_at: string;
  days_until_expiry: number;
  requires_rotation_warning: boolean;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Service Account List Response
 */
export interface ServiceAccountListResponse {
  total: number;
  items: ServiceAccount[];
  skip: number;
  limit: number;
}

/**
 * Service Account Create Request
 */
export interface ServiceAccountCreateRequest {
  name: string;
  description?: string;
  role: ServiceAccountRole;
  rate_limit: number;
  environment: string;
  is_system: boolean;
}

/**
 * Service Account Create Response (includes client_secret)
 */
export interface ServiceAccountCreateResponse {
  id: string;
  name: string;
  client_id: string;
  client_secret: string;  // ONLY returned on create
  role: ServiceAccountRole;
  status: ServiceAccountStatus;
  rate_limit: number;
  secret_expires_at: string;
  created_at: string;
}

/**
 * Service Account Update Request
 */
export interface ServiceAccountUpdateRequest {
  name?: string;
  description?: string;
  role?: ServiceAccountRole;
  rate_limit?: number;
  status?: ServiceAccountStatus;
}

/**
 * Service Account Rotate Secret Response (includes new_client_secret)
 */
export interface ServiceAccountRotateSecretResponse {
  id: string;
  name: string;
  client_id: string;
  new_client_secret: string;  // ONLY returned on rotation
  secret_expires_at: string;
  status: ServiceAccountStatus;
}

/**
 * Service Accounts Service
 * Управление Service Accounts через API
 */
@Injectable({
  providedIn: 'root'
})
export class ServiceAccountsService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = `${environment.apiUrl}/service-accounts`;

  /**
   * Получить список Service Accounts с фильтрацией и пагинацией
   */
  getServiceAccounts(
    skip: number = 0,
    limit: number = 100,
    role?: ServiceAccountRole,
    status?: ServiceAccountStatus,
    search?: string
  ): Observable<ServiceAccountListResponse> {
    let params = new HttpParams()
      .set('skip', skip.toString())
      .set('limit', limit.toString());

    if (role) {
      params = params.set('role', role);
    }
    if (status) {
      params = params.set('status', status);
    }
    if (search) {
      params = params.set('search', search);
    }

    return this.http.get<ServiceAccountListResponse>(this.apiUrl, { params });
  }

  /**
   * Получить Service Account по ID
   */
  getServiceAccount(id: string): Observable<ServiceAccount> {
    return this.http.get<ServiceAccount>(`${this.apiUrl}/${id}`);
  }

  /**
   * Создать новый Service Account
   */
  createServiceAccount(request: ServiceAccountCreateRequest): Observable<ServiceAccountCreateResponse> {
    return this.http.post<ServiceAccountCreateResponse>(this.apiUrl, request);
  }

  /**
   * Обновить Service Account
   */
  updateServiceAccount(id: string, request: ServiceAccountUpdateRequest): Observable<ServiceAccount> {
    return this.http.put<ServiceAccount>(`${this.apiUrl}/${id}`, request);
  }

  /**
   * Удалить Service Account
   */
  deleteServiceAccount(id: string): Observable<void> {
    return this.http.delete<void>(`${this.apiUrl}/${id}`);
  }

  /**
   * Ротация client_secret Service Account
   */
  rotateSecret(id: string): Observable<ServiceAccountRotateSecretResponse> {
    return this.http.post<ServiceAccountRotateSecretResponse>(`${this.apiUrl}/${id}/rotate-secret`, {});
  }
}
