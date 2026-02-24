---
name: youtube-korean-transcript
description: Extracts one readable markdown transcript from a YouTube URL or video ID using yt-dlp with Korean-first subtitle selection, then routes output through an LLM workflow for translation, summary writing, and humanized Korean style cleanup. Use when users ask to extract, structure, timestamp, or translate YouTube transcripts (especially into Korean).
---

# YouTube Korean Transcript

## Overview
Generate one readable markdown transcript file.
Use Korean subtitle tracks first; if the extracted text is non-Korean, your LLM workflow translates the readable file into Korean and overwrites the same file.
After translation/summarization, run a humanization pass to remove AI-style Korean writing patterns.

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
- `## 📎 Summary Source (Compact)`
- `## 📌 Executive Summary`
- `## 🔍 Detailed Summary`
- `## 💡 Key Insights & Action Items`
- `## 📝 Transcript`

### 5) Translate + summarize in your LLM workflow
Token-saving execution policy (MUST):
- Use exactly one LLM edit call per video (`replace` or one-shot file edit). Avoid multi-turn read/replace/write loops.
- Use `## 📎 Summary Source (Compact)` as the primary input for summary generation.
- Keep summary length limits:
  - `Executive Summary`: 4~6 sentences
  - `Detailed Summary`: 4~6 bullets
  - `Key Insights & Action Items`: 3~5 bullets
- Remove `## 📎 Summary Source (Compact)` before final delivery unless the user explicitly asks to keep it.

Case A: `needs_llm_translation: true`
- Translate transcript body text into Korean.
- Keep transcript section headers and `[HH:MM:SS]` timestamps exactly unchanged.
- Keep proper nouns/product names in original form when translation is awkward.
- Fill summary sections in Korean using compact summary source.
- Overwrite the same file (`<video_id>.ko.readable.md`) in place.
- Update YAML property to `needs_llm_translation: false`.

Case B: `needs_llm_translation: false`
- Do not rewrite transcript body.
- Fill or refine summary sections in Korean using compact summary source only.

### 5-1) Humanizer-KR pass (AI 티 제거)
After step 5, you MUST apply a humanized Korean style pass.

Core rewriting rules:
- Avoid hype-heavy words (`핵심적`, `획기적`, `중대한`, `새 지평`, `패러다임 전환`) unless objectively justified.
- Replace vague authority claims (`전문가들은`, `업계 관계자에 따르면`) with concrete sources, or remove.
- Reduce repetitive connectors (`이를 통해`, `아울러`, `나아가`, `이러한 맥락에서`).
- Reduce overuse of `~적` adjectives and inflated Sino-Korean wording.
- Avoid verbose forms like `~에 있어서`, `~함에 있어`; rewrite to direct Korean.
- Prefer concrete facts, numbers, and observable outcomes over abstract praise.
- Keep sentence rhythm mixed (short + medium); avoid monotonous, machine-like cadence.
- Preserve original meaning and factual content; do not alter timestamps or section boundaries.
- Keep professional tone, but avoid press-release style phrasing.

### 5-2) LLM Post-Translation Prompt Templates
Use one of the templates below in your current environment (Gemini/OpenAI/Claude).

Template A (Korean default):

```text
다음 Markdown 파일을 수정해 주세요.
파일 경로: <READABLE_FILE_PATH>

규칙:
1) 이 작업은 한 번의 편집 호출로 끝냅니다.
2) `## 📎 Summary Source (Compact)`만 사용해 요약을 작성합니다.
3) `needs_llm_translation: true`이면 `## 📝 Transcript` 본문을 자연스러운 한국어로 번역하고, `false`이면 Transcript는 수정하지 않습니다.
4) `## 📝 Transcript` 아래의 소제목과 `[HH:MM:SS]` 타임스탬프는 원문을 그대로 유지합니다.
5) `## 📌 Executive Summary`는 4~6문장, `## 🔍 Detailed Summary`는 4~6개 bullet, `## 💡 Key Insights & Action Items`는 3~5개 bullet로 작성합니다.
6) 고유명사(인명, 제품명, 프로젝트명)는 의미가 어색해지면 원문을 유지합니다.
7) YAML frontmatter는 유지하되 `needs_llm_translation: true`는 `needs_llm_translation: false`로 바꿉니다.
8) 마지막으로 AI 글쓰기 패턴을 제거합니다: 과장어, 모호한 출처, `~적`/`~에 있어서` 남용, 연결어 남발을 줄이고 더 자연스러운 한국어 문장으로 다듬습니다.
9) 최종본 저장 전 `## 📎 Summary Source (Compact)` 섹션은 삭제합니다(사용자가 유지 요청한 경우 제외).
10) 설명 출력 없이 파일만 덮어써서 저장합니다.
```

Template B (target language variable):

```text
Edit this markdown file in place.
File path: <READABLE_FILE_PATH>
Target language: <TARGET_LANGUAGE>

Requirements:
1) Complete this in one edit call.
2) Use only `Summary Source (Compact)` for summary writing.
3) If `needs_llm_translation: true`, translate transcript body into <TARGET_LANGUAGE>; otherwise, do not edit transcript body.
4) Preserve transcript section headings and `[HH:MM:SS]` timestamps exactly.
5) Keep summary lengths: Executive 4-6 sentences, Detailed 4-6 bullets, Action Items 3-5 bullets.
6) Keep proper nouns in original form when translation hurts clarity.
7) Keep YAML frontmatter unchanged except setting `needs_llm_translation: false` when translation is done.
8) Apply a humanization pass: remove hype-heavy wording, vague attribution, repetitive connectors, and overly formulaic AI phrasing.
9) Remove the `Summary Source (Compact)` section before final delivery unless the user asks to keep it.
10) Save changes to the same file with no extra commentary.
```

### 6) Apply response-quality checks
- Verify the file includes both first and last timestamps.
- Verify every timestamp is `HH:MM:SS`.
- Verify transcript section headers and timestamp tokens were not changed by translation.
- Verify summary sections were written from `Summary Source (Compact)` content.
- Verify all three summary sections are filled (not placeholders).
- Verify summary length limits are met.
- Verify `Summary Source (Compact)` is removed in the final file by default.
- Verify wording is not overly promotional or template-like AI prose.
- If any check fails, fix the file and re-run the checks before returning.
- If user asks for polishing, only fix obvious ASR wording issues.

### 7) Session hygiene for token savings
- Use one fresh chat/session per video URL.
- Do not continue from prior unrelated long threads when running this skill.

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
- `--summary-compact-sections`: max sections included in compact summary source (default: `8`)
- `--summary-compact-points`: max representative points per section in compact summary source (default: `2`)
- `--summary-compact-chars`: max characters per representative point in compact summary source (default: `180`)

## Failure Handling
- If transcript fetch fails, report the exact error briefly.
- If no subtitle track is accessible, state that clearly and stop.
- If YouTube blocks the network/IP (HTTP 429), retry later, change network, disable Tailscale Exit Node/VPN/cloud egress, or use `--cookies`/`--proxy-url`.
- If TLS certificate verification fails, retry with `--no-check-certificate` only in restricted environments.
