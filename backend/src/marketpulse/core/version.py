"""Çalışan kodun sürümü: git commit'i ve süreç başlangıcı.

Neden: aynı makinede eski bir `make dev` oturumu arka planda kalırsa kullanıcı onun arayüzüne
bakıp yeni sürümü çalışıyor sanabilir. Arayüz hangi commit'in çalıştığını gösterir.

Öncelik: `MP_GIT_SHA` ortam değişkeni (Docker imajında build sırasında gömülür) → `git rev-parse`
→ "bilinmiyor". Git çağrısı bir kez yapılır ve önbelleğe alınır.
"""

import os
import subprocess
from functools import lru_cache
from pathlib import Path

UNKNOWN = "bilinmiyor"
GIT_TIMEOUT_SEC = 3.0
REPO_ROOT = Path(__file__).resolve().parents[4]


@lru_cache(maxsize=1)
def git_sha() -> str:
    """Çalışan kodun kısa commit kimliği. Bulunamazsa `bilinmiyor`."""
    from_env = os.environ.get("MP_GIT_SHA", "").strip()
    if from_env:
        return from_env
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SEC,
            cwd=REPO_ROOT,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else UNKNOWN
