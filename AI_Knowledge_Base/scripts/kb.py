#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen


BASE_DIR = Path(__file__).resolve().parents[1]
STRUCTURE_DIRS = [
    "inbox",
    "sources/youtube",
    "sources/pdf",
    "sources/html",
    "sources/text",
    "sources/media",
    "sources/courses",
    "sources/other",
    "extracts/transcripts",
    "extracts/pdf",
    "extracts/html",
    "extracts/text",
    "extracts/media",
    "extracts/docx",
    "knowledge/wiki",
    "knowledge/summaries",
    "knowledge/playbooks",
    "knowledge/concepts",
    "knowledge/people",
    "indexes",
    "personas",
    "projects/imports",
    "projects/reports",
    "projects/manifests",
    "scripts",
]
TEXT_EXTS = {".txt", ".md"}
MEDIA_EXTS = {".mp4", ".mp3", ".m4a", ".wav", ".mov"}
HTML_EXTS = {".html", ".htm"}
PDF_EXTS = {".pdf"}
DOCX_EXTS = {".docx"}
SEARCH_EXTS = {".md", ".txt", ".json"}


def optional_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str, limit: int = 80) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug[:limit] or "item"


def ensure_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_setup_report(message: str) -> None:
    report = BASE_DIR / "projects" / "reports" / "setup-report.md"
    prefix = f"- {utcnow()}: "
    existing = report.read_text(encoding="utf-8") if report.exists() else "# Setup Report\n\n"
    ensure_text(report, existing + prefix + message + "\n")


def rel(path: Path) -> str:
    return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def is_youtube_url(value: str) -> bool:
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    return "youtube.com" in host or "youtu.be" in host


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    ensure_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def load_existing_manifests() -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for path in sorted((BASE_DIR / "projects" / "imports").glob("*.json")):
        try:
            manifests.append(read_json(path))
        except Exception:
            continue
    return manifests


def find_duplicate_by_sha(file_sha: str) -> dict[str, Any] | None:
    for manifest in load_existing_manifests():
        if manifest.get("sha256") == file_sha:
            return manifest
        for item in manifest.get("items", []):
            if item.get("sha256") == file_sha:
                return manifest
    return None


def find_duplicate_by_url(url: str) -> dict[str, Any] | None:
    for manifest in load_existing_manifests():
        if manifest.get("source_url") == url:
            return manifest
    return None


def classify_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTS:
        return "text"
    if suffix in HTML_EXTS:
        return "html"
    if suffix in PDF_EXTS:
        return "pdf"
    if suffix in DOCX_EXTS:
        return "docx"
    if suffix in MEDIA_EXTS:
        return "media"
    return "other"


def target_source_dir(kind: str) -> Path:
    mapping = {
        "text": BASE_DIR / "sources" / "text",
        "html": BASE_DIR / "sources" / "html",
        "pdf": BASE_DIR / "sources" / "pdf",
        "docx": BASE_DIR / "sources" / "other",
        "media": BASE_DIR / "sources" / "media",
        "other": BASE_DIR / "sources" / "other",
    }
    return mapping[kind]


def target_extract_dir(kind: str) -> Path:
    mapping = {
        "text": BASE_DIR / "extracts" / "text",
        "html": BASE_DIR / "extracts" / "html",
        "pdf": BASE_DIR / "extracts" / "pdf",
        "docx": BASE_DIR / "extracts" / "docx",
        "media": BASE_DIR / "extracts" / "media",
        "youtube": BASE_DIR / "extracts" / "transcripts",
    }
    return mapping[kind]


def safe_copy(source: Path, destination_dir: Path, digest: str | None = None) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    digest = digest or sha256_file(source)
    stem = slugify(source.stem)
    name = f"{stem}-{digest[:12]}{source.suffix.lower()}"
    target = destination_dir / name
    if not target.exists():
        shutil.copy2(source, target)
    return target


def extract_text_from_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_text_from_html(path: Path) -> tuple[str, list[str]]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    links = re.findall(r"""href=["']([^"']+)["']""", raw, flags=re.I)
    if optional_module("bs4"):
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(raw, "html.parser")
        for bad in soup(["script", "style"]):
            bad.decompose()
        text = soup.get_text("\n", strip=True)
        return text, links
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, flags=re.I | re.S)
    body = re.sub(r"<script.*?</script>", " ", raw, flags=re.I | re.S)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.I | re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(re.sub(r"\s+", " ", body)).strip()
    title = html.unescape(title_match.group(1).strip()) if title_match else ""
    combined = f"{title}\n\n{body}".strip()
    return combined, links


def extract_text_from_pdf(path: Path) -> str:
    if not optional_module("pypdf"):
        return "PDF saved. Text extraction requires pypdf.\n"
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(path))
    pages: list[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            text = f"[page {idx} extraction error: {exc}]"
        pages.append(f"# Page {idx}\n\n{text.strip()}\n")
    return "\n".join(pages).strip() + "\n"


def extract_text_from_docx(path: Path) -> str:
    if not optional_module("docx"):
        return "DOCX saved. Text extraction requires python-docx.\n"
    from docx import Document  # type: ignore

    doc = Document(str(path))
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(lines).strip() + "\n"


def summarize_text(text: str, title: str) -> tuple[str, list[str], list[str], list[str]]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        cleaned = "No extractable text available yet."
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    summary = " ".join(sentences[:3]).strip()[:600]
    lines = [line.strip(" -•\t") for line in text.splitlines() if line.strip()]
    ideas = lines[:5] if lines else [summary]
    practical = []
    for idea in ideas[:3]:
        practical.append(f"Use: {idea[:140]}")
    tags = sorted({slugify(word, 24) for word in re.findall(r"[A-Za-zА-Яа-я0-9]{4,}", cleaned)[:12]})
    if not tags:
        tags = [slugify(title)]
    return summary, ideas[:5], practical[:3], tags[:8]


def extract_title_from_text(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:120]
    return fallback


def build_summary_markdown(
    *,
    title: str,
    source_ref: str,
    kind: str,
    imported_at: str,
    summary: str,
    ideas: list[str],
    practical: list[str],
    tags: list[str],
    source_path: str,
    extract_path: str,
) -> str:
    idea_lines = "\n".join(f"- {item}" for item in ideas) or "- No key ideas extracted."
    practical_lines = "\n".join(f"- {item}" for item in practical) or "- No practical takeaways yet."
    tag_line = ", ".join(f"`{tag}`" for tag in tags) or "`untagged`"
    return textwrap.dedent(
        f"""\
        # {title}

        - source path/url: {source_ref}
        - type: {kind}
        - imported_at: {imported_at}
        - source file: `{source_path}`
        - extract file: `{extract_path}`

        ## Brief Summary

        {summary}

        ## Key Ideas

        {idea_lines}

        ## Practical Takeaways

        {practical_lines}

        ## Tags

        {tag_line}
        """
    ).strip() + "\n"


def create_summary_and_manifest(
    *,
    title: str,
    source_ref: str,
    kind: str,
    source_path: Path,
    extract_path: Path,
    imported_at: str,
    manifest: dict[str, Any],
) -> None:
    text = extract_path.read_text(encoding="utf-8", errors="ignore") if extract_path.exists() else ""
    summary, ideas, practical, tags = summarize_text(text, title)
    summary_name = f"{slugify(title)}-{manifest['manifest_id'][:12]}.md"
    summary_path = BASE_DIR / "knowledge" / "summaries" / summary_name
    ensure_text(
        summary_path,
        build_summary_markdown(
            title=title,
            source_ref=source_ref,
            kind=kind,
            imported_at=imported_at,
            summary=summary,
            ideas=ideas,
            practical=practical,
            tags=tags,
            source_path=rel(source_path),
            extract_path=rel(extract_path),
        ),
    )
    manifest["summary_path"] = rel(summary_path)
    manifest["tags"] = tags
    manifest["title"] = title


def create_basic_files() -> None:
    for folder in STRUCTURE_DIRS:
        (BASE_DIR / folder).mkdir(parents=True, exist_ok=True)
    defaults = {
        BASE_DIR / "README.md": textwrap.dedent(
            """\
            # AI Knowledge Base

            Локальная база знаний для материалов: YouTube, PDF, HTML, TXT, Markdown, DOCX, медиа и папок курсов.

            ## Что уже настроено автоматически

            - Создана структура папок для источников, извлечённого текста, summaries, wiki и индексов.
            - Подготовлен CLI `scripts/kb.py`.
            - Настроены manifests импорта, checksum и дедупликация.

            ## Куда кидать материалы

            Помещайте новые файлы во `inbox/` или добавляйте напрямую через CLI.

            ## Как добавить YouTube

            `python scripts/kb.py add "https://www.youtube.com/watch?v=..."`

            ## Как добавить PDF

            `python scripts/kb.py add "C:/path/to/file.pdf"`

            ## Как добавить папку курса

            `python scripts/kb.py add "C:/path/to/course-folder"`

            ## Как спросить Codex по базе

            Укажите Codex, что ответы должны опираться на файлы из `index.md`, `indexes/root.md`, `knowledge/summaries/` и нужные source/extract-файлы.

            ## Как обновить индексы

            `python scripts/kb.py rebuild-index`

            ## Что делать, если не работает транскрибация

            Медиа и YouTube всё равно сохраняются. Если `yt-dlp`, `ffmpeg`, Whisper или субтитры недоступны, CLI создаёт fallback extract note со статусом `needs transcript`.
            """
        ).strip()
        + "\n",
        BASE_DIR / "AGENTS.md": textwrap.dedent(
            """\
            # Agent Rules

            - Агент всегда сначала читает `index.md` и `indexes/root.md`.
            - Агент не удаляет `sources/` без прямой команды пользователя.
            - Если агент отвечает по базе, он указывает источники.
            - Если подтверждения в базе нет, агент честно сообщает об этом.
            - Новые материалы сначала сохраняются как source, потом создаётся extract, потом summary/wiki, потом обновляются indexes.
            - Агент не смешивает personas без команды пользователя.
            """
        ).strip()
        + "\n",
        BASE_DIR / "index.md": "# AI Knowledge Base Index\n\nUse `indexes/root.md` as the main navigation file.\n",
        BASE_DIR / "requirements.txt": "yt-dlp\npypdf\nbeautifulsoup4\npython-docx\nmarkdownify\n",
        BASE_DIR / ".gitignore": ".venv/\n__pycache__/\n*.pyc\n.DS_Store\ntmp/\n*.wav\n*.mp3\n",
        BASE_DIR / "inbox" / "README.md": "# Inbox\n\nDrop new materials here, then run `python scripts/kb.py process`.\n",
        BASE_DIR / "knowledge" / "glossary.md": "# Glossary\n\n- Knowledge Base: Local repository of sources, extracts, summaries and indexes.\n",
        BASE_DIR / "knowledge" / "wiki" / "getting-started.md": textwrap.dedent(
            """\
            # Getting Started

            1. Add materials with `scripts/kb.py add <path_or_url>` or place them into `inbox/`.
            2. Run `scripts/kb.py process` to import inbox materials.
            3. Read `knowledge/summaries/` and `indexes/` for navigation.
            """
        ).strip()
        + "\n",
        BASE_DIR / "indexes" / "root.md": "# Root Index\n\nNo materials indexed yet.\n",
        BASE_DIR / "indexes" / "sources.md": "# Sources Index\n\nNo sources yet.\n",
        BASE_DIR / "indexes" / "topics.md": "# Topics Index\n\nNo topics yet.\n",
        BASE_DIR / "indexes" / "personas.md": "# Personas Index\n\n- `personas/default.md`\n- `personas/strict-source.md`\n- `personas/teacher.md`\n- `personas/strategist.md`\n",
        BASE_DIR / "personas" / "default.md": "# Default Persona\n\nКоротко, практично, без воды.\n",
        BASE_DIR / "personas" / "strict-source.md": "# Strict Source Persona\n\nОтвечать только по материалам базы. Не додумывать. Если источника нет, сказать, что подтверждения нет.\n",
        BASE_DIR / "personas" / "teacher.md": "# Teacher Persona\n\nОбъяснять как преподаватель. Давать примеры и упражнения.\n",
        BASE_DIR / "personas" / "strategist.md": "# Strategist Persona\n\nПревращать знания в план действий, продукт, оффер, контент и систему.\n",
    }
    for path, content in defaults.items():
        if not path.exists():
            ensure_text(path, content)


def maybe_import_url(url: str) -> dict[str, Any]:
    if is_youtube_url(url):
        return import_youtube(url)
    return import_generic_url(url)


def import_generic_url(url: str) -> dict[str, Any]:
    duplicate = find_duplicate_by_url(url)
    if duplicate:
        return {"status": "duplicate", "reason": "URL already imported", "manifest": duplicate.get("manifest_path")}
    imported_at = utcnow()
    parsed = urlparse(url)
    title_seed = slugify(parsed.path.rsplit("/", 1)[-1] or parsed.netloc)
    source_path = BASE_DIR / "sources" / "html" / f"{title_seed}.url.md"
    extract_path = BASE_DIR / "extracts" / "html" / f"{title_seed}.md"
    try:
        with urlopen(url, timeout=20) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "")
        raw_html = data.decode("utf-8", errors="ignore")
        ensure_text(source_path, f"# URL Source\n\n- url: {url}\n- fetched_at: {imported_at}\n- content_type: {content_type}\n")
        tmp_html = BASE_DIR / "tmp_generic_url.html"
        ensure_text(tmp_html, raw_html)
        text, links = extract_text_from_html(tmp_html)
        tmp_html.unlink(missing_ok=True)
        body = f"# Extracted HTML\n\nSource: {url}\n\n## Text\n\n{text}\n\n## Links\n\n" + "\n".join(f"- {link}" for link in links)
        ensure_text(extract_path, body)
        title = extract_title_from_text(text, parsed.netloc)
        manifest_id = hashlib.sha256(url.encode("utf-8")).hexdigest()
        manifest = {
            "manifest_id": manifest_id,
            "manifest_path": rel(BASE_DIR / "projects" / "imports" / f"{manifest_id[:12]}.json"),
            "source_url": url,
            "source_type": "html_url",
            "imported_at": imported_at,
            "status": "imported",
            "errors": [],
            "source_path": rel(source_path),
            "extract_path": rel(extract_path),
        }
        create_summary_and_manifest(
            title=title,
            source_ref=url,
            kind="html_url",
            source_path=source_path,
            extract_path=extract_path,
            imported_at=imported_at,
            manifest=manifest,
        )
        manifest_path = BASE_DIR / "projects" / "imports" / f"{manifest_id[:12]}.json"
        write_json(manifest_path, manifest)
        rebuild_indexes()
        return {"status": "imported", "manifest": rel(manifest_path)}
    except Exception as exc:
        manifest_id = hashlib.sha256(url.encode("utf-8")).hexdigest()
        manifest = {
            "manifest_id": manifest_id,
            "manifest_path": rel(BASE_DIR / "projects" / "imports" / f"{manifest_id[:12]}.json"),
            "source_url": url,
            "source_type": "url",
            "imported_at": imported_at,
            "status": "error",
            "errors": [str(exc)],
        }
        write_json(BASE_DIR / "projects" / "imports" / f"{manifest_id[:12]}.json", manifest)
        return {"status": "error", "error": str(exc)}


def find_yt_dlp() -> list[str] | None:
    for candidate in ("yt-dlp", "yt_dlp"):
        path = shutil.which(candidate)
        if path:
            return [path]
    return None


def import_youtube(url: str) -> dict[str, Any]:
    duplicate = find_duplicate_by_url(url)
    if duplicate:
        return {"status": "duplicate", "reason": "URL already imported", "manifest": duplicate.get("manifest_path")}
    imported_at = utcnow()
    manifest_id = hashlib.sha256(url.encode("utf-8")).hexdigest()
    slug = slugify(urlparse(url).path or manifest_id[:12])
    source_path = BASE_DIR / "sources" / "youtube" / f"{slug}-{manifest_id[:12]}.md"
    extract_path = BASE_DIR / "extracts" / "transcripts" / f"{slug}-{manifest_id[:12]}.md"
    errors: list[str] = []
    yt_dlp = find_yt_dlp()
    meta: dict[str, Any] = {}
    transcript_note = "needs transcript"
    if yt_dlp:
        try:
            result = subprocess.run(
                yt_dlp + ["--dump-single-json", "--skip-download", url],
                capture_output=True,
                text=True,
                check=True,
            )
            meta = json.loads(result.stdout)
            subtitles = meta.get("subtitles") or meta.get("automatic_captions") or {}
            transcript_note = "subtitles available" if subtitles else "needs transcript"
        except Exception as exc:
            errors.append(f"yt-dlp metadata error: {exc}")
    else:
        errors.append("yt-dlp not available")
    source_note = {
        "url": url,
        "imported_at": imported_at,
        "title": meta.get("title") or "YouTube source",
        "channel": meta.get("channel"),
        "duration": meta.get("duration"),
        "status": transcript_note,
        "metadata": meta,
    }
    ensure_text(source_path, "# YouTube Source\n\n" + json.dumps(source_note, indent=2, ensure_ascii=False) + "\n")
    transcript_content = textwrap.dedent(
        f"""\
        # YouTube Extract

        - url: {url}
        - imported_at: {imported_at}
        - status: {transcript_note}

        Transcript is not embedded by default. Use subtitles if available, otherwise transcription is needed.
        """
    )
    ensure_text(extract_path, transcript_content)
    manifest = {
        "manifest_id": manifest_id,
        "manifest_path": rel(BASE_DIR / "projects" / "imports" / f"{manifest_id[:12]}.json"),
        "source_url": url,
        "source_type": "youtube",
        "imported_at": imported_at,
        "status": "imported_with_fallback" if errors else "imported",
        "errors": errors,
        "source_path": rel(source_path),
        "extract_path": rel(extract_path),
    }
    create_summary_and_manifest(
        title=meta.get("title") or f"YouTube {manifest_id[:8]}",
        source_ref=url,
        kind="youtube",
        source_path=source_path,
        extract_path=extract_path,
        imported_at=imported_at,
        manifest=manifest,
    )
    manifest_path = BASE_DIR / "projects" / "imports" / f"{manifest_id[:12]}.json"
    write_json(manifest_path, manifest)
    rebuild_indexes()
    return {"status": manifest["status"], "manifest": rel(manifest_path)}


def build_extract_note(kind: str, title: str, source_ref: str, text: str) -> str:
    return textwrap.dedent(
        f"""\
        # {title}

        - source: {source_ref}
        - type: {kind}

        {text.strip()}
        """
    ).strip() + "\n"


def import_file(path: Path) -> dict[str, Any]:
    kind = classify_path(path)
    digest = sha256_file(path)
    duplicate = find_duplicate_by_sha(digest)
    if duplicate:
        return {"status": "duplicate", "reason": "sha256 already imported", "manifest": duplicate.get("manifest_path")}
    imported_at = utcnow()
    source_copy = safe_copy(path, target_source_dir(kind), digest)
    extract_name = f"{source_copy.stem}.md"
    extract_path = target_extract_dir(kind) / extract_name
    errors: list[str] = []
    try:
        if kind == "text":
            extracted = extract_text_from_text(path)
        elif kind == "html":
            text, links = extract_text_from_html(path)
            extracted = "# HTML Extract\n\n" + text + "\n\n## Links\n\n" + "\n".join(f"- {link}" for link in links) + "\n"
        elif kind == "pdf":
            extracted = extract_text_from_pdf(path)
        elif kind == "docx":
            extracted = extract_text_from_docx(path)
        elif kind == "media":
            extracted = "Media saved, transcription needed.\n"
        else:
            extracted = "Source saved. No extractor for this file type yet.\n"
    except Exception as exc:
        errors.append(str(exc))
        extracted = f"Extraction error: {exc}\n"
    title = extract_title_from_text(extracted, path.stem)
    if kind == "media":
        extracted = build_extract_note(kind, title, rel(source_copy), extracted)
    elif kind in {"pdf", "docx", "other"} and "requires" in extracted.lower():
        extracted = build_extract_note(kind, title, rel(source_copy), extracted)
    ensure_text(extract_path, extracted)
    manifest_id = digest
    manifest = {
        "manifest_id": manifest_id,
        "manifest_path": rel(BASE_DIR / "projects" / "imports" / f"{manifest_id[:12]}.json"),
        "source_type": kind,
        "source_original": str(path.resolve()),
        "imported_at": imported_at,
        "sha256": digest,
        "size_bytes": path.stat().st_size,
        "status": "imported_with_errors" if errors else "imported",
        "errors": errors,
        "source_path": rel(source_copy),
        "extract_path": rel(extract_path),
    }
    create_summary_and_manifest(
        title=title,
        source_ref=rel(source_copy),
        kind=kind,
        source_path=source_copy,
        extract_path=extract_path,
        imported_at=imported_at,
        manifest=manifest,
    )
    manifest_path = BASE_DIR / "projects" / "imports" / f"{manifest_id[:12]}.json"
    write_json(manifest_path, manifest)
    rebuild_indexes()
    return {"status": manifest["status"], "manifest": rel(manifest_path)}


def import_course_folder(path: Path) -> dict[str, Any]:
    imported_at = utcnow()
    manifest_id = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()
    course_dir = BASE_DIR / "sources" / "courses" / f"{slugify(path.name)}-{manifest_id[:12]}"
    course_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for file_path in sorted(path.rglob("*")):
        if not file_path.is_file():
            continue
        item: dict[str, Any] = {
            "path": str(file_path.resolve()),
            "size_bytes": file_path.stat().st_size,
            "type": classify_path(file_path),
        }
        try:
            item["sha256"] = sha256_file(file_path)
            if item["type"] in {"text", "html", "pdf", "docx", "media"}:
                result = import_file(file_path)
                item["status"] = result["status"]
                item["manifest"] = result.get("manifest")
            else:
                item["status"] = "reference_only"
        except Exception as exc:
            item["status"] = "error"
            item["error"] = str(exc)
            errors.append(f"{file_path}: {exc}")
        items.append(item)
    copied_manifest = course_dir / "course-folder-source.md"
    ensure_text(
        copied_manifest,
        f"# Course Folder Source\n\n- original_path: {path.resolve()}\n- imported_at: {imported_at}\n- file_count: {len(items)}\n",
    )
    manifest = {
        "manifest_id": manifest_id,
        "manifest_path": rel(BASE_DIR / "projects" / "imports" / f"{manifest_id[:12]}.json"),
        "source_type": "course_folder",
        "source_original": str(path.resolve()),
        "imported_at": imported_at,
        "status": "imported_with_errors" if errors else "imported",
        "errors": errors,
        "items": items,
        "source_path": rel(copied_manifest),
    }
    manifest_path = BASE_DIR / "projects" / "imports" / f"{manifest_id[:12]}.json"
    write_json(manifest_path, manifest)
    rebuild_indexes()
    return {"status": manifest["status"], "manifest": rel(manifest_path)}


def process_inbox() -> list[dict[str, Any]]:
    results = []
    for item in sorted((BASE_DIR / "inbox").iterdir()):
        if item.name.lower() == "readme.md":
            continue
        results.append(add_entry(str(item)))
    return results


def add_entry(target: str) -> dict[str, Any]:
    create_basic_files()
    if is_url(target):
        return maybe_import_url(target)
    path = Path(target)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")
    if path.is_dir():
        return import_course_folder(path)
    return import_file(path)


def count_files(path: Path, pattern: str) -> int:
    return sum(1 for _ in path.glob(pattern))


def status_payload() -> dict[str, int]:
    manifests = load_existing_manifests()
    errors = 0
    for manifest in manifests:
        errors += len(manifest.get("errors", []))
        for item in manifest.get("items", []):
            if item.get("status") == "error":
                errors += 1
    return {
        "sources": sum(1 for p in (BASE_DIR / "sources").rglob("*") if p.is_file()),
        "extracts": sum(1 for p in (BASE_DIR / "extracts").rglob("*") if p.is_file()),
        "summaries": count_files(BASE_DIR / "knowledge" / "summaries", "*.md"),
        "wiki": count_files(BASE_DIR / "knowledge" / "wiki", "*.md"),
        "manifests": count_files(BASE_DIR / "projects" / "imports", "*.json"),
        "errors": errors,
    }


def rebuild_indexes() -> None:
    summaries = sorted((BASE_DIR / "knowledge" / "summaries").glob("*.md"))
    manifests = load_existing_manifests()
    source_lines = ["# Sources Index", ""]
    topic_map: dict[str, list[str]] = {}
    for manifest in manifests:
        title = manifest.get("title") or manifest.get("source_url") or manifest.get("source_original") or manifest.get("source_path")
        source_ref = manifest.get("source_path") or manifest.get("source_url") or "unknown"
        summary_ref = manifest.get("summary_path") or "missing"
        source_lines.append(f"- {title}: `{source_ref}` -> `{summary_ref}`")
        for tag in manifest.get("tags", []):
            topic_map.setdefault(tag, []).append(summary_ref)
    if len(source_lines) == 2:
        source_lines.append("- No sources yet.")
    ensure_text(BASE_DIR / "indexes" / "sources.md", "\n".join(source_lines) + "\n")

    topic_lines = ["# Topics Index", ""]
    for tag in sorted(topic_map):
        refs = ", ".join(f"`{ref}`" for ref in sorted(set(topic_map[tag])))
        topic_lines.append(f"- {tag}: {refs}")
    if len(topic_lines) == 2:
        topic_lines.append("- No topics yet.")
    ensure_text(BASE_DIR / "indexes" / "topics.md", "\n".join(topic_lines) + "\n")

    root_lines = [
        "# Root Index",
        "",
        "- Main index: `index.md`",
        "- Sources: `indexes/sources.md`",
        "- Topics: `indexes/topics.md`",
        "- Personas: `indexes/personas.md`",
        "- Glossary: `knowledge/glossary.md`",
        "- Getting started: `knowledge/wiki/getting-started.md`",
        "",
        "## Recent Summaries",
        "",
    ]
    if summaries:
        for summary in summaries[-20:]:
            root_lines.append(f"- `{rel(summary)}`")
    else:
        root_lines.append("- No summaries yet.")
    ensure_text(BASE_DIR / "indexes" / "root.md", "\n".join(root_lines) + "\n")

    main_lines = [
        "# AI Knowledge Base Index",
        "",
        "Start with `indexes/root.md`.",
        "",
        "## Collections",
        "",
        "- `sources/` originals",
        "- `extracts/` extracted text",
        "- `knowledge/summaries/` processed summaries",
        "- `knowledge/wiki/` curated notes",
        "",
        "## Summary Files",
        "",
    ]
    if summaries:
        for summary in summaries:
            main_lines.append(f"- `{rel(summary)}`")
    else:
        main_lines.append("- No summaries yet.")
    ensure_text(BASE_DIR / "index.md", "\n".join(main_lines) + "\n")


def search_knowledge(query: str) -> list[str]:
    hits: list[str] = []
    pattern = query.lower()
    for path in BASE_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SEARCH_EXTS:
            continue
        try:
            for idx, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
                if pattern in line.lower():
                    hits.append(f"{rel(path)}:{idx}: {line.strip()}")
        except Exception:
            continue
    return hits


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local AI Knowledge Base CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init")
    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("path_or_url")
    subparsers.add_parser("process")
    subparsers.add_parser("status")
    subparsers.add_parser("rebuild-index")
    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query")
    return parser


def cmd_init() -> int:
    create_basic_files()
    rebuild_indexes()
    print(f"Initialized knowledge base at {BASE_DIR}")
    return 0


def cmd_add(path_or_url: str) -> int:
    result = add_entry(path_or_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_process() -> int:
    results = process_inbox()
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def cmd_status() -> int:
    print(json.dumps(status_payload(), ensure_ascii=False, indent=2))
    return 0


def cmd_rebuild_index() -> int:
    rebuild_indexes()
    print("Indexes rebuilt.")
    return 0


def cmd_search(query: str) -> int:
    hits = search_knowledge(query)
    if hits:
        print("\n".join(hits))
    else:
        print("No matches found.")
    return 0


def main(argv: list[str] | None = None) -> int:
    create_basic_files()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        return cmd_init()
    if args.command == "add":
        return cmd_add(args.path_or_url)
    if args.command == "process":
        return cmd_process()
    if args.command == "status":
        return cmd_status()
    if args.command == "rebuild-index":
        return cmd_rebuild_index()
    if args.command == "search":
        return cmd_search(args.query)
    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
