/**
 * ArtStore Admin UI - Main Layout Component
 * Главный layout приложения, объединяющий Navbar, Sidebar, Footer и контент
 */
import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet } from '@angular/router';

import { Navbar } from '../navbar/navbar';
import { Sidebar } from '../sidebar/sidebar';
import { Footer } from '../footer/footer';

@Component({
  selector: 'app-main-layout',
  imports: [CommonModule, RouterOutlet, Navbar, Sidebar, Footer],
  templateUrl: './main-layout.html',
  styleUrl: './main-layout.scss',
  standalone: true,
})
export class MainLayout {}
