/**
 * ArtStore Admin UI - Dashboard Component
 * Главная страница админ панели после успешного входа
 */
import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-dashboard',
  imports: [CommonModule],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
  standalone: true,
})
export class DashboardComponent {}
