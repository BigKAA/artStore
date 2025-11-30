/**
 * ArtStore Admin UI - Admin Users Component
 * Управление пользователями админ панели
 */
import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AdminUsersService, AdminUser, AdminRole, AdminUserListResponse } from '../../services/admin-users';
import { NotificationService } from '../../services/notification.service';

@Component({
  selector: 'app-admin-users',
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-users.html',
  styleUrl: './admin-users.scss',
  standalone: true,
})
export class AdminUsersComponent implements OnInit {
  private readonly adminUsersService = inject(AdminUsersService);
  private readonly notification = inject(NotificationService);

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

  // Password validation state
  passwordValidation = {
    hasMinLength: false,
    hasUppercase: false,
    hasLowercase: false,
    hasDigit: false,
    isValid: false
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
        this.notification.error('Ошибка загрузки администраторов: ' + (err.error?.detail || err.message));
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
    // Reset password validation
    this.passwordValidation = {
      hasMinLength: false,
      hasUppercase: false,
      hasLowercase: false,
      hasDigit: false,
      isValid: false
    };
    this.showCreateModal = true;
  }

  /**
   * Создать администратора
   */
  createAdminUser(): void {
    this.loading = true;

    this.adminUsersService.createAdminUser(this.createForm).subscribe({
      next: () => {
        this.showCreateModal = false;
        this.notification.success('Администратор успешно создан');
        this.loadAdminUsers();
      },
      error: (err) => {
        // Handle Pydantic validation errors (422)
        if (err.status === 422 && Array.isArray(err.error?.detail)) {
          const validationErrors = err.error.detail.map((e: any) => e.msg).join('; ');
          this.notification.error('Ошибка валидации: ' + validationErrors);
        } else if (typeof err.error?.detail === 'string') {
          this.notification.error('Ошибка создания администратора: ' + err.error.detail);
        } else {
          this.notification.error('Ошибка создания администратора: ' + (err.message || 'Неизвестная ошибка'));
        }
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

    this.adminUsersService.updateAdminUser(this.selectedUser.id, this.editForm).subscribe({
      next: () => {
        this.showEditModal = false;
        this.selectedUser = null;
        this.notification.success('Администратор успешно обновлён');
        this.loadAdminUsers();
      },
      error: (err) => {
        this.notification.error('Ошибка обновления администратора: ' + (err.error?.detail || err.message));
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

    this.adminUsersService.deleteAdminUser(this.selectedUser.id).subscribe({
      next: () => {
        this.showDeleteModal = false;
        this.selectedUser = null;
        this.notification.success('Администратор успешно удалён');
        this.loadAdminUsers();
      },
      error: (err) => {
        this.notification.error('Ошибка удаления администратора: ' + (err.error?.detail || err.message));
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
    // Reset password validation
    this.passwordValidation = {
      hasMinLength: false,
      hasUppercase: false,
      hasLowercase: false,
      hasDigit: false,
      isValid: false
    };
    this.showPasswordModal = true;
  }

  /**
   * Сбросить пароль
   */
  resetPassword(): void {
    if (!this.selectedUser) return;

    this.loading = true;

    this.adminUsersService.resetPassword(this.selectedUser.id, { new_password: this.passwordForm.newPassword }).subscribe({
      next: () => {
        this.showPasswordModal = false;
        this.selectedUser = null;
        this.loading = false;
        this.notification.success('Пароль успешно сброшен');
      },
      error: (err) => {
        this.notification.error('Ошибка сброса пароля: ' + (err.error?.detail || err.message));
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
   * Валидация пароля в реальном времени
   */
  validatePassword(password: string): void {
    this.passwordValidation.hasMinLength = password.length >= 8;
    this.passwordValidation.hasUppercase = /[A-Z]/.test(password);
    this.passwordValidation.hasLowercase = /[a-z]/.test(password);
    this.passwordValidation.hasDigit = /\d/.test(password);
    this.passwordValidation.isValid =
      this.passwordValidation.hasMinLength &&
      this.passwordValidation.hasUppercase &&
      this.passwordValidation.hasLowercase &&
      this.passwordValidation.hasDigit;
  }

  /**
   * Обработчик изменения пароля в форме создания
   */
  onCreatePasswordChange(): void {
    this.validatePassword(this.createForm.password);
  }

  /**
   * Обработчик изменения пароля в форме сброса
   */
  onResetPasswordChange(): void {
    this.validatePassword(this.passwordForm.newPassword);
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
