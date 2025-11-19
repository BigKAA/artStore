/**
 * ArtStore Admin UI - Service Accounts Component
 * Управление Service Accounts с CRUD операциями
 */
import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import {
  ServiceAccountsService,
  ServiceAccount,
  ServiceAccountRole,
  ServiceAccountStatus,
  ServiceAccountCreateRequest,
  ServiceAccountUpdateRequest,
  ServiceAccountCreateResponse,
  ServiceAccountRotateSecretResponse
} from '../../services/service-accounts/service-accounts.service';

/**
 * Service Accounts Management Component
 *
 * Features:
 * - Service Accounts list с пагинацией
 * - Фильтрация по роли и статусу
 * - Поиск по имени или client_id
 * - Создание Service Account (с отображением client_secret)
 * - Редактирование параметров
 * - Удаление (с защитой системных аккаунтов)
 * - Ротация client_secret (с отображением нового секрета)
 * - Предупреждения о необходимости ротации (expires < 7 дней)
 */
@Component({
  selector: 'app-service-accounts',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './service-accounts.html',
  styleUrls: ['./service-accounts.scss']
})
export class ServiceAccountsComponent implements OnInit {
  private readonly serviceAccountsService = inject(ServiceAccountsService);

  // Data properties
  serviceAccounts: ServiceAccount[] = [];
  total = 0;
  skip = 0;
  limit = 50;

  // Filter properties
  searchQuery = '';
  roleFilter: ServiceAccountRole | '' = '';
  statusFilter: ServiceAccountStatus | '' = '';

  // Loading state
  isLoading = false;

  // Modal state
  showCreateModal = false;
  showEditModal = false;
  showDeleteModal = false;
  showRotateModal = false;
  showCredentialsModal = false;
  selectedAccount: ServiceAccount | null = null;

  // Create form
  createForm = {
    name: '',
    description: '',
    role: ServiceAccountRole.USER,
    rate_limit: 100,
    environment: 'prod' as 'prod' | 'staging' | 'dev',
    is_system: false
  };

  // Edit form
  editForm = {
    name: '',
    description: '',
    role: ServiceAccountRole.USER,
    rate_limit: 100,
    status: ServiceAccountStatus.ACTIVE
  };

  // Credentials display (client_secret shown ONLY on create/rotate)
  createdCredentials: ServiceAccountCreateResponse | null = null;
  rotatedCredentials: ServiceAccountRotateSecretResponse | null = null;

  // Helper for template
  readonly ServiceAccountRole = ServiceAccountRole;
  readonly ServiceAccountStatus = ServiceAccountStatus;
  readonly Math = Math;

  ngOnInit(): void {
    this.loadServiceAccounts();
  }

  /**
   * Загрузка списка Service Accounts
   */
  loadServiceAccounts(): void {
    this.isLoading = true;

    this.serviceAccountsService.getServiceAccounts(
      this.skip,
      this.limit,
      this.roleFilter || undefined,
      this.statusFilter || undefined,
      this.searchQuery || undefined
    ).subscribe({
      next: (response) => {
        this.serviceAccounts = response.items;
        this.total = response.total;
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Failed to load Service Accounts:', error);
        this.isLoading = false;
      }
    });
  }

  /**
   * Применение фильтров
   */
  applyFilters(): void {
    this.skip = 0;  // Reset pagination
    this.loadServiceAccounts();
  }

  /**
   * Сброс фильтров
   */
  resetFilters(): void {
    this.searchQuery = '';
    this.roleFilter = '';
    this.statusFilter = '';
    this.skip = 0;
    this.loadServiceAccounts();
  }

  /**
   * Pagination - Previous page
   */
  previousPage(): void {
    if (this.skip > 0) {
      this.skip = Math.max(0, this.skip - this.limit);
      this.loadServiceAccounts();
    }
  }

  /**
   * Pagination - Next page
   */
  nextPage(): void {
    if (this.skip + this.limit < this.total) {
      this.skip += this.limit;
      this.loadServiceAccounts();
    }
  }

  /**
   * Открыть Create modal
   */
  openCreateModal(): void {
    this.createForm = {
      name: '',
      description: '',
      role: ServiceAccountRole.USER,
      rate_limit: 100,
      environment: 'prod',
      is_system: false
    };
    this.createdCredentials = null;
    this.showCreateModal = true;
  }

  /**
   * Создание Service Account
   */
  createServiceAccount(): void {
    const request: ServiceAccountCreateRequest = {
      name: this.createForm.name,
      description: this.createForm.description || undefined,
      role: this.createForm.role,
      rate_limit: this.createForm.rate_limit,
      environment: this.createForm.environment,
      is_system: this.createForm.is_system
    };

    this.serviceAccountsService.createServiceAccount(request).subscribe({
      next: (response) => {
        // Сохраняем credentials для отображения
        this.createdCredentials = response;
        // Переключаемся на credentials modal
        this.showCreateModal = false;
        this.showCredentialsModal = true;
        this.loadServiceAccounts();
      },
      error: (error) => {
        console.error('Failed to create Service Account:', error);
        alert(`Failed to create Service Account: ${error.error?.detail || 'Unknown error'}`);
      }
    });
  }

  /**
   * Открыть Edit modal
   */
  openEditModal(account: ServiceAccount): void {
    this.selectedAccount = account;
    this.editForm = {
      name: account.name,
      description: account.description || '',
      role: account.role,
      rate_limit: account.rate_limit,
      status: account.status
    };
    this.showEditModal = true;
  }

  /**
   * Обновление Service Account
   */
  updateServiceAccount(): void {
    if (!this.selectedAccount) return;

    const request: ServiceAccountUpdateRequest = {
      name: this.editForm.name !== this.selectedAccount.name ? this.editForm.name : undefined,
      description: this.editForm.description !== this.selectedAccount.description ? this.editForm.description : undefined,
      role: this.editForm.role !== this.selectedAccount.role ? this.editForm.role : undefined,
      rate_limit: this.editForm.rate_limit !== this.selectedAccount.rate_limit ? this.editForm.rate_limit : undefined,
      status: this.editForm.status !== this.selectedAccount.status ? this.editForm.status : undefined
    };

    this.serviceAccountsService.updateServiceAccount(this.selectedAccount.id, request).subscribe({
      next: () => {
        this.showEditModal = false;
        this.selectedAccount = null;
        this.loadServiceAccounts();
      },
      error: (error) => {
        console.error('Failed to update Service Account:', error);
        alert(`Failed to update Service Account: ${error.error?.detail || 'Unknown error'}`);
      }
    });
  }

  /**
   * Открыть Delete modal
   */
  openDeleteModal(account: ServiceAccount): void {
    this.selectedAccount = account;
    this.showDeleteModal = true;
  }

  /**
   * Удаление Service Account
   */
  deleteServiceAccount(): void {
    if (!this.selectedAccount) return;

    this.serviceAccountsService.deleteServiceAccount(this.selectedAccount.id).subscribe({
      next: () => {
        this.showDeleteModal = false;
        this.selectedAccount = null;
        this.loadServiceAccounts();
      },
      error: (error) => {
        console.error('Failed to delete Service Account:', error);
        alert(`Failed to delete Service Account: ${error.error?.detail || 'Unknown error'}`);
      }
    });
  }

  /**
   * Открыть Rotate Secret modal
   */
  openRotateModal(account: ServiceAccount): void {
    this.selectedAccount = account;
    this.rotatedCredentials = null;
    this.showRotateModal = true;
  }

  /**
   * Ротация client_secret
   */
  rotateSecret(): void {
    if (!this.selectedAccount) return;

    this.serviceAccountsService.rotateSecret(this.selectedAccount.id).subscribe({
      next: (response) => {
        // Сохраняем новые credentials для отображения
        this.rotatedCredentials = response;
        // Переключаемся на credentials modal
        this.showRotateModal = false;
        this.showCredentialsModal = true;
        this.loadServiceAccounts();
      },
      error: (error) => {
        console.error('Failed to rotate secret:', error);
        alert(`Failed to rotate secret: ${error.error?.detail || 'Unknown error'}`);
      }
    });
  }

  /**
   * Закрыть Credentials modal
   */
  closeCredentialsModal(): void {
    this.showCredentialsModal = false;
    this.createdCredentials = null;
    this.rotatedCredentials = null;
    this.selectedAccount = null;
  }

  /**
   * Копирование client_secret в clipboard
   */
  copyToClipboard(text: string): void {
    navigator.clipboard.writeText(text).then(() => {
      alert('Copied to clipboard!');
    });
  }

  /**
   * Get role badge CSS class
   */
  getRoleBadgeClass(role: ServiceAccountRole): string {
    switch (role) {
      case ServiceAccountRole.ADMIN:
        return 'badge bg-danger';
      case ServiceAccountRole.USER:
        return 'badge bg-primary';
      case ServiceAccountRole.AUDITOR:
        return 'badge bg-info';
      case ServiceAccountRole.READONLY:
        return 'badge bg-secondary';
      default:
        return 'badge bg-secondary';
    }
  }

  /**
   * Get role label
   */
  getRoleLabel(role: ServiceAccountRole): string {
    switch (role) {
      case ServiceAccountRole.ADMIN:
        return 'Admin';
      case ServiceAccountRole.USER:
        return 'User';
      case ServiceAccountRole.AUDITOR:
        return 'Auditor';
      case ServiceAccountRole.READONLY:
        return 'Read Only';
      default:
        return role;
    }
  }

  /**
   * Get status badge CSS class
   */
  getStatusBadgeClass(status: ServiceAccountStatus): string {
    switch (status) {
      case ServiceAccountStatus.ACTIVE:
        return 'badge bg-success';
      case ServiceAccountStatus.SUSPENDED:
        return 'badge bg-warning';
      case ServiceAccountStatus.EXPIRED:
        return 'badge bg-danger';
      case ServiceAccountStatus.DELETED:
        return 'badge bg-dark';
      default:
        return 'badge bg-secondary';
    }
  }

  /**
   * Get status label
   */
  getStatusLabel(status: ServiceAccountStatus): string {
    switch (status) {
      case ServiceAccountStatus.ACTIVE:
        return 'Active';
      case ServiceAccountStatus.SUSPENDED:
        return 'Suspended';
      case ServiceAccountStatus.EXPIRED:
        return 'Expired';
      case ServiceAccountStatus.DELETED:
        return 'Deleted';
      default:
        return status;
    }
  }

  /**
   * Get expiry warning badge
   */
  getExpiryWarning(account: ServiceAccount): string | null {
    if (account.requires_rotation_warning && account.days_until_expiry <= 7) {
      return `Expires in ${account.days_until_expiry} days`;
    }
    return null;
  }
}
