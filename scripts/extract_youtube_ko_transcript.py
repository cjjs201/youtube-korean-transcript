#!/usr/bin/env python3
"""Extract YouTube subtitles via yt-dlp and generate one readable markdown file."""

from __future__ import annotations

import argparse
from datetime import datetime
import html
import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def parse_video_id(value: str) -> str:
    raw = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
        return raw

    if not re.match(r"^https?://", raw):
        if "youtube.com" in raw or "youtu.be" in raw:
            raw = f"https://{raw}"
        else:
            raise ValueError(f"Unsupported video input: {value}")

    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    path_parts = [p for p in parsed.path.split("/") if p]

    if host.endswith("youtu.be") and path_parts:
        candidate = path_parts[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
            return candidate

    if "youtube.com" in host:
        query_v = parse_qs(parsed.query).get("v", [])
        if query_v and re.fullmatch(r"[A-Za-z0-9_-]{11}", query_v[0]):
            return query_v[0]

        if len(path_parts) >= 2 and path_parts[0] in {"shorts", "embed", "live"}:
            candidate = path_parts[1]
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
                return candidate

    raise ValueError(f"Could not extract video ID from input: {value}")


def parse_lang_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def is_korean_lang_code(lang: str) -> bool:
    lower = lang.lower()
    return lower == "ko" or lower.startswith("ko-") or lower.startswith("ko_")


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\n", " ").replace("\t", " ").replace(">>", "")
    return re.sub(r"\s+", " ", text).strip()


def ends_sentence(text: str) -> bool:
    trimmed = text.strip()
    if not trimmed:
        return False
    trimmed = re.sub(r'["\')\]\s]+$', "", trimmed)
    return bool(re.search(r"[.!?…]$", trimmed))


def starts_with_lowercase_ascii(text: str) -> bool:
    for ch in text.strip():
        if ch.isalpha():
            return ch.islower()
        if ch.isdigit():
            return False
    return False


def hhmmss(seconds: float) -> str:
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_vtt_time(value: str) -> float:
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(value)


def parse_json3(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    snippets: list[dict] = []

    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs:
            continue

        text = "".join(seg.get("utf8", "") for seg in segs)
        text = clean_text(text)
        if not text:
            continue

        start = float(event.get("tStartMs", 0)) / 1000.0
        duration = float(event.get("dDurationMs", 0)) / 1000.0
        snippets.append({"text": text, "start": start, "duration": duration})

    return snippets


def parse_vtt(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    snippets: list[dict] = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if "-->" not in line:
            i += 1
            continue

        try:
            start_str, end_str = [x.strip() for x in line.split("-->", 1)]
            start = parse_vtt_time(start_str.split(" ")[0])
            end = parse_vtt_time(end_str.split(" ")[0])
        except Exception:
            i += 1
            continue

        i += 1
        text_lines: list[str] = []
        while i < len(lines) and lines[i].strip() != "":
            if not lines[i].startswith("NOTE"):
                text_lines.append(lines[i])
            i += 1

        text = clean_text(" ".join(text_lines))
        if text:
            snippets.append(
                {
                    "text": text,
                    "start": max(0.0, start),
                    "duration": max(0.0, end - start),
                }
            )

        i += 1

    return snippets


def paragraphize(
    snippets: list[dict],
    max_chars: int = 620,
    max_gap: float = 8.0,
    hard_max_chars: int = 900,
) -> list[tuple[float, str]]:
    paragraphs: list[tuple[float, str]] = []
    cur_texts: list[str] = []
    cur_start: float | None = None
    last_start: float | None = None

    for item in snippets:
        text = item["text"]
        if not text:
            continue

        if cur_start is None:
            cur_start = item["start"]

        projected = (" ".join(cur_texts) + " " + text).strip() if cur_texts else text
        gap = 0.0 if last_start is None else item["start"] - last_start

        if cur_texts and gap > max_gap:
            paragraphs.append((cur_start, " ".join(cur_texts).strip()))
            cur_texts = [text]
            cur_start = item["start"]
            last_start = item["start"]
            continue

        if cur_texts and len(projected) > max_chars:
            prev_text = cur_texts[-1]
            should_split = ends_sentence(prev_text) or not starts_with_lowercase_ascii(text)

            # If the next cue clearly continues the same sentence, keep it attached.
            if not should_split and len(projected) <= hard_max_chars:
                cur_texts.append(text)
            else:
                paragraphs.append((cur_start, " ".join(cur_texts).strip()))
                cur_texts = [text]
                cur_start = item["start"]
        else:
            cur_texts.append(text)

        last_start = item["start"]

    if cur_texts and cur_start is not None:
        paragraphs.append((cur_start, " ".join(cur_texts).strip()))

    return paragraphs


def trim_text_for_summary(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact

    sliced = compact[:max_chars]
    sentence_cut = max(sliced.rfind(". "), sliced.rfind("? "), sliced.rfind("! "))
    if sentence_cut >= max_chars // 2:
        return sliced[: sentence_cut + 1].strip()

    word_cut = sliced.rfind(" ")
    if word_cut >= max_chars // 2:
        sliced = sliced[:word_cut]

    return sliced.rstrip(" ,;:") + "..."


def collect_sections(
    snippets: list[dict],
    chapters: list[dict],
    total_duration: float,
    section_seconds: float,
) -> list[dict]:
    sections: list[dict] = []

    if chapters:
        for chapter_index, chapter in enumerate(chapters, start=1):
            chapter_start = chapter["start"]
            chapter_end = chapter["end"]
            section_snippets = [
                item for item in snippets if chapter_start <= item["start"] < chapter_end
            ]
            if not section_snippets:
                continue
            sections.append(
                {
                    "heading": f"{chapter_index}. {chapter['title']}",
                    "start": chapter_start,
                    "end": chapter_end,
                    "snippets": section_snippets,
                }
            )

    if sections:
        return sections

    section_index = 1
    section_start = 0.0
    while section_start < total_duration:
        section_end = min(total_duration, section_start + section_seconds)
        if section_end <= section_start:
            break

        section_snippets = [
            item for item in snippets if section_start <= item["start"] < section_end
        ]
        if section_snippets:
            sections.append(
                {
                    "heading": f"Section {section_index}",
                    "start": section_start,
                    "end": section_end,
                    "snippets": section_snippets,
                }
            )
            section_index += 1

        section_start = section_end

    return sections


def build_compact_summary_source(
    sections: list[dict],
    max_sections: int,
    max_points_per_section: int,
    max_chars_per_point: int,
) -> list[str]:
    compact_lines: list[str] = []
    selected_sections = sections[: max(1, max_sections)]

    for section in selected_sections:
        paras = paragraphize(
            section["snippets"],
            max_chars=max_chars_per_point,
            max_gap=15.0,
            hard_max_chars=max_chars_per_point * 2,
        )
        if not paras:
            continue

        selected_texts: list[str] = [paras[0][1]]

        if len(paras) > 2 and len(selected_texts) < max_points_per_section:
            middle_text = paras[len(paras) // 2][1]
            if middle_text not in selected_texts:
                selected_texts.append(middle_text)

        if len(paras) > 1 and len(selected_texts) < max_points_per_section:
            last_text = paras[-1][1]
            if last_text not in selected_texts:
                selected_texts.append(last_text)

        selected_texts = selected_texts[: max(1, max_points_per_section)]
        merged = " | ".join(trim_text_for_summary(t, max_chars_per_point) for t in selected_texts)

        compact_lines.append(
            f"- [{hhmmss(section['start'])}~{hhmmss(section['end'])}] {section['heading']}: {merged}"
        )

    return compact_lines


def normalize_chapters(chapters: list[dict] | None, total_duration: float) -> list[dict]:
    if not chapters:
        return []

    cleaned: list[dict] = []
    for idx, chapter in enumerate(chapters):
        start_val = chapter.get("start_time", chapter.get("start"))
        if start_val is None:
            continue

        try:
            start = float(start_val)
        except Exception:
            continue

        if start >= total_duration:
            continue

        end_val = chapter.get("end_time", chapter.get("end"))
        end: float | None = None
        if end_val is not None:
            try:
                end = float(end_val)
            except Exception:
                end = None

        title = str(chapter.get("title") or f"Chapter {idx + 1}").strip() or f"Chapter {idx + 1}"
        cleaned.append(
            {
                "title": title,
                "start": max(0.0, start),
                "end": end,
            }
        )

    if not cleaned:
        return []

    cleaned.sort(key=lambda x: x["start"])
    normalized: list[dict] = []

    for idx, chapter in enumerate(cleaned):
        start = chapter["start"]
        next_start = cleaned[idx + 1]["start"] if idx + 1 < len(cleaned) else total_duration
        end = chapter["end"] if chapter["end"] is not None else next_start
        end = min(total_duration, end)
        if end <= start:
            end = min(total_duration, next_start)
        if end <= start:
            continue

        normalized.append(
            {
                "title": chapter["title"],
                "start": start,
                "end": end,
            }
        )

    return normalized


class _YDLLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def debug(self, msg: str) -> None:
        return

    def warning(self, msg: str) -> None:
        self.warnings.append(str(msg))

    def error(self, msg: str) -> None:
        self.errors.append(str(msg))


def detect_ip_block(messages: list[str]) -> bool:
    text = "\n".join(messages).lower()
    return (
        "http error 429" in text
        or "too many requests" in text
        or ("ip" in text and "block" in text)
        or "sign in to confirm you're not a bot" in text
    )


def detect_ssl_cert_error(message: str) -> bool:
    text = message.lower()
    return "certificate verify failed" in text or "certificateverifyerror" in text


def normalize_yyyymmdd(value: str) -> str | None:
    raw = value.strip()
    if re.fullmatch(r"\d{8}", raw):
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    return None


def detect_published_date(info: dict) -> str | None:
    for key in ("release_date", "upload_date"):
        maybe = normalize_yyyymmdd(str(info.get(key) or ""))
        if maybe:
            return maybe

    ts = info.get("release_timestamp") or info.get("timestamp")
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            return datetime.utcfromtimestamp(ts).date().isoformat()
        except Exception:
            return None
    return None


def yaml_quote(value: str) -> str:
    cleaned = value.replace("\n", " ").strip()
    escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def gather_available_languages(info: dict) -> list[str]:
    subs = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    return dedupe_keep_order(list(subs.keys()) + list(auto.keys()))


def build_candidate_languages(available: list[str], preferred_ko: list[str], source_languages: list[str]) -> list[str]:
    candidates: list[str] = []

    # Always request Korean and Korean-translation variants first.
    candidates.extend(preferred_ko)
    candidates.extend(["ko", "ko-KR", "ko.*"])
    for source_lang in source_languages:
        candidates.append(f"ko-{source_lang}")

    # Fallback order when Korean cannot be resolved by YouTube.
    candidates.extend(source_languages)
    candidates.extend(available[:5])

    return dedupe_keep_order(candidates)


def download_subtitles_with_ytdlp(
    video_url: str,
    video_id: str,
    preferred_ko: list[str],
    source_languages: list[str],
    proxy_url: str | None,
    cookie_file: str | None,
    user_agent: str | None,
    no_check_certificate: bool,
):
    try:
        import yt_dlp
    except ModuleNotFoundError:
        raise RuntimeError(
            "Missing dependency: yt-dlp. Install with: PIP_DISABLE_PIP_VERSION_CHECK=1 python3 -m pip install yt-dlp"
        )

    info_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
    }
    if proxy_url:
        info_opts["proxy"] = proxy_url
    if cookie_file:
        info_opts["cookiefile"] = cookie_file
    if user_agent:
        info_opts["user_agent"] = user_agent
    if no_check_certificate:
        info_opts["nocheckcertificate"] = True
    with yt_dlp.YoutubeDL(info_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    video_title = str(info.get("title") or video_id).strip()
    video_web_url = str(info.get("webpage_url") or video_url).strip()
    channel_name = str(info.get("channel") or info.get("uploader") or "").strip()
    thumbnail_url = str(info.get("thumbnail") or "").strip()
    published_date = detect_published_date(info)

    available_languages = gather_available_languages(info)
    candidate_languages = build_candidate_languages(available_languages, preferred_ko, source_languages)

    logger = _YDLLogger()
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        dl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": candidate_languages,
            "subtitlesformat": "json3/vtt/best",
            "outtmpl": str(tmp_dir / "%(id)s.%(ext)s"),
            "ignoreerrors": True,
            "quiet": True,
            "no_warnings": False,
            "logger": logger,
        }
        if proxy_url:
            dl_opts["proxy"] = proxy_url
        if cookie_file:
            dl_opts["cookiefile"] = cookie_file
        if user_agent:
            dl_opts["user_agent"] = user_agent
        if no_check_certificate:
            dl_opts["nocheckcertificate"] = True

        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ydl.extract_info(video_url, download=True)

        files: list[dict] = []
        pattern = re.compile(rf"^{re.escape(video_id)}\.([^.]+)\.([^.]+)$")
        for path in sorted(tmp_dir.iterdir()):
            if not path.is_file():
                continue
            m = pattern.match(path.name)
            if not m:
                continue
            lang = m.group(1)
            ext = m.group(2).lower()
            files.append({"path": path, "lang": lang, "ext": ext})

        parsed: list[dict] = []
        for item in files:
            try:
                if item["ext"] == "json3":
                    snippets = parse_json3(item["path"])
                elif item["ext"] == "vtt":
                    snippets = parse_vtt(item["path"])
                else:
                    continue
            except Exception:
                continue

            if snippets:
                parsed.append({"lang": item["lang"], "ext": item["ext"], "snippets": snippets})
    return {
        "video_title": video_title,
        "video_url": video_web_url,
        "channel_name": channel_name,
        "thumbnail_url": thumbnail_url,
        "published_date": published_date,
        "chapters": info.get("chapters") or [],
        "available_languages": available_languages,
        "candidate_languages": candidate_languages,
        "parsed_tracks": parsed,
        "warnings": logger.warnings,
        "errors": logger.errors,
    }


def choose_best_track(tracks: list[dict], preferred_ko: list[str], source_languages: list[str]) -> dict | None:
    if not tracks:
        return None

    source_index = {lang: idx for idx, lang in enumerate(source_languages)}
    ko_index = {lang: idx for idx, lang in enumerate(preferred_ko)}

    def rank(track: dict):
        lang = track["lang"]
        if is_korean_lang_code(lang):
            return (0, ko_index.get(lang, 999), len(track["snippets"]) * -1)
        return (1, source_index.get(lang, 999), len(track["snippets"]) * -1)

    return sorted(tracks, key=rank)[0]


def decide_proxy(proxy_url: str | None, proxy_https_url: str | None, proxy_http_url: str | None) -> str | None:
    if proxy_url:
        return proxy_url
    if proxy_https_url:
        return proxy_https_url
    if proxy_http_url:
        return proxy_http_url
    return None


def track_mode(selected_lang: str) -> str:
    if is_korean_lang_code(selected_lang):
        return "korean-direct-or-translated-track"
    return "source-language-fallback"


def find_project_root_marker(start_dir: Path) -> tuple[Path, Path] | None:
    cur = start_dir.resolve()
    while True:
        marker = cur / ".project_root"
        if marker.is_file():
            try:
                target = marker.read_text(encoding="utf-8", errors="replace").strip()
            except Exception:
                target = ""
            if not target:
                return None
            return marker, Path(target).expanduser()
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def resolve_output_dir(output_dir_arg: str, cwd: Path | None = None) -> Path:
    output_dir = Path(output_dir_arg).expanduser()
    if output_dir.is_absolute():
        return output_dir.resolve()

    cwd = cwd or Path.cwd()
    marker_info = find_project_root_marker(cwd)
    if marker_info:
        marker, real_project_root = marker_info
        tmp_project_root = marker.parent.resolve()
        cwd_resolved = cwd.resolve()
        try:
            relative_cwd = cwd_resolved.relative_to(tmp_project_root)
        except ValueError:
            relative_cwd = Path(".")
        mapped_cwd = (real_project_root / relative_cwd).expanduser()
        return (mapped_cwd / output_dir).resolve()

    # Fallback: keep the classic behavior (relative to current working directory).
    return (cwd / output_dir).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract subtitles via yt-dlp and generate one readable markdown file."
    )
    parser.add_argument("--video", required=True, help="YouTube URL or 11-char video ID")
    parser.add_argument("--output-dir", default="artifacts", help="Output directory (default: artifacts)")
    parser.add_argument(
        "--prefer-korean-languages",
        default="ko,ko-KR",
        help="Preferred Korean subtitle language codes",
    )
    parser.add_argument(
        "--source-languages",
        dest="source_languages",
        default="en,en-US,ja,es,fr,de",
        help="Fallback source subtitle language order",
    )
    parser.add_argument(
        "--languages",
        dest="source_languages",
        help="Backward-compatible alias of --source-languages",
    )
    parser.add_argument(
        "--proxy-url",
        help="Proxy URL for yt-dlp (for example http://user:pass@host:port)",
    )
    parser.add_argument(
        "--proxy-http-url",
        help="Legacy alias for proxy URL (HTTP)",
    )
    parser.add_argument(
        "--proxy-https-url",
        help="Legacy alias for proxy URL (HTTPS)",
    )
    parser.add_argument(
        "--cookies",
        help="Path to Netscape-format cookies file for YouTube authenticated fetch",
    )
    parser.add_argument(
        "--user-agent",
        help="Optional custom User-Agent for yt-dlp requests",
    )
    parser.add_argument(
        "--no-check-certificate",
        action="store_true",
        help="Disable TLS certificate verification (use only in restricted environments)",
    )
    parser.add_argument(
        "--no-chapters",
        action="store_true",
        help="Disable chapter-based organization and use fixed section ranges only",
    )
    parser.add_argument(
        "--section-minutes",
        type=int,
        default=10,
        help="Section size in minutes for readable markdown (default: 10)",
    )
    parser.add_argument(
        "--summary-compact-sections",
        type=int,
        default=8,
        help="Max sections included in compact summary source (default: 8)",
    )
    parser.add_argument(
        "--summary-compact-points",
        type=int,
        default=2,
        help="Max representative points per section in compact summary source (default: 2)",
    )
    parser.add_argument(
        "--summary-compact-chars",
        type=int,
        default=180,
        help="Max characters per representative point in compact summary source (default: 180)",
    )
    args = parser.parse_args()

    try:
        video_id = parse_video_id(args.video)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    preferred_ko = parse_lang_list(args.prefer_korean_languages)
    source_languages = parse_lang_list(args.source_languages)
    if not preferred_ko:
        preferred_ko = ["ko", "ko-KR"]

    proxy_url = decide_proxy(args.proxy_url, args.proxy_https_url, args.proxy_http_url)

    cookie_file: str | None = None
    if args.cookies:
        cookie_path = Path(args.cookies).expanduser()
        if not cookie_path.exists():
            print(f"Cookie file does not exist: {cookie_path}", file=sys.stderr)
            return 1
        cookie_file = str(cookie_path)

    try:
        result = download_subtitles_with_ytdlp(
            video_url=f"https://www.youtube.com/watch?v={video_id}",
            video_id=video_id,
            preferred_ko=preferred_ko,
            source_languages=source_languages,
            proxy_url=proxy_url,
            cookie_file=cookie_file,
            user_agent=args.user_agent,
            no_check_certificate=args.no_check_certificate,
        )
    except Exception as exc:
        message = str(exc)
        if detect_ssl_cert_error(message):
            print(
                "Failed to prepare subtitle download: TLS certificate verification failed.\n"
                "Retry with --no-check-certificate only if your environment intercepts HTTPS.",
                file=sys.stderr,
            )
            return 2
        print(f"Failed to prepare subtitle download for {video_id}: {message}", file=sys.stderr)
        return 2
    video_title = str(result.get("video_title") or video_id).strip()
    video_web_url = str(result.get("video_url") or f"https://www.youtube.com/watch?v={video_id}").strip()
    channel_name = str(result.get("channel_name") or "Unknown").strip() or "Unknown"
    thumbnail_url = str(result.get("thumbnail_url") or "").strip()
    created_date = datetime.now().date().isoformat()
    published_date = str(result.get("published_date") or created_date).strip()

    best = choose_best_track(result["parsed_tracks"], preferred_ko, source_languages)
    if best is None:
        messages = result["warnings"] + result["errors"]
        if detect_ip_block(messages):
            print(
                "Failed to fetch subtitles: YouTube blocked this network/IP (HTTP 429 likely).\n"
                "If using Tailscale Exit Node or cloud/VPN egress, switch to a residential/local network.\n"
                "Then retry with --cookies or --proxy-url.",
                file=sys.stderr,
            )
            return 3
        print("Failed to fetch subtitles: no downloadable subtitle track found.", file=sys.stderr)
        return 2

    selected_lang = best["lang"]
    korean_output = is_korean_lang_code(selected_lang)

    snippets = best["snippets"]
    out_dir = resolve_output_dir(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    readable_path = out_dir / f"{video_id}.ko.readable.md"
    total_duration = snippets[-1]["start"] + snippets[-1]["duration"]
    section_seconds = max(60, args.section_minutes * 60)
    chapters = [] if args.no_chapters else normalize_chapters(result.get("chapters"), total_duration)
    sections = collect_sections(snippets, chapters, total_duration, section_seconds)
    summary_compact_sections = max(1, args.summary_compact_sections)
    summary_compact_points = max(1, args.summary_compact_points)
    summary_compact_chars = max(80, args.summary_compact_chars)
    compact_summary_lines = build_compact_summary_source(
        sections=sections,
        max_sections=summary_compact_sections,
        max_points_per_section=summary_compact_points,
        max_chars_per_point=summary_compact_chars,
    )

    needs_llm_translation = str((not korean_output)).lower()
    readable_lines = [
        "---",
        f"title: {yaml_quote(video_title)}",
        f"url: {yaml_quote(video_web_url)}",
        f"video_id: {yaml_quote(video_id)}",
        f"channel: {yaml_quote(channel_name)}",
        f"published: {published_date}",
        f"created: {created_date}",
        'category: "Video/Knowledge"',
        "tags:",
        '  - "📺Youtube"',
        f"needs_llm_translation: {needs_llm_translation}",
        f"selected_subtitle_language: {yaml_quote(selected_lang)}",
        "---",
        "",
        f"[영상 링크]({video_web_url})",
    ]
    if thumbnail_url:
        readable_lines.extend(
            [
                f"![{video_title}]({thumbnail_url})",
                "",
            ]
        )
    readable_lines.extend(
        [
            "## 📎 Summary Source (Compact)",
            "- 아래 항목만으로 요약을 작성하세요. (토큰 절약 모드)",
            f"- 요약 반영 범위: 상위 {min(len(sections), summary_compact_sections)}개 섹션",
            "",
        ]
    )
    if compact_summary_lines:
        readable_lines.extend(compact_summary_lines)
    else:
        readable_lines.append("- (Compact source를 생성하지 못했습니다. Transcript 상단 구간을 기준으로 요약하세요.)")
    readable_lines.extend(
        [
            "",
            "## 📌 Executive Summary",
            "- (4~6문장으로 작성해 주세요.)",
            "",
            "## 🔍 Detailed Summary",
            "### 핵심 개념 및 주요 사항",
            "Keywords: (5~10개)",
            "",
            "### 섹션별 상세 분석",
            "- (4~6개 bullet로 작성해 주세요.)",
            "",
            "## 💡 Key Insights & Action Items",
            "- (3~5개 action item으로 작성해 주세요.)",
            "",
            "## 📝 Transcript",
            "",
        ]
    )

    for section in sections:
        readable_lines.append(
            f"### {section['heading']} ({hhmmss(section['start'])}~{hhmmss(section['end'])})"
        )
        readable_lines.append("")
        for p_start, p_text in paragraphize(section["snippets"]):
            readable_lines.append(f"[{hhmmss(p_start)}] {p_text}")
            readable_lines.append("")

    readable_path.write_text("\n".join(readable_lines).rstrip() + "\n", encoding="utf-8")

    print(f"video_id={video_id}")
    print(f"segments={len(snippets)}")
    print(f"duration={hhmmss(total_duration)}")
    print(f"selected_language={selected_lang}")
    print(f"needs_llm_translation={needs_llm_translation}")
    print(f"summary_source_sections={min(len(sections), summary_compact_sections)}")
    print(f"readable={readable_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
