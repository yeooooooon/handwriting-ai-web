# app/routers/auth_fs.py
# -*- coding: utf-8 -*-
"""
DB 없이 파일(JSON)로 아주 단순하게:
- /auth/register: 회원가입(아이디/비번 평문 저장)   ※ 보안 고려 안 함(요구사항)
- /auth/login   : 로그인 → 랜덤 토큰 발급(세션 파일에 저장)
- /auth/me      : 토큰 검증 후 사용자 조회
- /auth/scores  : 내 점수 목록 조회
유틸 함수(get_username_from_token, append_user_score 등)를 외부 라우터에서 재사용.
"""
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from pathlib import Path
import os, json, time, secrets, threading
from typing import Optional, Dict, Any, List
# 맨 위 import에 추가
from datetime import datetime, timezone


try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

router = APIRouter()

# ─────────────────────────────────────────────────────
# 파일 경로/락
# ─────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parents[1]  # app/ 까지
DATA_DIR = BASE_DIR / "data"
USERS_FILE = DATA_DIR / "users.json"
SESS_FILE  = DATA_DIR / "sessions.json"
SCORES_DIR = DATA_DIR / "scores"
_lock = threading.Lock()

def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        USERS_FILE.write_text("{}", encoding="utf-8")
    if not SESS_FILE.exists():
        SESS_FILE.write_text("{}", encoding="utf-8")

def _load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except:
        return default

def _save_json(p: Path, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

_ensure_dirs()

# ─────────────────────────────────────────────────────
# 모델
# ─────────────────────────────────────────────────────
class RegisterIn(BaseModel):
    username: str
    password: str

class LoginIn(BaseModel):
    username: str
    password: str

# ─────────────────────────────────────────────────────
# 세션/토큰 유틸
# ─────────────────────────────────────────────────────
SESSION_TTL_SEC = int(os.getenv("SESSION_TTL_SEC", "604800"))  # 기본 7일

def _now() -> int:
    return int(time.time())

def _new_token() -> str:
    return secrets.token_urlsafe(32)

def get_username_from_token(token: str) -> Optional[str]:
    """토큰 → 유저명 (만료되었으면 제거)"""
    if not token:
        return None
    with _lock:
        sess = _load_json(SESS_FILE, {})
        item = sess.get(token)
        if not item:
            return None
        if item.get("exp", 0) < _now():
            # 만료 → 세션 제거
            sess.pop(token, None)
            _save_json(SESS_FILE, sess)
            return None
        return item.get("username")

def bearer_token_from_request(req: Request) -> Optional[str]:
    auth = req.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        return None
    return auth.split(" ", 1)[1].strip() or None

def append_user_score(username: str, entry: Dict[str, Any]) -> None:
    """사용자 점수 파일에 한 줄 append"""
    if not username:
        return
    with _lock:
        f = SCORES_DIR / f"{username}.json"
        arr = _load_json(f, [])
        arr.append(entry)
        _save_json(f, arr)

def _to_epoch(v) -> int:
    """int/float/str(숫자/ISO-8601 '...Z')를 epoch(sec)로 안전 변환"""
    try:
        # 이미 숫자
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str):
            s = v.strip()
            # 숫자 문자열
            if s.isdigit():
                return int(s)
            # ISO-8601 문자열 처리 (Z -> +00:00)
            s = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
    except Exception:
        pass
    return 0

# ─────────────────────────────────────────────────────
# 라우트: 회원가입/로그인/조회
# ─────────────────────────────────────────────────────
@router.post("/register")
def register(data: RegisterIn):
    if not data.username or not data.password:
        raise HTTPException(400, "username/password 필요")
    with _lock:
        users = _load_json(USERS_FILE, {})
        if data.username in users:
            raise HTTPException(409, "이미 존재하는 아이디")
        # 요구사항: 보안 불필요 → 평문 저장(데모)
        users[data.username] = {"password": data.password}
        _save_json(USERS_FILE, users)
    return {"ok": True, "username": data.username}

@router.post("/login")
def login(data: LoginIn):
    with _lock:
        users = _load_json(USERS_FILE, {})
        u = users.get(data.username)
        if not u or u.get("password") != data.password:
            raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다")
        token = _new_token()
        sess = _load_json(SESS_FILE, {})
        sess[token] = {"username": data.username, "exp": _now() + SESSION_TTL_SEC}
        _save_json(SESS_FILE, sess)
    return {"ok": True, "token": token, "username": data.username, "exp_in_sec": SESSION_TTL_SEC}

@router.get("/me")
def me(req: Request):
    token = bearer_token_from_request(req)
    username = get_username_from_token(token or "")
    if not username:
        raise HTTPException(401, "인증 필요")
    return {"username": username}

@router.get("/scores")
def my_scores(req: Request):
    token = bearer_token_from_request(req)
    username = get_username_from_token(token or "")
    if not username:
        raise HTTPException(401, "인증 필요")
    f = SCORES_DIR / f"{username}.json"
    arr = _load_json(f, [])
    # ▼ ts를 epoch(sec)로 통일
    for e in arr:
        try:
            e["ts"] = _to_epoch(e.get("ts", 0))
        except Exception:
            e["ts"] = 0
    return arr

@router.get("/leaderboard")
def leaderboard(limit: int = 50):
    rows = []
    for f in SCORES_DIR.glob("*.json"):
        username = f.stem
        arr = _load_json(f, [])
        if not arr:
            continue
        best = max((float(e.get("score", 0)) for e in arr), default=0.0)
        count = len(arr)
        # ▼ 혼합 포맷 안전 처리
        last_ts = max((_to_epoch(e.get("ts", 0)) for e in arr), default=0)
        rows.append({
            "username": username,
            "best_score": round(best, 2),
            "count": count,
            "last_ts": last_ts,
        })
    rows.sort(key=lambda x: x["best_score"], reverse=True)
    return rows[:limit]