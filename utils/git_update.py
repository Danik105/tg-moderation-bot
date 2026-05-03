"""
utils/git_update.py — git pull / restart утилиты.
"""
import logging
import os
import subprocess
import sys
from typing import List, Tuple

logger = logging.getLogger(__name__)


def _run_git(args: List[str], timeout: int = 30) -> Tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "⏱ Превышено время ожидания"
    except FileNotFoundError:
        return False, "❌ Git не установлен"
    except Exception as exc:
        return False, f"❌ Ошибка: {exc}"


def git_current_commit() -> str:
    ok, out = _run_git(["rev-parse", "--short", "HEAD"])
    return out if ok else "неизвестно"


def git_current_branch() -> str:
    ok, out = _run_git(["branch", "--show-current"])
    return out if ok else "main"


def git_check_updates() -> Tuple[bool, int, str]:
    ok, _ = _run_git(["fetch", "origin"], timeout=60)
    if not ok:
        return False, 0, "❌ Не удалось подключиться к репозиторию"
    branch = git_current_branch()
    ok, _ = _run_git(["rev-parse", "--verify", f"origin/{branch}"])
    if not ok:
        return True, 0, "✅ Удалённая ветка не найдена — обновления недоступны"
    ok, out = _run_git(["rev-list", "--count", f"HEAD..origin/{branch}"])
    count = int(out) if ok and out.isdigit() else 0
    if count == 0:
        return True, 0, "✅ Бот уже обновлён до последней версии"
    ok2, log = _run_git(["log", f"HEAD..origin/{branch}", "--format=%h %s", "-n", "10"])
    log_text = (
        f"📦 Доступно обновлений: {count}\n\nПоследние изменения:\n<pre>{log}</pre>"
        if ok2 else f"📦 Доступно обновлений: {count}"
    )
    return True, count, log_text


def git_pull() -> Tuple[bool, str]:
    ok, out = _run_git(["pull", "origin"], timeout=120)
    if not ok:
        return False, f"❌ Ошибка обновления:\n<pre>{out}</pre>"
    ok2, commit = _run_git(["log", "--format=%h %s", "-n", "1"])
    info = commit if ok2 else ""
    return True, f"✅ Обновление успешно!\n\n🔹 Последний коммит:\n<pre>{info}</pre>"


def git_restart() -> None:
    logger.info("[GIT] Перезапуск бота...")
    os.execv(sys.executable, [sys.executable] + sys.argv)
