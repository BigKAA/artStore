# План тестирования torage Element Selection Strategy

```yaml
Задача: Протестировать "Storage Element Selection Strategy" из @README.md
Целевой набор модулей:
- admin-module: 1шт. 
  DB_DATABASE: artstore_admin
- ingester-module: 1шт.
- query-module: 1шт. 
  DATABASE_DATABASE: artstore_query
- admin-ui: 1шт.
- storage-elements: 3шт. 
	- storage-element-name: se-01
	  APP_MODE: edit
	  STORAGE_MAX_SIZE_GB: 1
	  STORAGE_S3_BUCKET_NAME: artstore-files
	  STORAGE_S3_APP_FOLDER: se_01
	  DB_DATABASE: se_01
	  DB_TABLE_PREFIX: se
	  externalPort: 8010
	- storage-element-name: se-02
	  APP_MODE: edit
	  STORAGE_MAX_SIZE_GB: 1
	  STORAGE_S3_BUCKET_NAME: artstore-files
	  STORAGE_S3_APP_FOLDER: se_02
	  DB_DATABASE: se_02
	  DB_TABLE_PREFIX: se
	  externalPort: 8011
	- storage-element-name: se-03
	  APP_MODE: rw
	  STORAGE_MAX_SIZE_GB: 1
	  STORAGE_S3_BUCKET_NAME: artstore-files
	  STORAGE_S3_APP_FOLDER: se_03
	  DB_DATABASE: se_03
	  DB_TABLE_PREFIX: se
	  externalPort: 8012
Подготовка стенда: 
- Прочитать текущий @docker-compose.yml
- Остановить все контейнеры с модулями.
- Удалить из базы данных все текущие базы.
- Удалить из minio все записи
- исправить docker-compose.yml согласно новым условиям.
  условие1: При формировании файла создать все конфигурационные параметры заново, учитывая текущие изменения в исходных кодах.
  условие2: Модули storage-element используют один контейнере.
  условие3: Отличия в параметрах модулей storage-element описаны в разделе 'storage-elements'.
- Пересобрать контейнеры модулей без использования кеш.
- Запустить каждый контейнер по отдельности.
  условие1: Если требуется создать с нуля базу данных с применением всех alembic миграций.
  условие2: Проверить корректность запуска.
  условие3: Если при запуске обнаружены ошибки, записать ошибки в файл TEST-RESULTS.md и остановить процесс тестирования.
- Проверить наличие всех необходимых методов в API модулей для реализации "Процедура тестирования". Если возникают проблемы, подробно описать их файле TEST-RESULTS.md и остановить процесс тестирования.
Процедура тестирования:
- Загрузка тестовых файлов:
  - Загрузить в систему при помощи ingester-module 40 тестовых файлов, в качестве источника можно выбрать любые файлы из директории текущего проекта.
  - Проверить соответствует ли выбранный storage-element "Storage Element Selection Strategy".
  - Загружать в систему случайные текстовые файлы до тех пор пока хранилище не заполниться на 96%. Попутно проверяя логи и метрики на Capacity Status Levels.
	- Вопрос: стоит ли одновременно контролировать появление сообщений в WEB UI? Или для его тестирования сделать отдельные тесты?
  - Продолжить загружать случайные текстовые файлы до переключения загрузки на второй storage-element и появления 20 новых файлов во втором storage-element.
  - Переместить 20% загруженных файлов из первого storage-element в режиме edit в storage-elemnet, работающем в режиме rw.
  - Снова загрузить новые файлы в модуль работающий в режиме edit. Проверить в какой из модулей он загружается. Описать причину, почему новые файлы загружаются в этот модуль.
- На любом этапе в случае возникновения ошибки подробно описать ее в файл TEST-RESULTS.md и остановить процесс тестирования.
- Писать подробный отчет о каждом этапе тестирования в файл TEST-RESULTS.md.
Критерии успеха:
 - Все тесты пройдены без ошибок.
 - В minio появились все загруженные файлы и файлы с атрибутами.
 - В логах и метриках в необходимое время появляются статусы и сообщения согласно "Storage Element Selection Strategy".
```