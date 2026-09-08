from __future__ import annotations

from grounded_desk.models import ExtractQuestion, PlaybookRule, TicketAnswers, VerifiedClaim


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def score_playbook(verified: VerifiedClaim, rule: PlaybookRule) -> bool:
    if verified.status != "grounded":
        return False
    claim = verified.claim
    if claim.rule_id not in (None, rule.id):
        return False
    if claim.verdict != rule.expected:
        return False
    if rule.canonical_span_ids and claim.span_id not in rule.canonical_span_ids:
        return False
    for needle in rule.required_substrings:
        if _norm(needle) not in _norm(claim.quote):
            return False
    return True


def score_extract(verified: VerifiedClaim, question: ExtractQuestion) -> bool:
    if verified.status != "grounded":
        return False
    claim = verified.claim
    if claim.span_id not in question.acceptable_span_ids:
        return False
    for needle in question.required_substrings:
        if _norm(needle) not in _norm(claim.quote):
            return False
    return True


def task_scores(
    verified: list[VerifiedClaim], answers: TicketAnswers
) -> dict[str, bool]:
    scores: dict[str, bool] = {}
    playbook = [v for v in verified if v.task == "playbook"]
    extract = [v for v in verified if v.task == "extract"]

    for rule in answers.rules:
        pool = [v for v in playbook if v.claim.rule_id in (None, rule.id)]
        scores[f"playbook:{rule.id}"] = any(score_playbook(v, rule) for v in pool)

    for question in answers.extract_questions:
        pool = [
            v
            for v in extract
            if v.claim.question_id in (None, question.id)
        ]
        scores[f"extract:{question.id}"] = any(
            score_extract(v, question) for v in pool
        )
    return scores
