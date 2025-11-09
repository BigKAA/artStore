# Вспомогательные инструменты

## MCP Serena

### Установка и настройка

```bash
cd /home/artur/Projects
git clone https://github.com/oraios/serena
cd serena
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Добавление MCP сервера в Claude Code

```bash
cd /home/artur/Projects/artStore
claude mcp add serena -- /home/artur/Projects/serena/start-mcp.sh "$(pwd)"
```

Файл [start-mcp.sh](../../serena/start-mcp.sh):
```bash
#!/bin/bash
source /home/artur/Projects/serena/.venv/bin/activate
cd /home/artur/Projects/serena
exec serena-mcp-server --context ide-assistant --project "$1"
```

### Запуск Dashboard для мониторинга

По факту не нужен. Дашборд автоматом запускается при старте serena.

```bash
# В отдельном терминале
/home/artur/Projects/serena/start-dashboard.sh
```

Затем откройте в браузере: **http://127.0.0.1:24282/dashboard/index.html**

Файл [start-dashboard.sh](../../serena/start-dashboard.sh):
```bash
#!/bin/bash
source /home/artur/Projects/serena/.venv/bin/activate
cd /home/artur/Projects/serena
exec serena-mcp-server --context ide-assistant --project /home/artur/Projects/artStore --transport sse --port 24283 --enable-web-dashboard true
```