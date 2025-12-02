# app/routers/gpt_handwriting_feedback_api.py
# -*- coding: utf-8 -*-
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse
from PIL import Image
import base64, io, json, os, datetime
import time
from urllib.parse import urlparse

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
        "4) 'feedback'에는 다음 내용을 포함해야 한다:\n"
        "   - 글자별로 어떤 부분을 어떻게 고치면 좋을지 구체적인 팁\n"
        "   - 전체 개선 1~2가지\n"
        "   - 폰트 유사도 정보 (예: '굴림: 80%, 돋움: 50%, 고딕: 20%, 궁서: 10%')를 명시적으로 언급.\n" # ⬅ 이 부분이 핵심
        "출력은 아래 JSON만, 추가 텍스트 금지.\n"
        "{\n"
        "  \"recognized_text\": \"...\",\n"
        "  \"char_scores\": [ {\"char\":\"첫글자\",\"score\":0}, {\"char\":\"둘째글자\",\"score\":0} ],\n"
        "  \"overall_score\": 0,\n"
        "  \"feedback\": \"...\"\n"
        "  \"font_similarity\": {\n"
        "  \n"
        "    \"굴림\": 0, \"돋움\": 0, \"고딕\": 0, \"궁서\": 0 \n"
        "  }\n"
        "}\n"
        "주의: char_scores는 실제 읽힌 순서, 최대 20개, font_similarity 값은 0~100 정수."
    )

def _call_gpt_vision_and_score(image_bytes: bytes) -> dict:
    client = _get_client()
    data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("utf-8")
    resp = client.chat.completions.create(
        model="gpt-4o",
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
        # 첫 번째 여는 중괄호 '{' 위치를 찾습니다.
        start_index = content.find('{')
        if start_index != -1:
            # '{' 이후부터의 문자열만 사용합니다.
            content = content[start_index:]
        else:
            # '{'가 아예 없으면 유효한 JSON이 아니므로 오류 발생
            raise ValueError("GPT 응답에서 JSON 시작 문자 '{'를 찾을 수 없습니다.")
    except Exception as e:
        # JSON 시작점 찾기 실패 시 오류 처리
        raise HTTPException(status_code=500, detail=f"AI 응답 전처리 실패: {e}")
        
    try:
        data = json.loads(content)
    except Exception as e:
        # 파싱 실패 시, 디버깅을 위해 AI가 보낸 원본 content를 로그에 남기는 것이 좋습니다.
        # 예: print(f"Raw GPT Content: {content}")
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

    # ⬇ 폰트 유사도 추출 및 처리
    font_similarity = gpt.get("font_similarity") or {}
    font_similarity_list = []
    for key in font_similarity:
        try:
            # 0~100 정수형으로 변환
            score = int(round(float(font_similarity[key]))) 
            font_similarity[key] = score
            font_similarity_list.append(f"{key}: {score}%") # 리스트 생성
        except Exception:
            font_similarity[key] = 0

    # ⬇ 핵심 수정: feedback 텍스트에 폰트 유사도 정보 강제 추가
    original_feedback = gpt.get("feedback", "")
    
    if font_similarity_list:
        # 유사도 정보를 보기 좋게 문자열로 만듭니다. (예: 굴림: 80%, 돋움: 50% ...)
        similarity_text = "유사도 정보: " + ", ".join(font_similarity_list)
        
        # 기존 피드백 텍스트에 폰트 유사도 정보를 삽입합니다.
        # 기존 피드백이 이미 유사도 정보를 포함하고 있는지 간단히 체크한 후 추가합니다.
        if "유사도 정보" not in original_feedback and "폰트 유사도" not in original_feedback:
            # 기존 피드백이 없으면 유사도 정보만 넣고, 있으면 줄바꿈 후 추가
            if original_feedback.strip():
                final_feedback = f"{original_feedback}\n\n---추정 폰트 분석---\n{similarity_text}"
            else:
                final_feedback = similarity_text
        else:
            # 이미 포함된 것 같으면 원본 그대로 사용
            final_feedback = original_feedback
    else:
        final_feedback = original_feedback

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

        # Referer가 /daily 로 시작할 때만 저장
        allow_save = False
        try:
            ref = request.headers.get("referer") or request.headers.get("Referer") or ""
            path = urlparse(ref).path if ref else ""
            allow_save = path.startswith("/daily")
        except Exception:
            allow_save = False

        if username and allow_save:
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
        # "feedback": gpt.get("feedback", ""),
        "feedback": final_feedback, # ⬅ 수정된 feedback을 사용합니다.
        "char_scores": score_map,
        "char_scores_seq": char_scores_seq,
        "font_similarity": font_similarity, # ⬅ 추가
        "engine": "gpt-4o"
    })
