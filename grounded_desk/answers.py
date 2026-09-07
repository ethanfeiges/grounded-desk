from __future__ import annotations

import yaml

from grounded_desk.models import TicketAnswers
from grounded_desk.paths import ANSWERS


def load_answers(ticket_id: str) -> TicketAnswers:
    path = ANSWERS / f"{ticket_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no answer key for ticket {ticket_id}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return TicketAnswers.model_validate(data)
