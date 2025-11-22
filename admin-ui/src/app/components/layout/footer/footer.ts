/**
 * ArtStore Admin UI - Footer Component
 * Нижний футер страницы с информацией о системе
 */
import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-footer',
  imports: [CommonModule],
  templateUrl: './footer.html',
  styleUrl: './footer.scss',
  standalone: true,
})
export class Footer {
  /** Текущий год для copyright */
  currentYear: number = new Date().getFullYear();

  /** Версия приложения */
  appVersion: string = '1.0.0';
}
