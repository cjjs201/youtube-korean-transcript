# YouTube Korean Transcript Skill

A practical YouTube transcript extraction skill built for agent-based workflows.

This skill:
- Extracts subtitles from YouTube with `yt-dlp`
- Prefers Korean subtitle tracks (`ko`, `ko-KR`, `ko.*`) first
- Generates one readable output file: `<video_id>.ko.readable.md`
- Adds YAML frontmatter properties and summary sections:
  - `title`, `url`, `video_id`, `channel`, `published`, `created`
  - `needs_llm_translation`, `selected_subtitle_language`
  - `Executive Summary`, `Detailed Summary`, `Key Insights & Action Items`
- Uses chapter-based grouping when chapter metadata exists
- Falls back to time-range sections when chapters do not exist

## Repository Structure

```text
youtube-korean-transcript/
├── SKILL.md
├── README.md
├── LICENSE
├── .gitignore
└── scripts/
    └── extract_youtube_ko_transcript.py
```

## Requirements

- Python 3.10+
- `yt-dlp`

Python command by environment:

- macOS/Linux: `python3` (or `python` if `python --version` is 3.x)
- Windows: `py -3` (or `python` if it points to Python 3)

Install dependency (`<PYTHON_CMD>` is one of `python3`, `python`, `py -3`):

```bash
PIP_DISABLE_PIP_VERSION_CHECK=1 <PYTHON_CMD> -m pip install yt-dlp
```

## Usage

Run from this skill directory:

```bash
<PYTHON_CMD> scripts/extract_youtube_ko_transcript.py \
  --video "https://www.youtube.com/watch?v=VIDEO_ID" \
  --output-dir artifacts
```

Path behavior:
- If running inside Gemini temp sessions (`~/.gemini/tmp/...`), relative output paths (like `artifacts`) are mapped to the original project path from `.project_root`.
- Otherwise, relative output paths are resolved from the current working directory.

Optional flags:

```bash
<PYTHON_CMD> scripts/extract_youtube_ko_transcript.py \
  --video "https://www.youtube.com/watch?v=VIDEO_ID" \
  --output-dir artifacts \
  --cookies /path/to/cookies.txt \
  --proxy-url "http://user:pass@host:port" \
  --no-check-certificate
```

If you want to disable chapter grouping:

```bash
<PYTHON_CMD> scripts/extract_youtube_ko_transcript.py \
  --video "https://www.youtube.com/watch?v=VIDEO_ID" \
  --output-dir artifacts \
  --no-chapters
```

## Output Example

```text
---
title: "<video title>"
url: "https://www.youtube.com/watch?v=<video_id>"
video_id: "<video_id>"
channel: "<channel>"
published: 2026-02-19
created: 2026-02-24
category: "Video/Knowledge"
tags:
  - "📺Youtube"
needs_llm_translation: true|false
selected_subtitle_language: "en"
---

[영상 링크](https://www.youtube.com/watch?v=<video_id>)
![<video title>](<thumbnail_url>)

## 📌 Executive Summary
...
## 🔍 Detailed Summary
...
## 💡 Key Insights & Action Items
...
## 📝 Transcript
### 1. <chapter title> (00:00:00~00:03:10)
[00:00:00] ...
```

## LLM Post-Translation Workflow

When `needs_llm_translation: true`:
- Translate transcript body to Korean
- Fill summary sections in Korean
- Keep transcript section headings and `[HH:MM:SS]` timestamps unchanged
- Keep proper nouns in source language if needed
- Update YAML field to:

```text
needs_llm_translation: false
```

## Troubleshooting

- HTTP 429 / IP blocked:
  - Retry later
  - Change network (avoid cloud/VPN/Tailscale Exit Node egress)
  - Use `--cookies` or `--proxy-url`
- TLS certificate error:
  - Use `--no-check-certificate` only when your environment intercepts HTTPS
- No subtitles found:
  - The video may not expose downloadable subtitle tracks

## License

MIT License. See `LICENSE`.
