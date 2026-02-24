# YouTube Korean Transcript Skill

A practical YouTube transcript extraction skill built for agent-based workflows.

This skill:
- Extracts subtitles from YouTube with `yt-dlp`
- Prefers Korean subtitle tracks (`ko`, `ko-KR`, `ko.*`) first
- Generates one readable output file: `<video_id>.ko.readable.md`
- Adds metadata flags for post-translation workflows:
  - `Video ID`
  - `Video Title`
  - `Video URL`
  - `Needs LLM Translation`
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
# <video title>

- Video ID: <video_id>
- Video Title: <video_title>
- Video URL: <youtube_url>
- Needs LLM Translation: true|false

## 1. <chapter title> (00:00:00~00:03:10)
[00:00:00] ...
```

## LLM Post-Translation Workflow

When `Needs LLM Translation: true`:
- Translate transcript body to Korean
- Keep section headings and `[HH:MM:SS]` timestamps unchanged
- Keep proper nouns in source language if needed
- Update metadata line to:

```text
- Needs LLM Translation: false
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
