"""Typed payloads for desk units."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PathName = Literal["refund", "how_to", "bug"]


class Claim(BaseModel):
    statement: str
    span_id: str
    quote: str
    source: Literal["email", "policy"] | None = None
    question_id: str | None = None
    rule_id: str | None = None
    verdict: Literal["pass", "fail"] | None = None


class VerifiedClaim(BaseModel):
    claim: Claim
    status: Literal["grounded", "ungrounded"]
    reason: str | None = None
    decoy_match: str | None = None
    task: str


class PlaybookRule(BaseModel):
    id: str
    question: str
    expected: Literal["pass", "fail"]
    canonical_span_ids: list[str] = Field(default_factory=list)
    required_substrings: list[str] = Field(default_factory=list)


class ExtractQuestion(BaseModel):
    id: str
    question: str
    acceptable_span_ids: list[str] = Field(default_factory=list)
    required_substrings: list[str] = Field(default_factory=list)


class TicketAnswers(BaseModel):
    ticket_id: str
    path: PathName
    rules: list[PlaybookRule] = Field(default_factory=list)
    extract_questions: list[ExtractQuestion] = Field(default_factory=list)


class ClaimBatch(BaseModel):
    claims: list[Claim]


class PublicItem(BaseModel):
    id: str
    question: str
