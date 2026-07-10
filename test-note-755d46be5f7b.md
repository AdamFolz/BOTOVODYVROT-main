# AI Knowledge Base

Локальная AI Knowledge Base без Obsidian для YouTube, PDF, HTML, TXT, Markdown, DOCX, медиа и папок курсов.

## Что это такое

Система хранит оригиналы материалов, извлекает текст, делает summaries, пишет manifests и собирает markdown-индексы для навигации и ответов по базе.

## Что уже настроено автоматически

- Создан полный каталог базы.
- Подготовлен CLI `scripts/kb.py`.
- Настроены manifests импорта, checksum SHA256, дедупликация и summaries.
- Создан `.venv` и выполнена попытка установки зависимостей.

## Куда кидать материалы

Можно класть материалы во `inbox/`, а затем запускать `python scripts/kb.py process`.

## Как добавить YouTube

`python scripts/kb.py add "https://www.youtube.com/watch?v=..."`

Если доступен `yt-dlp`, CLI заберёт metadata и попробует использовать субтитры. Если нет, будет создан fallback note со статусом `needs transcript`.

## Как добавить PDF

`python scripts/kb.py add "C:/path/to/file.pdf"`

Если доступен `pypdf`, текст будет извлечён по страницам. Иначе будет создан fallback extract.

## Как добавить папку курса

`python scripts/kb.py add "C:/path/to/course-folder"`

CLI рекурсивно пройдёт по папке, создаст manifest со списком файлов и обработает поддерживаемые типы.

## Как спросить Codex по базе

Попросите Codex опираться на `index.md`, `indexes/root.md`, `knowledge/summaries/` и конкретные source/extract-файлы. Для строгого режима используйте persona `personas/strict-source.md`.

## Как обновить индексы

`python scripts/kb.py rebuild-index`

## Что делать, если не работает транскрибация

Медиа и YouTube всё равно будут сохранены в базе. Если не хватает `yt-dlp`, `ffmpeg`, Whisper или субтитров, используйте созданный fallback extract и при необходимости позже добавьте транскрипт вручную.
