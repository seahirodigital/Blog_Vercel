"""Blog VercelのMLX URLから安全にローカルTerminalを起動する。"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


URL_SCHEME = "blogvercel-mlx"
WORKER_COMMAND = Path(
    "/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command"
)
JOB_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def parse_launcher_url(raw_url: str) -> list[str]:
    """許可したURL形式から最大5件のUUIDだけを返す。"""
    parsed = urlparse(raw_url)
    if parsed.scheme != URL_SCHEME or parsed.netloc != "run" or parsed.path not in ("", "/"):
        raise ValueError("Blog Vercel MLXランチャー用URLではありません")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if set(query) - {"job_id"}:
        raise ValueError("許可されていないURLパラメータがあります")
    job_ids = list(dict.fromkeys(value.strip() for value in query.get("job_id", []) if value.strip()))
    if not 1 <= len(job_ids) <= 5:
        raise ValueError("1〜5件のジョブIDが必要です")
    if any(not JOB_ID_PATTERN.fullmatch(job_id) for job_id in job_ids):
        raise ValueError("ジョブIDの形式が不正です")
    return job_ids


def terminal_command(job_ids: list[str]) -> str:
    """検証済みジョブIDを周辺機器ワーカーの引数へ変換する。"""
    parts = [shlex.quote(str(WORKER_COMMAND))]
    for job_id in job_ids:
        parts.extend(("--job-id", shlex.quote(job_id)))
    return " ".join(parts)


def _apple_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", " ")
    return f'"{escaped}"'


def open_terminal(job_ids: list[str]) -> None:
    if not WORKER_COMMAND.is_file():
        raise FileNotFoundError(f"MLX起動ファイルが見つかりません: {WORKER_COMMAND}")
    if not WORKER_COMMAND.stat().st_mode & 0o111:
        raise PermissionError(f"MLX起動ファイルに実行権限がありません: {WORKER_COMMAND}")
    command = terminal_command(job_ids)
    script = (
        'tell application "Terminal"\n'
        "activate\n"
        f"do script {_apple_string(command)}\n"
        "end tell"
    )
    completed = subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "不明なエラー").strip()[:300]
        raise RuntimeError(f"Terminalを起動できませんでした: {detail}")


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    print_only = arguments[:1] == ["--print-command"]
    if print_only:
        arguments = arguments[1:]
    if len(arguments) != 1:
        raise ValueError("Blog Vercel MLXランチャーURLを1件指定してください")
    job_ids = parse_launcher_url(arguments[0])
    if print_only:
        print(terminal_command(job_ids))
    else:
        open_terminal(job_ids)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"MLXランチャーエラー: {error}", file=sys.stderr)
        raise SystemExit(1)
