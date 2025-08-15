# app/ai_feedback.py
from typing import Dict

def generate_ai_feedback(recognized_text: str, score_dict: Dict[str, int]) -> str:
    """
    기존 프로젝트에 이미 있다면 이 파일은 그대로 사용하세요.
    없을 경우, 아래 최소 구현을 임시로 사용해도 됩니다.
    """
    if not score_dict:
        return "평가할 글자가 없습니다."

    low = [ch for ch, sc in score_dict.items() if sc < 70]
    mid = [ch for ch, sc in score_dict.items() if 70 <= sc < 90]
    high = [ch for ch, sc in score_dict.items() if sc >= 90]

    parts = []
    if high:
        parts.append(f"우수: {', '.join(repr(c) for c in high)}")
    if mid:
        parts.append(f"보통: {', '.join(repr(c) for c in mid)}")
    if low:
        parts.append(f"개선 필요: {', '.join(repr(c) for c in low)}")

    tips = []
    if low:
        tips.append("획의 시작/끝 밀착과 균형을 의식해 천천히 써보세요.")
    if mid:
        tips.append("자간/행간을 일정하게 유지하면 전체 인상이 좋아집니다.")
    if not tips:
        tips.append("현재 필체를 유지하며 안정적으로 연습해 보세요.")

    return " / ".join(parts) + "<br>" + " ".join(tips)
