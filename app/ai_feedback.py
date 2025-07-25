# ai_feedback.py
from openai import OpenAI
import os

# API 키 설정: 환경변수 또는 직접 키 지정
client = OpenAI(api_key="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")  # ← 여기에 본인 API 키 직접 작성 가능

def generate_ai_feedback(text: str, score_dict: dict) -> str:
    score_lines = "\n".join([f"'{k}': {v}점" for k, v in score_dict.items()])
    prompt = f"""
학생이 쓴 글자: "{text}"

각 글자의 유사도 점수:zz
{score_lines}

기준: 90점 이상 → 완벽, 70~89점 → 보통, 70점 미만 → 교정 필요

위 정보를 바탕으로 아래 조건을 만족하는 AI 피드백 문장을 생성해 주세요:
1. 따뜻하고 칭찬하는 말투
2. 잘한 점과 아쉬운 점 모두 언급
3. 너무 짧거나 너무 길지 않게, 자연스럽고 친절한 문장으로 구성
4. 교정이 필요한 글자는 어떤 점을 개선하면 좋을지도 알려주세요.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "당신은 친절한 손글씨 선생님입니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"AI 피드백 생성 오류: {str(e)}"
