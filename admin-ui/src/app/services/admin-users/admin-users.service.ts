/**
 * ArtStore Admin UI - Admin Users Service
 * Сервис для взаимодействия с Admin Users API
 */
import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

/**
 * Admin User роли
 */
export enum AdminRole {
  SUPER_ADMIN = 'super_admin',
  ADMIN = 'admin',
  READONLY = 'readonly'
}

/**
 * Admin User интерфейс
 */
export interface AdminUser {
  id: string;
  username: string;
  email: string;
  role: AdminRole;
  enabled: boolean;
  is_system: boolean;
  last_login_at: string | null;
  password_changed_at: string | null;
  locked_until: string | null;
  login_attempts: number;
  created_at: string;
  updated_at: string;
}

/**
 * Admin User List Response
 */
export interface AdminUserListResponse {
  items: AdminUser[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/**
 * Admin User Create Request
 */
export interface AdminUserCreateRequest {
  username: string;
  email: string;
  password: string;
  role: AdminRole;
  enabled: boolean;
}

/**
 * Admin User Update Request
 */
export interface AdminUserUpdateRequest {
  email?: string;
  role?: AdminRole;
  enabled?: boolean;
}

/**
 * Admin User Password Reset Request
 */
export interface AdminUserPasswordResetRequest {
  new_password: string;
}

/**
 * Admin User Delete Response
 */
export interface AdminUserDeleteResponse {
  message: string;
  deleted_id: string;
  deleted_username: string;
}

/**
 * Admin User Password Reset Response
 */
export interface AdminUserPasswordResetResponse {
  message: string;
  admin_id: string;
  username: string;
}

/**
 * Admin Users Service
 * Управление администраторами через API
 */
@Injectable({
  providedIn: 'root'
})
export class AdminUsersService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = `${environment.apiUrl}/admin-users`;

  /**
   * Получить список администраторов с фильтрацией и пагинацией
   */
  getAdminUsers(
    page: number = 1,
    pageSize: number = 10,
    role?: AdminRole,
    enabled?: boolean,
    search?: string
  ): Observable<AdminUserListResponse> {
    let params = new HttpParams()
      .set('page', page.toString())
      .set('page_size', pageSize.toString());

    if (role) {
      params = params.set('role', role);
    }
    if (enabled !== undefined) {
      params = params.set('enabled', enabled.toString());
    }
    if (search) {
      params = params.set('search', search);
    }

    return this.http.get<AdminUserListResponse>(this.apiUrl, { params });
  }

  /**
   * Получить администратора по ID
   */
  getAdminUser(id: string): Observable<AdminUser> {
    return this.http.get<AdminUser>(`${this.apiUrl}/${id}`);
  }

  /**
   * Создать нового администратора
   */
  createAdminUser(request: AdminUserCreateRequest): Observable<AdminUser> {
    return this.http.post<AdminUser>(this.apiUrl, request);
  }

  /**
   * Обновить администратора
   */
  updateAdminUser(id: string, request: AdminUserUpdateRequest): Observable<AdminUser> {
    return this.http.put<AdminUser>(`${this.apiUrl}/${id}`, request);
  }

  /**
   * Удалить администратора
   */
  deleteAdminUser(id: string): Observable<AdminUserDeleteResponse> {
    return this.http.delete<AdminUserDeleteResponse>(`${this.apiUrl}/${id}`);
  }

  /**
   * Сбросить пароль администратора
   */
  resetPassword(id: string, request: AdminUserPasswordResetRequest): Observable<AdminUserPasswordResetResponse> {
    return this.http.post<AdminUserPasswordResetResponse>(`${this.apiUrl}/${id}/reset-password`, request);
  }
}
