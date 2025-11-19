/**
 * ArtStore Admin UI - Admin Users Component
 * Управление пользователями админ панели
 */
import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AdminUsersService, AdminUser, AdminRole, AdminUserListResponse } from '../../services/admin-users';

@Component({
  selector: 'app-admin-users',
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-users.html',
  styleUrl: './admin-users.scss',
  standalone: true,
})
export class AdminUsersComponent implements OnInit {
  private readonly adminUsersService = inject(AdminUsersService);

  // Data
  adminUsers: AdminUser[] = [];
  total = 0;
  page = 1;
  pageSize = 10;
  totalPages = 0;

  // Filters
  searchQuery = '';
  roleFilter: AdminRole | '' = '';
  enabledFilter: boolean | '' = '';

  // UI State
  loading = false;
  error: string | null = null;

  // Modals
  showCreateModal = false;
  showEditModal = false;
  showDeleteModal = false;
  showPasswordModal = false;
  selectedUser: AdminUser | null = null;

  // Forms
  createForm = {
    username: '',
    email: '',
    password: '',
    role: AdminRole.ADMIN as AdminRole,
    enabled: true
  };

  editForm = {
    email: '',
    role: AdminRole.ADMIN as AdminRole,
    enabled: true
  };

  passwordForm = {
    newPassword: ''
  };

  // Enums for template
  readonly AdminRole = AdminRole;
  readonly Math = Math;
  readonly roles = [
    { value: AdminRole.SUPER_ADMIN, label: 'Super Admin' },
    { value: AdminRole.ADMIN, label: 'Admin' },
    { value: AdminRole.READONLY, label: 'Read Only' }
  ];

  ngOnInit(): void {
    this.loadAdminUsers();
  }

  /**
   * Загрузить список администраторов
   */
  loadAdminUsers(): void {
    this.loading = true;
    this.error = null;

    this.adminUsersService.getAdminUsers(
      this.page,
      this.pageSize,
      this.roleFilter || undefined,
      this.enabledFilter !== '' ? this.enabledFilter : undefined,
      this.searchQuery || undefined
    ).subscribe({
      next: (response: AdminUserListResponse) => {
        this.adminUsers = response.items;
        this.total = response.total;
        this.totalPages = response.total_pages;
        this.loading = false;
      },
      error: (err) => {
        this.error = 'Ошибка загрузки администраторов: ' + (err.error?.detail || err.message);
        this.loading = false;
      }
    });
  }

  /**
   * Применить фильтры
   */
  applyFilters(): void {
    this.page = 1;
    this.loadAdminUsers();
  }

  /**
   * Сбросить фильтры
   */
  resetFilters(): void {
    this.searchQuery = '';
    this.roleFilter = '';
    this.enabledFilter = '';
    this.page = 1;
    this.loadAdminUsers();
  }

  /**
   * Перейти на страницу
   */
  goToPage(page: number): void {
    if (page >= 1 && page <= this.totalPages) {
      this.page = page;
      this.loadAdminUsers();
    }
  }

  /**
   * Открыть модал создания
   */
  openCreateModal(): void {
    this.createForm = {
      username: '',
      email: '',
      password: '',
      role: AdminRole.ADMIN,
      enabled: true
    };
    this.showCreateModal = true;
  }

  /**
   * Создать администратора
   */
  createAdminUser(): void {
    this.loading = true;
    this.error = null;

    this.adminUsersService.createAdminUser(this.createForm).subscribe({
      next: () => {
        this.showCreateModal = false;
        this.loadAdminUsers();
      },
      error: (err) => {
        this.error = 'Ошибка создания администратора: ' + (err.error?.detail || err.message);
        this.loading = false;
      }
    });
  }

  /**
   * Открыть модал редактирования
   */
  openEditModal(user: AdminUser): void {
    this.selectedUser = user;
    this.editForm = {
      email: user.email,
      role: user.role,
      enabled: user.enabled
    };
    this.showEditModal = true;
  }

  /**
   * Обновить администратора
   */
  updateAdminUser(): void {
    if (!this.selectedUser) return;

    this.loading = true;
    this.error = null;

    this.adminUsersService.updateAdminUser(this.selectedUser.id, this.editForm).subscribe({
      next: () => {
        this.showEditModal = false;
        this.selectedUser = null;
        this.loadAdminUsers();
      },
      error: (err) => {
        this.error = 'Ошибка обновления администратора: ' + (err.error?.detail || err.message);
        this.loading = false;
      }
    });
  }

  /**
   * Открыть модал удаления
   */
  openDeleteModal(user: AdminUser): void {
    this.selectedUser = user;
    this.showDeleteModal = true;
  }

  /**
   * Удалить администратора
   */
  deleteAdminUser(): void {
    if (!this.selectedUser) return;

    this.loading = true;
    this.error = null;

    this.adminUsersService.deleteAdminUser(this.selectedUser.id).subscribe({
      next: () => {
        this.showDeleteModal = false;
        this.selectedUser = null;
        this.loadAdminUsers();
      },
      error: (err) => {
        this.error = 'Ошибка удаления администратора: ' + (err.error?.detail || err.message);
        this.loading = false;
      }
    });
  }

  /**
   * Открыть модал сброса пароля
   */
  openPasswordModal(user: AdminUser): void {
    this.selectedUser = user;
    this.passwordForm = {
      newPassword: ''
    };
    this.showPasswordModal = true;
  }

  /**
   * Сбросить пароль
   */
  resetPassword(): void {
    if (!this.selectedUser) return;

    this.loading = true;
    this.error = null;

    this.adminUsersService.resetPassword(this.selectedUser.id, { new_password: this.passwordForm.newPassword }).subscribe({
      next: () => {
        this.showPasswordModal = false;
        this.selectedUser = null;
        this.loading = false;
        alert('Пароль успешно сброшен');
      },
      error: (err) => {
        this.error = 'Ошибка сброса пароля: ' + (err.error?.detail || err.message);
        this.loading = false;
      }
    });
  }

  /**
   * Закрыть все модалы
   */
  closeModals(): void {
    this.showCreateModal = false;
    this.showEditModal = false;
    this.showDeleteModal = false;
    this.showPasswordModal = false;
    this.selectedUser = null;
  }

  /**
   * Получить бейдж для роли
   */
  getRoleBadgeClass(role: AdminRole): string {
    switch (role) {
      case AdminRole.SUPER_ADMIN:
        return 'badge bg-danger';
      case AdminRole.ADMIN:
        return 'badge bg-primary';
      case AdminRole.READONLY:
        return 'badge bg-secondary';
      default:
        return 'badge bg-secondary';
    }
  }

  /**
   * Получить название роли
   */
  getRoleLabel(role: AdminRole): string {
    const found = this.roles.find(r => r.value === role);
    return found?.label || role;
  }
}
