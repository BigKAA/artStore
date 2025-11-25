# TODO добавляемые вручную

## ✅ COMPLETED

Title: Убрать подключение между модулями по mTLS. Убрать из кода и всей документации. Составить план (stages) работ по модулям.
Priority: Hi
Module: All
Status: COMPLETED (2025-11-25)
Branch: feature/remove-mtls
Commit: 05defea
Details:
- ✅ Удалены TLSSettings классы из всех модулей
- ✅ Удален tls_middleware.py из Admin Module
- ✅ Удалены все TLS/mTLS integration и unit тесты (7 файлов)
- ✅ Обновлена документация (README.md, CLAUDE.md, Serena memories)
- ✅ Удалено ~4145 строк кода
- ✅ Cryptography зависимость сохранена (требуется для JWT RS256)
Result: Система работает через HTTP с OAuth 2.0 JWT аутентификацией

---

## TODO

Title: Добавить переменную среды окружения для указания включения SSL протокола при подключении к базе данных.
Priority: Low
Module: All