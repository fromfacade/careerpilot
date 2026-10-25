from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    """Liveness + DB connectivity check. Used by README setup verification and uptime checks."""
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised via integration test with DB down
        db_status = f"error: {exc.__class__.__name__}"

    return {"status": "ok", "database": db_status}
