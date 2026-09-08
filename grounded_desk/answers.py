from __future__ import annotations

import yaml

from grounded_desk.models import PublicItem, TicketAnswers
from grounded_desk.paths import ANSWERS


def load_answers(ticket_id: str) -> TicketAnswers:
    path = ANSWERS / f"{ticket_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no answer key for ticket {ticket_id}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return TicketAnswers.model_validate(data)


def public_items(ticket_id: str, task: str) -> list[PublicItem]:
    """Questions only. No expected verdicts, spans, or substrings."""
    answers = load_answers(ticket_id)
    if task == "extract":
        return [PublicItem(id=q.id, question=q.question) for q in answers.extract_questions]
    if task == "playbook":
        return [PublicItem(id=r.id, question=r.question) for r in answers.rules]
    raise ValueError(f"no public items for {task}")
