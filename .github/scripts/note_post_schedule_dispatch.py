#!/usr/bin/env python3
"""note公開予約をGitHub Actions内で確認して、事前起動対象を投稿ジョブへ渡す。"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any


GITHUB_API = "https://api.github.com"
WORKFLOW_FILE = "note-post.yml"
SCHEDULE_PATH = "data/note-post-schedules.json"
MAX_CLAIM_RETRIES = 3
DEFAULT_QUEUE_STALE_MINUTES = 90
DEFAULT_PRESTART_WINDOW_MINUTES = 35
DEFAULT_LATE_GRACE_MINUTES = 720
TRANSIENT_HTTP_STATUS_CODES = {502, 503, 504}
MAX_HTTP_REQUEST_ATTEMPTS = 6



class ScheduleConflictError(RuntimeError):
    """予約ファイル更新の競合。別監視ジョブが先に処理した可能性が高い。"""


def log(message: str) -> None:
    print(message, flush=True)


def request_json(method: str, url: str, token: str, payload: dict[str, Any] | None = None, accept_404: bool = False) -> tuple[int, dict[str, Any]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")

    for attempt in range(1, MAX_HTTP_REQUEST_ATTEMPTS + 1):
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
                return response.status, json.loads(body) if body else {}
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            if accept_404 and error.code == 404:
                return 404, {}
            if error.code == 409:
                raise ScheduleConflictError(body[:300])
            if error.code in TRANSIENT_HTTP_STATUS_CODES and attempt < MAX_HTTP_REQUEST_ATTEMPTS:
                sleep_seconds = min(30, 2 ** attempt)
                log(f"GitHub API ???????????????????: method={method}, status={error.code}, attempt={attempt}, sleepSeconds={sleep_seconds}")
                time.sleep(sleep_seconds)
                continue
            raise RuntimeError(f"{method} {url} failed: {error.code} {body[:500]}") from error
        except urllib.error.URLError as error:
            if attempt < MAX_HTTP_REQUEST_ATTEMPTS:
                sleep_seconds = min(30, 2 ** attempt)
                log(f"GitHub API ??????????????????: method={method}, attempt={attempt}, sleepSeconds={sleep_seconds}, error={error}")
                time.sleep(sleep_seconds)
                continue
            raise RuntimeError(f"{method} {url} failed: {error}") from error

    raise RuntimeError(f"{method} {url} failed after retries")


def parse_schedules(raw: str) -> list[dict[str, Any]]:
    if not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise RuntimeError(f"予約ファイルJSONを解析できません: {exc}") from exc
    if not isinstance(parsed, list):
        raise RuntimeError("予約ファイルJSONのルートが配列ではありません")
    return [item for item in parsed if isinstance(item, dict)]


def api_base(repo: str) -> str:
    return f"{GITHUB_API}/repos/{repo}"


def schedule_url(repo: str) -> str:
    encoded_path = urllib.parse.quote(SCHEDULE_PATH, safe="/")
    return f"{api_base(repo)}/contents/{encoded_path}"


def load_schedules(repo: str, token: str) -> tuple[list[dict[str, Any]], str]:
    status, file_data = request_json("GET", schedule_url(repo), token, accept_404=True)
    if status == 200:
        raw = base64.b64decode((file_data.get("content") or "").replace("\n", "")).decode("utf-8")
        return parse_schedules(raw), str(file_data.get("sha") or "")
    return [], ""


def save_schedules(repo: str, token: str, schedules: list[dict[str, Any]], sha: str, message: str) -> None:
    payload: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(
            (json.dumps(schedules, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        ).decode("ascii"),
    }
    if sha:
        payload["sha"] = sha
    request_json("PUT", schedule_url(repo), token, payload)


def env_int(name: str, fallback: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return fallback
    return value if value > 0 else fallback


def env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def parse_publish_at(item: dict[str, Any]) -> datetime | None:
    raw_publish_at = str(item.get("publishAt") or "")
    try:
        return datetime.fromisoformat(raw_publish_at.replace("Z", "+00:00"))
    except Exception:
        return None


def should_claim(
    item: dict[str, Any],
    now: datetime,
    queue_stale_seconds: int,
    prestart_seconds: int,
    late_grace_seconds: int,
) -> bool:
    publish_at = parse_publish_at(item)

    if item.get("status") == "scheduled":
        if publish_at is None:
            return True
        seconds_until_publish = (publish_at - now).total_seconds()
        return -late_grace_seconds <= seconds_until_publish <= prestart_seconds

    if item.get("status") != "queued" or item.get("publishedAt"):
        return False

    if publish_at is not None and (now - publish_at).total_seconds() > late_grace_seconds:
        return False

    raw_queued_at = str(item.get("queuedAt") or "")
    try:
        queued_at = datetime.fromisoformat(raw_queued_at.replace("Z", "+00:00"))
    except Exception:
        return True
    return (now - queued_at).total_seconds() >= queue_stale_seconds


def claim_due_schedules(
    repo: str,
    token: str,
    source: str,
    queue_stale_minutes: int,
    prestart_window_minutes: int,
    late_grace_minutes: int,
) -> tuple[list[dict[str, Any]], int]:
    queue_stale_seconds = queue_stale_minutes * 60
    prestart_seconds = prestart_window_minutes * 60
    late_grace_seconds = late_grace_minutes * 60

    for attempt in range(1, MAX_CLAIM_RETRIES + 1):
        schedules, sha = load_schedules(repo, token)
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        claimed: list[dict[str, Any]] = []
        changed = False
        next_schedules: list[dict[str, Any]] = []

        log(f"予約ファイルを確認しました: total={len(schedules)}, attempt={attempt}")

        for item in schedules:
            if item.get("status") == "scheduled" and parse_publish_at(item) is None:
                changed = True
                next_schedules.append({
                    **item,
                    "status": "error",
                    "error": f"publishAtを解析できません: {item.get('publishAt')}",
                })
                continue

            if not should_claim(item, now, queue_stale_seconds, prestart_seconds, late_grace_seconds):
                next_schedules.append(item)
                continue

            changed = True
            if not item.get("fileId") or not item.get("id"):
                next_schedules.append({
                    **item,
                    "status": "error",
                    "error": "fileId または予約IDが空のため起動できません。",
                })
                continue

            claimed_item = {
                **item,
                "status": "queued",
                "queuedAt": now_iso,
                "queuedBy": source,
                "dispatchAttempts": int(item.get("dispatchAttempts") or 0) + 1,
                "error": "",
            }
            claimed.append(claimed_item)
            next_schedules.append(claimed_item)

        if not changed:
            return [], len(schedules)

        try:
            save_schedules(repo, token, next_schedules, sha, "Claim due note post schedules")
            return claimed, len(schedules)
        except ScheduleConflictError:
            if attempt == MAX_CLAIM_RETRIES:
                raise
            log(f"予約ファイル更新が競合しました。再試行します: attempt={attempt}")
            time.sleep(1.5 * attempt)

    return [], 0


def dispatch_note_post(repo: str, token: str, item: dict[str, Any]) -> tuple[bool, str]:
    inputs = {
        "file_id": str(item.get("fileId") or ""),
        "no_top_image": str(bool(item.get("noTopImage"))).lower(),
        "note_target": str(item.get("noteTarget") or "blog_main"),
        "publish_mode": "scheduled_due",
        "scheduled_at": str(item.get("publishAt") or ""),
        "schedule_id": str(item.get("id") or ""),
        "article_title": str(item.get("title") or item.get("name") or ""),
    }
    try:
        request_json(
            "POST",
            f"{api_base(repo)}/actions/workflows/{WORKFLOW_FILE}/dispatches",
            token,
            {"ref": "main", "inputs": inputs},
        )
        return True, ""
    except Exception as exc:
        return False, str(exc)[:500]


def mark_dispatch_failures(repo: str, token: str, failures: list[dict[str, str]]) -> None:
    if not failures:
        return
    failure_map = {item["id"]: item["error"] for item in failures}

    for attempt in range(1, MAX_CLAIM_RETRIES + 1):
        schedules, sha = load_schedules(repo, token)
        next_schedules = [
            {**item, "status": "error", "error": failure_map[item["id"]]}
            if item.get("id") in failure_map else item
            for item in schedules
        ]
        try:
            save_schedules(repo, token, next_schedules, sha, "Mark failed note post dispatches")
            return
        except ScheduleConflictError:
            if attempt == MAX_CLAIM_RETRIES:
                raise
            log(f"失敗状態の更新が競合しました。再試行します: attempt={attempt}")
            time.sleep(1.5 * attempt)


def run_once_from_env() -> int:
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or ""
    repo = os.environ.get("GITHUB_REPOSITORY") or os.environ.get("REPOSITORY") or "seahirodigital/Blog_Vercel"
    source = os.environ.get("NOTE_POST_SCHEDULE_SOURCE") or "github-schedule"
    queue_stale_minutes = env_int("NOTE_POST_QUEUE_STALE_MINUTES", DEFAULT_QUEUE_STALE_MINUTES)
    prestart_window_minutes = env_int("NOTE_POST_PRESTART_WINDOW_MINUTES", DEFAULT_PRESTART_WINDOW_MINUTES)
    late_grace_minutes = env_int("NOTE_POST_LATE_GRACE_MINUTES", DEFAULT_LATE_GRACE_MINUTES)

    if not token:
        print("GH_PAT または GITHUB_TOKEN が未設定です", file=sys.stderr)
        return 1

    checked_at = datetime.now(timezone.utc).isoformat()
    log(
        "note予約監視を開始します: "
        f"repo={repo}, source={source}, queueStaleMinutes={queue_stale_minutes}, "
        f"prestartWindowMinutes={prestart_window_minutes}, lateGraceMinutes={late_grace_minutes}, "
        f"checkedAt={checked_at}"
    )

    claimed, checked = claim_due_schedules(
        repo,
        token,
        source,
        queue_stale_minutes,
        prestart_window_minutes,
        late_grace_minutes,
    )
    dispatched: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []

    for item in claimed:
        log(f"投稿ジョブを起動します: scheduleId={item.get('id')}, fileId={item.get('fileId')}")
        ok, error = dispatch_note_post(repo, token, item)
        summary = {
            "id": str(item.get("id") or ""),
            "fileId": str(item.get("fileId") or ""),
            "title": str(item.get("title") or item.get("name") or ""),
        }
        if ok:
            log(f"投稿ジョブを起動しました: scheduleId={summary['id']}")
            dispatched.append(summary)
        else:
            log(f"投稿ジョブの起動に失敗しました: scheduleId={summary['id']}, error={error}")
            failures.append({**summary, "error": error})

    mark_dispatch_failures(repo, token, failures)

    print(json.dumps({
        "success": not failures,
        "checkedAt": checked_at,
        "repository": repo,
        "source": source,
        "queueStaleMinutes": queue_stale_minutes,
        "prestartWindowMinutes": prestart_window_minutes,
        "lateGraceMinutes": late_grace_minutes,
        "checked": checked,
        "claimed": len(claimed),
        "dispatched": dispatched,
        "failures": failures,
    }, ensure_ascii=False, indent=2))

    return 0 if not failures else 1


def count_pending_before_deadline(repo: str, token: str, deadline: datetime, late_grace_minutes: int) -> int:
    schedules, _ = load_schedules(repo, token)
    now = datetime.now(timezone.utc)
    late_grace_seconds = late_grace_minutes * 60
    pending = 0

    for item in schedules:
        if item.get("publishedAt"):
            continue
        if item.get("status") not in {"scheduled", "queued"}:
            continue

        publish_at = parse_publish_at(item)
        if publish_at is None:
            pending += 1
            continue
        if publish_at > deadline:
            continue
        if (now - publish_at).total_seconds() > late_grace_seconds:
            continue
        pending += 1

    return pending


def run_monitor_from_env() -> int:
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or ""
    repo = os.environ.get("GITHUB_REPOSITORY") or os.environ.get("REPOSITORY") or "seahirodigital/Blog_Vercel"
    duration_minutes = env_int("NOTE_POST_MONITOR_DURATION_MINUTES", 330)
    poll_seconds = env_int("NOTE_POST_MONITOR_POLL_SECONDS", 60)
    late_grace_minutes = env_int("NOTE_POST_LATE_GRACE_MINUTES", DEFAULT_LATE_GRACE_MINUTES)

    if not token:
        print("GH_PAT または GITHUB_TOKEN が未設定です", file=sys.stderr)
        return 1

    started_at = datetime.now(timezone.utc)
    deadline = started_at + timedelta(minutes=duration_minutes)
    cycle = 0
    final_code = 0
    summaries: list[dict[str, Any]] = []

    log(
        "note予約監視セッションを開始します: "
        f"repo={repo}, durationMinutes={duration_minutes}, pollSeconds={poll_seconds}, "
        f"startedAt={started_at.isoformat()}, deadline={deadline.isoformat()}"
    )

    while True:
        cycle += 1
        log(f"note予約監視サイクルを実行します: cycle={cycle}")
        code = run_once_from_env()
        final_code = final_code or code

        pending = count_pending_before_deadline(repo, token, deadline, late_grace_minutes)
        now = datetime.now(timezone.utc)
        summaries.append({
            "cycle": cycle,
            "exitCode": code,
            "pendingBeforeDeadline": pending,
            "checkedAt": now.isoformat(),
        })

        if pending <= 0:
            log("監視セッション内に残っている予約はありません。終了します。")
            break
        if now >= deadline:
            log("監視セッションの期限に到達しました。終了します。")
            break

        remaining_seconds = max(0, int((deadline - now).total_seconds()))
        sleep_seconds = min(poll_seconds, remaining_seconds)
        if sleep_seconds <= 0:
            break
        log(f"次の確認まで待機します: sleepSeconds={sleep_seconds}, pending={pending}")
        time.sleep(sleep_seconds)

    print(json.dumps({
        "success": final_code == 0,
        "monitor": True,
        "startedAt": started_at.isoformat(),
        "deadline": deadline.isoformat(),
        "cycles": summaries,
    }, ensure_ascii=False, indent=2))
    return final_code


def main() -> int:
    if env_bool("NOTE_POST_MONITOR_MODE"):
        return run_monitor_from_env()
    return run_once_from_env()


if __name__ == "__main__":
    raise SystemExit(main())
