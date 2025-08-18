# app/routers/game_drop_api.py
# -*- coding: utf-8 -*-
"""
드롭 미니게임(60초) 전용 리더보드 API
- 기존 리더보드와 완전히 분리된 파일 저장 방식
- 인증: Authorization: Bearer <token>  (auth_fs.py의 유틸 사용)
- 엔드포인트:
    GET  /game/drop/leaderboard  → 상위 점수 목록(+ 내 최고점)
    POST /game/drop/submit       → 점수 저장(로그인 필수)
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from pathlib import Path
from typing import Any, Dict, List, Optional
import json, os, time, threading

# 프로젝트의 auth 유틸 경로에 맞춰 import (app/routers/auth_fs.py 기준)
try:
    from app.routers.auth_fs import bearer_token_from_request, get_username_from_token
except Exception:
    # 만약 경로가 다르면 위 import를 주석 처리하고 아래 라인을 맞게 수정하세요.
    from .auth_fs import bearer_token_from_request, get_username_from_token

router = APIRouter()

# 데이터 저장 위치 (환경변수 DATA_DIR 없으면 프로젝트 루트의 data/)
DATA_DIR = Path(os.getenv("DATA_DIR", "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
LEADERBOARD_FILE = DATA_DIR / "drop_game_leaderboard.json"  # 기존 랭크와 분리

_LOCK = threading.Lock()

def _load() -> Dict[str, Any]:
    if LEADERBOARD_FILE.exists():
        try:
            return json.loads(LEADERBOARD_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"items": []}  # items: List[{username, score, hits, miss, duration_ms, at}]

def _save(obj: Dict[str, Any]) -> None:
    LEADERBOARD_FILE.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

class SubmitIn(BaseModel):
    score: int
    hits: int = 0
    miss: int = 0
    duration_ms: int = 60000

@router.get("/game/drop/leaderboard")
def leaderboard(req: Request):
    with _LOCK:
        data = _load()
        items = data.get("items", [])
        # 점수 내림차순, 동점은 최신 우선
        items_sorted = sorted(items, key=lambda x: (x.get("score", 0), x.get("at", 0)), reverse=True)

    # 내 최고점(로그인 시)
    me = None
    token = bearer_token_from_request(req)
    username = get_username_from_token(token or "") if token else ""
    if username:
        mine = [it for it in items_sorted if it.get("username") == username]
        if mine:
            best = sorted(mine, key=lambda x: (x.get("score", 0), x.get("at", 0)), reverse=True)[0]
            me = {"username": best["username"], "score": best["score"], "at": best["at"]}

    return {"items": items_sorted[:100], "me": me}

@router.post("/game/drop/submit")
def submit_score(req: Request, body: SubmitIn):
    token = bearer_token_from_request(req)
    username = get_username_from_token(token or "")
    if not username:
        raise HTTPException(status_code=401, detail="인증 필요")

    rec = {
        "username": username,
        "score": int(body.score),
        "hits": int(body.hits),
        "miss": int(body.miss),
        "duration_ms": int(body.duration_ms),
        "at": int(time.time())  # epoch seconds
    }

    with _LOCK:
        data = _load()
        data.setdefault("items", []).append(rec)
        # 파일 크기 무한 증가 방지: 상위 1000개만 유지
        data["items"] = sorted(
            data["items"], key=lambda x: (x.get("score", 0), x.get("at", 0)), reverse=True
        )[:1000]
        _save(data)

    return {"ok": True, "saved": rec}
