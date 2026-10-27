"""Pydantic I/O for writing samples."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import WritingSampleCategory, WritingSampleOrigin


class WritingSampleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    title: str
    body: str
    category: WritingSampleCategory
    origin: WritingSampleOrigin
    is_approved_style_reference: bool
    source_answer_id: int | None
    created_at: datetime
    updated_at: datetime


class WritingSampleCreate(BaseModel):
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=4000)
    category: WritingSampleCategory = WritingSampleCategory.GENERAL
    origin: WritingSampleOrigin = WritingSampleOrigin.USER_WRITTEN
    is_approved_style_reference: bool = False
    source_answer_id: int | None = None


class WritingSampleUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=4000)
    category: WritingSampleCategory | None = None
    is_approved_style_reference: bool | None = None
