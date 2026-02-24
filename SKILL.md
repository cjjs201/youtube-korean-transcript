---
name: youtube-korean-transcript
description: Extracts one readable markdown transcript from a YouTube URL or video ID using yt-dlp with Korean-first subtitle selection, then routes non-Korean output through an LLM translation workflow. Use when users ask to extract, structure, timestamp, or translate YouTube transcripts (especially into Korean).
---

# YouTube Korean Transcript

## Overview
Generate one readable markdown transcript file.
Use Korean subtitle tracks first; if the extracted text is non-Korean, your LLM workflow translates the readable file into Korean and overwrites the same file.

## Workflow

### 1) Collect inputs
- Accept one YouTube URL or 11-char video ID.
- Default output directory is `artifacts/` unless the user asks otherwise.
- If running inside Gemini temp sessions (`~/.gemini/tmp/...`), relative output paths are mapped to the original project path from `.project_root`.

### 2) Ensure dependency
Pick `<PYTHON_CMD>` by environment:
- macOS/Linux: `python3` (or `python` if `python --version` is 3.x)
- Windows: `py -3` (or `python` if it points to Python 3)

```bash
PIP_DISABLE_PIP_VERSION_CHECK=1 <PYTHON_CMD> -m pip install yt-dlp
```

### 3) Run the extractor
Run from this skill directory:

```bash
<PYTHON_CMD> scripts/extract_youtube_ko_transcript.py \
  --video "https://www.youtube.com/watch?v=VIDEO_ID" \
  --output-dir artifacts
```

If YouTube blocks requests, retry with network/auth options:

```bash
<PYTHON_CMD> scripts/extract_youtube_ko_transcript.py \
  --video "https://www.youtube.com/watch?v=VIDEO_ID" \
  --output-dir artifacts \
  --cookies /path/to/cookies.txt
```

or

```bash
<PYTHON_CMD> scripts/extract_youtube_ko_transcript.py \
  --video "https://www.youtube.com/watch?v=VIDEO_ID" \
  --output-dir artifacts \
  --proxy-url "http://user:pass@host:port"
```

If your environment has TLS interception/certificate issues:

```bash
<PYTHON_CMD> scripts/extract_youtube_ko_transcript.py \
  --video "https://www.youtube.com/watch?v=VIDEO_ID" \
  --output-dir artifacts \
  --no-check-certificate
```

### 4) Confirm generated output
Expect one file:
- `<video_id>.ko.readable.md`
- If chapters exist on YouTube metadata, readable output is grouped by chapter titles.
- If chapters do not exist, output falls back to fixed section ranges by `--section-minutes`.

Frontmatter/YAML properties to check:
- `title: ...`
- `url: ...`
- `video_id: ...`
- `channel: ...`
- `published: YYYY-MM-DD`
- `created: YYYY-MM-DD`
- `needs_llm_translation: true|false`

Summary/template sections to check:
- `## 📌 Executive Summary`
- `## 🔍 Detailed Summary`
- `## 💡 Key Insights & Action Items`
- `## 📝 Transcript`

### 5) Translate + summarize in your LLM workflow
When `needs_llm_translation: true`, you MUST:
- Translate transcript body text into Korean.
- Keep transcript section headers and `[HH:MM:SS]` timestamps exactly unchanged.
- Keep proper nouns/product names in original form when translation is awkward.
- Fill summary sections in Korean:
  - `## 📌 Executive Summary`
  - `## 🔍 Detailed Summary`
  - `## 💡 Key Insights & Action Items`
- Overwrite the same file (`<video_id>.ko.readable.md`) in place.
- Update YAML property in that file:
  - `needs_llm_translation: false`

When `needs_llm_translation: false`, you SHOULD still fill summary sections in Korean.

### 5-1) LLM Post-Translation Prompt Templates
Use one of the templates below in your current environment (Gemini/OpenAI/Claude).

Template A (Korean default):

```text
다음 Markdown 파일을 수정해 주세요.
파일 경로: <READABLE_FILE_PATH>

규칙:
1) `needs_llm_translation: true`이면 본문 자막 문장을 자연스러운 한국어로 번역합니다.
2) `## 📝 Transcript` 아래의 소제목과 `[HH:MM:SS]` 타임스탬프는 원문을 그대로 유지합니다.
3) `## 📌 Executive Summary`, `## 🔍 Detailed Summary`, `## 💡 Key Insights & Action Items`를 한국어로 채웁니다.
4) 고유명사(인명, 제품명, 프로젝트명)는 의미가 어색해지면 원문을 유지합니다.
5) YAML frontmatter는 유지하되 `needs_llm_translation: true`는 `needs_llm_translation: false`로 바꿉니다.
6) 설명 출력 없이 파일만 덮어써서 저장합니다.
```

Template B (target language variable):

```text
Edit this markdown file in place.
File path: <READABLE_FILE_PATH>
Target language: <TARGET_LANGUAGE>

Requirements:
1) If `needs_llm_translation: true`, translate transcript body sentences into <TARGET_LANGUAGE>.
2) Preserve transcript section headings and `[HH:MM:SS]` timestamps exactly.
3) Fill `Executive Summary / Detailed Summary / Key Insights` in <TARGET_LANGUAGE>.
4) Keep proper nouns in original form when translation hurts clarity.
5) Keep YAML frontmatter unchanged except setting `needs_llm_translation: false`.
6) Save changes to the same file with no extra commentary.
```

### 6) Apply response-quality checks
- Verify the file includes both first and last timestamps.
- Verify every timestamp is `HH:MM:SS`.
- Verify transcript section headers and timestamp tokens were not changed by translation.
- Verify all three summary sections are filled (not placeholders).
- If any check fails, fix the file and re-run the checks before returning.
- If user asks for polishing, only fix obvious ASR wording issues.

## Script Options

`extract_youtube_ko_transcript.py` supports:
- `--video`: YouTube URL or 11-char video ID (required)
- `--output-dir`: destination folder (default: `artifacts`; relative paths map to original project path in Gemini temp sessions, otherwise current working directory)
- `--prefer-korean-languages`: preferred Korean track codes (default: `ko,ko-KR`)
- `--source-languages`: fallback source track order (default: `en,en-US,ja,es,fr,de`)
- `--languages`: backward-compatible alias of `--source-languages`
- `--proxy-url`: proxy URL for yt-dlp
- `--proxy-http-url`: legacy alias for HTTP proxy
- `--proxy-https-url`: legacy alias for HTTPS proxy
- `--cookies`: Netscape-format cookies file path
- `--user-agent`: custom User-Agent string
- `--no-check-certificate`: disable TLS certificate verification (use only when needed)
- `--no-chapters`: disable chapter-based organization and always use fixed section ranges
- `--section-minutes`: readable markdown section size (default: `10`)

## Failure Handling
- If transcript fetch fails, report the exact error briefly.
- If no subtitle track is accessible, state that clearly and stop.
- If YouTube blocks the network/IP (HTTP 429), retry later, change network, disable Tailscale Exit Node/VPN/cloud egress, or use `--cookies`/`--proxy-url`.
- If TLS certificate verification fails, retry with `--no-check-certificate` only in restricted environments.
