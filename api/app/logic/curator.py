"""Curator access (design doc 9): three levels chosen by the student."""

from __future__ import annotations

from typing import Any, Literal

Access = Literal["fact", "progress", "full"]

MAX_CURATORS_PER_STUDENT = 2
MAX_STUDENTS_PER_CURATOR = 30
INVITE_TTL_HOURS = 48
NUDGES: dict[str, str] = {
    "start": "Сегодня отличный день, чтобы решить дейлики 🙂",
    "streak": "Серия ждёт — всего 15 минут!",
    "proud": "Вижу твой прогресс. Так держать!",
    "comeback": "Давно не виделись. Одна задача — и ты снова в деле.",
    "exam": "Попробуй сегодня половину пробного экзамена.",
    "focus": "Загляни в тему, которую мы выбрали на эту неделю.",
}
"""Six presets and no free text, so the bot never becomes a pressure channel (9.3)."""

FIELDS: dict[Access, frozenset[str]] = {
    "fact": frozenset({"streak", "threshold_today", "rank"}),
    "progress": frozenset(
        {"streak", "threshold_today", "rank", "coins_by_day", "confidence", "forecast", "exams"}
    ),
    "full": frozenset(
        {
            "streak",
            "threshold_today",
            "rank",
            "coins_by_day",
            "confidence",
            "forecast",
            "exams",
            "subtypes",
            "reasons",
            "attempts",
            "time_spent",
        }
    ),
}
DEFAULT_ACCESS: dict[str, Access] = {"parent": "progress", "tutor": "full"}


def visible(card: dict[str, Any], access: Access) -> dict[str, Any]:
    """Project a student card to exactly what the chosen access level allows.

    Free text from difficulty reasons and tickets is never included, whatever the
    level (14.3): it goes to moderation only.
    """
    allowed = FIELDS[access]
    return {k: v for k, v in card.items() if k in allowed or k in ("student_id", "name")}


def downgrade_ok(current: Access, new: Access) -> bool:
    order = ["fact", "progress", "full"]
    return order.index(new) <= order.index(current)


def risk_score(days_idle: int, confidence_drop: float, streak_broken: bool) -> float:
    """Dashboard sort key (9.3): idle days, falling confidence, a broken streak."""
    score = 0.0
    if days_idle >= 2:
        score += 1.0 + 0.2 * (days_idle - 2)
    score += max(0.0, confidence_drop) / 10.0
    if streak_broken:
        score += 1.0
    return round(score, 2)
