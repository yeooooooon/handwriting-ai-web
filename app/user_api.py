# app/user_api.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .db import get_db
from . import models, schemas
from .auth_api import get_current_user

router = APIRouter(prefix="/user", tags=["user"])

@router.post("/scores", response_model=schemas.ScoreOut)
def save_score(payload: schemas.ScoreCreate,
               db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    if payload.score < 0 or payload.score > 100:
        raise HTTPException(status_code=400, detail="점수 범위가 올바르지 않습니다.")
    row = models.Score(user_id=user.id, text=payload.text, score=payload.score)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

@router.get("/profile", response_model=schemas.ProfileOut)
def my_profile(db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    scores = (db.query(models.Score)
                .filter(models.Score.user_id == user.id)
                .order_by(models.Score.created_at.desc())
                .all())
    return {"user": user, "scores": scores}
