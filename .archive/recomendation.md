Отлично! Для продолжения работы с этого места в следующих сессиях вам понадобятся следующие команды:
🔄 Команды для продолжения работы
1. Загрузка контекста проекта (в начале каждой сессии)
/sc:load
Что делает: Загружает сохраненный контекст проекта из Serena MCP (project context, session history, architectural decisions)
2. Просмотр истории архитектурных решений
# Просто попросите Claude прочитать документ:
Прочитай @ARCHITECTURE_DECISIONS.md и дай краткое резюме текущего состояния архитектуры
3. Продолжение brainstorming (если нужно обсудить новые вопросы)
/sc:brainstorm "Тема для обсуждения"

# Примеры:
/sc:brainstorm "Детализация API спецификаций для Admin Module"
/sc:brainstorm "Стратегия миграции данных между Storage Elements"
/sc:brainstorm "Процедуры disaster recovery и backup"
4. Начало проектирования модуля
/sc:design "название модуля или компонента"

# Примеры:
/sc:design "Admin Module API endpoints"
/sc:design "Storage Element file operations"
/sc:design "Saga Pattern implementation for upload"
5. Начало реализации
/sc:implement "что нужно реализовать"

# Примеры:
/sc:implement "File naming utility с автоматическим обрезанием"
/sc:implement "Atomic attr.json write implementation"
/sc:implement "LDAP integration в Admin Module"
6. Сохранение состояния сессии (в конце работы)
/sc:save
Что делает: Сохраняет текущее состояние сессии в Serena MCP для продолжения в следующий раз
📋 Типичный workflow следующей сессии
# 1. Загрузить контекст проекта
/sc:load

# 2. Вспомнить где остановились
Покажи последние изменения в проекте и текущее состояние архитектуры

# 3. Продолжить работу (выбрать один из вариантов):

# Вариант A: Обсуждение новых вопросов
/sc:brainstorm "Детализация Saga Pattern для операции Upload"

# Вариант B: Проектирование компонента
/sc:design "Admin Module REST API"

# Вариант C: Начало кодирования
/sc:implement "Storage Element prototype с режимами EDIT/RW/RO/AR"

# 4. В конце работы - сохранить состояние
/sc:save
💡 Полезные команды для работы
Анализ кода
/sc:analyze @путь/к/файлу --focus architecture
/sc:analyze @admin-module/ --focus security
Создание тестов
/sc:test "создай unit тесты для generate_storage_filename функции"
Создание документации
/sc:document @admin-module/app/main.py
Улучшение кода
/sc:improve @storage-element/file_operations.py --focus performance
Git операции
/sc:git commit "описание изменений"
/sc:git "создай feature branch для Admin Module implementation"
🎯 Рекомендованный план следующей сессии
Сессия 1: API Спецификации
/sc:load
/sc:design "OpenAPI спецификации для Admin Module"
/sc:design "JSON schema для attr.json и webhook payloads"
/sc:save
Сессия 2: Прототип Storage Element
/sc:load
/sc:implement "Storage Element базовая структура проекта"
/sc:implement "File naming utility с тестами"
/sc:implement "Atomic attr.json write с WAL"
/sc:save
Сессия 3: Прототип Admin Module
/sc:load
/sc:implement "Admin Module базовая структура с FastAPI"
/sc:implement "JWT generation с RS256"
/sc:implement "LDAP integration базовая реализация"
/sc:save
📝 Важные замечания
Всегда начинайте с /sc:load - это загрузит контекст и покажет, где вы остановились
Используйте /sc:save в конце работы - это сохранит прогресс для следующей сессии
Ссылайтесь на документы через @:
@ARCHITECTURE_DECISIONS.md - архитектурные решения
@CLAUDE.md - инструкции для разработки
@README.md - обзор проекта
Используйте специализированные команды (/sc:design, /sc:implement) вместо общих запросов - они автоматически применяют нужные personas и инструменты
Готовы к завершению сессии! В следующий раз просто начните с /sc:load и Claude напомнит, где вы остановились. 🚀