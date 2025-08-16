# app/routers/gpt_handwriting_feedback_api.py
# -*- coding: utf-8 -*-
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse
from PIL import Image
import base64, io, json, os, datetime
import time
from app.routers.auth_fs import (
    bearer_token_from_request,
    get_username_from_token,
    append_user_score,
)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from openai import OpenAI

# ⬇ 추가: 파일 기반 세션/저장 유틸 재사용
from app.routers.auth_fs import (
    bearer_token_from_request,
    get_username_from_token,
    append_user_score,
)

router = APIRouter()
MAX_CHAR_LIMIT = 20

def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
    return OpenAI(api_key=api_key)

def _gpt_scoring_prompt():
    return (
        "너는 한글 손글씨 채점관이다.\n"
        "입력: 손글씨 이미지 1장.\n"
        "해야 할 일:\n"
        "1) 이미지 속 한글 문장을 정확히 읽어 'recognized_text' 로 반환(공백/줄바꿈 보존)\n"
        "2) 앞에서부터 최대 20글자에 대해 각 글자별 0~100 점수(가독성/안정/균형)를 'char_scores' 로 반환\n"
        "3) 전체 평균 점수(0~100, 소수 허용)를 'overall_score' 로 반환\n"
        "4) 'feedback'에는 글자별로 어떤 부분을 어떻게 고치면 좋을지 구체 팁 + 전체 개선 1~2가지\n"
        "출력은 아래 JSON만, 추가 텍스트 금지.\n"
        "{\n"
        "  \"recognized_text\": \"...\",\n"
        "  \"char_scores\": [ {\"char\":\"첫글자\",\"score\":0}, {\"char\":\"둘째글자\",\"score\":0} ],\n"
        "  \"overall_score\": 0,\n"
        "  \"feedback\": \"...\"\n"
        "}\n"
        "주의: char_scores는 실제 읽힌 순서, 최대 20개."
    )

def _call_gpt_vision_and_score(image_bytes: bytes) -> dict:
    client = _get_client()
    data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("utf-8")
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": "You are a strict JSON generator."},
            {"role": "user",
             "content": [
                 {"type": "text", "text": _gpt_scoring_prompt()},
                 {"type": "image_url", "image_url": {"url": data_url}},
             ]}
        ],
    )
    content = resp.choices[0].message.content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:].strip()
    try:
        data = json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 응답 파싱 실패: {e}")

    for key in ("recognized_text", "char_scores", "overall_score", "feedback"):
        if key not in data:
            raise HTTPException(status_code=500, detail=f"AI 응답에 '{key}' 없음")

    if isinstance(data.get("char_scores"), list):
        data["char_scores"] = data["char_scores"][:MAX_CHAR_LIMIT]

    return data

@router.post("/evaluate")
async def evaluate_handwriting(request: Request, file: UploadFile = File(...)):
    if file.content_type not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(status_code=400, detail="이미지 파일(png/jpeg/webp)만 업로드 가능합니다.")
    try:
        raw = await file.read()
        Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="유효한 이미지가 아닙니다.")

    gpt = _call_gpt_vision_and_score(raw)

    recognized_text = gpt.get("recognized_text") or ""
    char_scores_list = gpt.get("char_scores") or []
    try:
        overall_score = float(gpt.get("overall_score", 0.0))
    except Exception:
        overall_score = 0.0

    # 리스트 그대로 보존(중복 글자 유지) + map은 호환용
    char_scores_seq = []
    score_map = {}
    for item in char_scores_list[:MAX_CHAR_LIMIT]:
        ch = str(item.get("char", "") or "")
        try:
            sc = int(round(float(item.get("score", 0))))
        except Exception:
            sc = 0
        char_scores_seq.append({"char": ch, "score": sc})
        if ch and ch not in score_map:
            score_map[ch] = sc

    if (overall_score <= 0.0) and char_scores_seq:
        overall_score = sum(i["score"] for i in char_scores_seq) / len(char_scores_seq)
    avg_score = max(0.0, min(100.0, overall_score))

    # ⬇ 로그인 상태면 점수 저장
    try:
        token = bearer_token_from_request(request)
        username = get_username_from_token(token or "")
        if username:
            append_user_score(username, {
                "ts": int(time.time()),
                "score": round(avg_score, 2),
                "source": "gpt",
                "text": (recognized_text or "")[:100]
            })
    except Exception:
        # 저장 실패는 채점 결과 반환에 영향 주지 않음
        pass

    return JSONResponse(content={
        "match": True,
        "recognized_text": recognized_text,
        "corrected_text": recognized_text,
        "score": round(avg_score, 2),
        "feedback": gpt.get("feedback", ""),
        "char_scores": score_map,
        "char_scores_seq": char_scores_seq,
        "engine": "gpt-4o-mini"
    })
