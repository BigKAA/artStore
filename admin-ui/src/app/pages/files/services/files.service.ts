/**
 * ArtStore Admin UI - Files Service
 * Сервис для интеграции с Ingester и Query Module API
 */
import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpEvent } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import {
  FileMetadata,
  SearchRequest,
  SearchResponse,
  UploadRequest,
  UploadResponse
} from '../models';

@Injectable({
  providedIn: 'root'
})
export class FilesService {
  private queryApiUrl = `${environment.queryModuleUrl}/api`;
  private ingesterApiUrl = `${environment.ingesterModuleUrl}`;

  constructor(private http: HttpClient) {}

  /**
   * Поиск файлов с фильтрацией (Query Module)
   *
   * @param request Параметры поиска
   * @returns Observable с результатами поиска
   */
  searchFiles(request: SearchRequest): Observable<SearchResponse> {
    return this.http.post<SearchResponse>(
      `${this.queryApiUrl}/search`,
      request
    );
  }

  /**
   * Получение метаданных файла по ID (Query Module)
   *
   * @param fileId UUID файла
   * @returns Observable с метаданными файла
   */
  getFileMetadata(fileId: string): Observable<FileMetadata> {
    return this.http.get<FileMetadata>(
      `${this.queryApiUrl}/search/${fileId}`
    );
  }

  /**
   * Загрузка файла (Ingester Module) с отслеживанием прогресса
   *
   * @param request Запрос на загрузку файла
   * @returns Observable с HTTP events (включая upload progress)
   */
  uploadFile(request: UploadRequest): Observable<HttpEvent<UploadResponse>> {
    const formData = new FormData();
    formData.append('file', request.file);

    if (request.description) {
      formData.append('description', request.description);
    }

    formData.append('storage_mode', request.storage_mode);
    formData.append('compress', request.compress.toString());
    formData.append('compression_algorithm', request.compression_algorithm);

    return this.http.post<UploadResponse>(
      `${this.ingesterApiUrl}/api/v1/files/upload`,
      formData,
      {
        reportProgress: true,
        observe: 'events'
      }
    );
  }

  /**
   * Скачивание файла (Query Module) - streaming download
   *
   * @param fileId UUID файла
   * @returns Observable с Blob данными файла
   */
  downloadFile(fileId: string): Observable<Blob> {
    return this.http.get(
      `${this.queryApiUrl}/download/${fileId}`,
      {
        responseType: 'blob',
        headers: new HttpHeaders({
          'Accept': 'application/octet-stream'
        })
      }
    );
  }

  /**
   * Trigger browser download для полученного Blob
   * Создает временную ссылку и программно кликает на нее
   *
   * @param blob Данные файла
   * @param filename Имя файла для сохранения
   */
  triggerBrowserDownload(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;

    // Добавляем ссылку в DOM, кликаем, удаляем
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    // Освобождаем URL object
    window.URL.revokeObjectURL(url);
  }
}
