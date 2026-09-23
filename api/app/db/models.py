"""Data model — design doc section 13, extended where the product needs it.

Every entity from section 13 is here; the additions (refresh tokens, one-time web
login tokens, curator invites, nudges, config overrides, audit log, placement)
carry their reason in the class docstring.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow

TZ = DateTime(timezone=True)


def user_fk() -> ForeignKey:
    """A fresh FK to ``users`` — a ForeignKey object cannot be shared by columns."""
    return ForeignKey("users.id", ondelete="CASCADE")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    username: Mapped[str | None] = mapped_column(String(64))
    tz: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    locale: Mapped[str] = mapped_column(String(8), default="ru")
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    #: Bit flags: 1 = admin. Curator is a property of a link, not an account (12.3).
    role_flags: Mapped[int] = mapped_column(Integer, default=0)
    delete_requested_at: Mapped[datetime | None] = mapped_column(TZ)

    @property
    def is_admin(self) -> bool:
        return bool(self.role_flags & 1)


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    band: Mapped[str] = mapped_column(String(1), default="B")
    #: «Не знаю — подскажем после 5 задач» (11.2): band B until we suggest one.
    band_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    python_level: Mapped[str] = mapped_column(String(8), default="little")
    daily_time: Mapped[time] = mapped_column(Time, default=time(16, 0))
    notifications: Mapped[dict[str, bool]] = mapped_column(JSONB, default=dict)
    privacy_defaults: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    vacation_days: Mapped[list[str]] = mapped_column(JSONB, default=list)
    easy_days: Mapped[list[str]] = mapped_column(JSONB, default=list)
    onboarding_step: Mapped[int] = mapped_column(Integer, default=0)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime | None] = mapped_column(TZ)
    placement_done: Mapped[bool] = mapped_column(Boolean, default=False)
    python_track_done: Mapped[bool] = mapped_column(Boolean, default=False)
    challenge_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    run_code_on_server: Mapped[bool] = mapped_column(Boolean, default=False)
    show_timer: Mapped[bool] = mapped_column(Boolean, default=False)
    cosmetics: Mapped[list[str]] = mapped_column(JSONB, default=list)

    __table_args__ = (CheckConstraint("band in ('A','B','C')", name="band"),)


class TaskType(Base):
    __tablename__ = "task_types"

    no: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    level: Mapped[str] = mapped_column(String(2))
    points: Mapped[int] = mapped_column(Integer)
    target_seconds: Mapped[int] = mapped_column(Integer)
    requires_software: Mapped[bool] = mapped_column(Boolean)


class Subtype(Base):
    __tablename__ = "subtypes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_no: Mapped[int] = mapped_column(ForeignKey("task_types.no"))
    code: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(256))
    exam_like_share: Mapped[float] = mapped_column(Float, default=1.0)
    default_difficulty: Mapped[int] = mapped_column(Integer, default=3)
    target_seconds: Mapped[int] = mapped_column(Integer, default=180)
    requires_code: Mapped[bool] = mapped_column(Boolean, default=False)
    #: New generators run only in the "challenge" slot for three days (16.5).
    beta: Mapped[bool] = mapped_column(Boolean, default=False)
    beta_until: Mapped[date | None] = mapped_column(Date)


class GeneratorVersion(Base):
    __tablename__ = "generator_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_no: Mapped[int] = mapped_column(ForeignKey("task_types.no"))
    version: Mapped[str] = mapped_column(String(32))
    released_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    changelog: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (UniqueConstraint("task_no", "version", name="task_version"),)


class Floor(Base):
    __tablename__ = "floors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(128))
    task_nos: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    unlock_cost: Mapped[int] = mapped_column(Integer)
    season_id: Mapped[str] = mapped_column(String(32))


class UserFloor(Base):
    __tablename__ = "user_floors"

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    floor_id: Mapped[int] = mapped_column(ForeignKey("floors.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), default="unlocked")
    unlocked_by: Mapped[str] = mapped_column(String(16), default="coins")
    at: Mapped[datetime] = mapped_column(TZ, default=utcnow)

    __table_args__ = (
        CheckConstraint("state in ('locked','unlocked','boss_passed')", name="state"),
        CheckConstraint(
            "unlocked_by in ('coins','extern','placement','default','boss')", name="unlocked_by"
        ),
    )


class Instance(Base):
    """One generated task given to one user (12.4 lifecycle)."""

    __tablename__ = "instances"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    task_no: Mapped[int] = mapped_column(Integer)
    subtype_id: Mapped[str] = mapped_column(String(64))
    difficulty: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int] = mapped_column(BigInteger)
    hidden_seed: Mapped[int] = mapped_column(BigInteger)
    gen_version: Mapped[str] = mapped_column(String(32))
    context: Mapped[str] = mapped_column(String(16))
    slot: Mapped[str] = mapped_column(String(16), default="practice")
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    statement_md: Mapped[str] = mapped_column(Text)
    assets: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    #: Server-only. Never serialised to a client (decision D‑021).
    answer: Mapped[str] = mapped_column(Text)
    answer_hash: Mapped[str] = mapped_column(String(64))
    answer_kind: Mapped[str] = mapped_column(String(16))
    checker: Mapped[str] = mapped_column(String(32))
    checker_options: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    solution_steps: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reference_code: Mapped[str | None] = mapped_column(Text)
    method_card_id: Mapped[str] = mapped_column(String(64))
    target_seconds: Mapped[int] = mapped_column(Integer)
    exam_like: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_code: Mapped[bool] = mapped_column(Boolean, default=False)
    flags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    state: Mapped[str] = mapped_column(String(16), default="planned")
    planned_for: Mapped[date | None] = mapped_column(Date)
    issued_at: Mapped[datetime | None] = mapped_column(TZ)
    expires_at: Mapped[datetime | None] = mapped_column(TZ)
    solved_at: Mapped[datetime | None] = mapped_column(TZ)
    attempts_count: Mapped[int] = mapped_column(Integer, default=0)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    revealed: Mapped[bool] = mapped_column(Boolean, default=False)
    code_run_seen: Mapped[bool] = mapped_column(Boolean, default=False)
    last_code: Mapped[str | None] = mapped_column(Text)
    draft: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    exam_id: Mapped[int | None] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"))
    void: Mapped[bool] = mapped_column(Boolean, default=False)
    """Annulled after a confirmed generator error (5.5): excluded from every metric."""
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)

    __table_args__ = (
        Index("ix_instances_user_planned", "user_id", "planned_for"),
        CheckConstraint(
            "state in ('planned','issued','attempted','solved','failed','revealed','expired')",
            name="state",
        ),
    )


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("instances.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(user_fk())
    no: Mapped[int] = mapped_column(Integer)
    answer_raw: Mapped[str] = mapped_column(String(4000))
    is_correct: Mapped[bool] = mapped_column(Boolean)
    time_spent_s: Mapped[int] = mapped_column(Integer, default=0)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    code_snapshot: Mapped[str | None] = mapped_column(Text)
    verify_status: Mapped[str] = mapped_column(String(16), default="n/a")
    coins: Mapped[int] = mapped_column(Integer, default=0)
    method_check: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)

    __table_args__ = (
        Index("ix_attempts_user_created", "user_id", "created_at"),
        UniqueConstraint("instance_id", "no", name="instance_no"),
        CheckConstraint(
            "verify_status in ('n/a','pending','ok','mismatch','error','no_code')",
            name="verify_status",
        ),
    )


class DifficultyFeedback(Base):
    __tablename__ = "difficulty_feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"))
    instance_id: Mapped[int] = mapped_column(ForeignKey("instances.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(user_fk())
    reason_code: Mapped[str] = mapped_column(String(16))
    free_text: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)

    __table_args__ = (UniqueConstraint("instance_id", "user_id", name="instance_user"),)


class SkillStateRow(Base):
    __tablename__ = "skill_state"

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    subtype_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_no: Mapped[int] = mapped_column(Integer)
    rating: Mapped[float] = mapped_column(Float, default=1000.0)
    attempts_n: Mapped[int] = mapped_column(Integer, default=0)
    correct_recent: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    time_ratios: Mapped[list[float]] = mapped_column(ARRAY(Float), default=list)
    reasons: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    exam_results: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    last_practiced: Mapped[date | None] = mapped_column(Date)
    review_step: Mapped[int] = mapped_column(Integer, default=0)
    next_review: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (Index("ix_skill_state_user_review", "user_id", "next_review"),)


class DailyPlan(Base):
    __tablename__ = "daily_plans"

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    generated_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)


class DailyStats(Base):
    __tablename__ = "daily_stats"

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    coins_earned: Mapped[int] = mapped_column(Integer, default=0)
    coins_capped: Mapped[int] = mapped_column(Integer, default=0)
    tasks_done: Mapped[int] = mapped_column(Integer, default=0)
    threshold_met: Mapped[bool] = mapped_column(Boolean, default=False)
    easy_day: Mapped[bool] = mapped_column(Boolean, default=False)
    vacation: Mapped[bool] = mapped_column(Boolean, default=False)
    time_spent_s: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    feedback_bonuses: Mapped[int] = mapped_column(Integer, default=0)
    free_reveals_used: Mapped[int] = mapped_column(Integer, default=0)
    similar_counts: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)


class Streak(Base):
    __tablename__ = "streaks"

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    current: Mapped[int] = mapped_column(Integer, default=0)
    best: Mapped[int] = mapped_column(Integer, default=0)
    freezes: Mapped[int] = mapped_column(Integer, default=0)
    last_met_date: Mapped[date | None] = mapped_column(Date)
    accounted_until: Mapped[date | None] = mapped_column(Date)
    lost_on: Mapped[date | None] = mapped_column(Date)
    lost_value: Mapped[int] = mapped_column(Integer, default=0)
    restores_month: Mapped[str] = mapped_column(String(7), default="")
    recovered_this_month: Mapped[int] = mapped_column(Integer, default=0)
    frozen_days: Mapped[list[str]] = mapped_column(JSONB, default=list)


class Wallet(Base):
    __tablename__ = "wallet"

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[str] = mapped_column(String(16), default="Байт")
    exam_tickets: Mapped[int] = mapped_column(Integer, default=0)
    free_exam_month: Mapped[str] = mapped_column(String(7), default="")

    __table_args__ = (CheckConstraint("balance >= 0", name="balance_non_negative"),)


class Transaction(Base):
    """Every coin movement, with its reason and a link to what caused it (5.6)."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(32))
    ref_type: Mapped[str] = mapped_column(String(16), default="")
    ref_id: Mapped[str] = mapped_column(String(64), default="")
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    balance_after: Mapped[int] = mapped_column(Integer)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow, index=True)


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    training: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    deadline_at: Mapped[datetime | None] = mapped_column(TZ)
    finished_at: Mapped[datetime | None] = mapped_column(TZ)
    primary_score: Mapped[int | None] = mapped_column(Integer)
    test_score: Mapped[int | None] = mapped_column(Integer)
    per_task: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    paid_with: Mapped[str] = mapped_column(String(16), default="coins")
    #: Pause bookkeeping for the training mode, the block topic, the comparison chart.
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    __table_args__ = (CheckConstraint("kind in ('full','half','block')", name="kind"),)


class ExamAnswer(Base):
    """One answer slot. Keyed by position: a "block" holds five of the same task."""

    __tablename__ = "exam_answers"

    exam_id: Mapped[int] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_no: Mapped[int] = mapped_column(Integer)
    instance_id: Mapped[int] = mapped_column(ForeignKey("instances.id", ondelete="CASCADE"))
    answer_raw: Mapped[str | None] = mapped_column(String(4000))
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    points: Mapped[int] = mapped_column(Integer, default=0)
    time_spent_s: Mapped[int] = mapped_column(Integer, default=0)


class CuratorLink(Base):
    __tablename__ = "curator_links"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(user_fk())
    curator_id: Mapped[int] = mapped_column(user_fk())
    status: Mapped[str] = mapped_column(String(16), default="pending")
    access: Mapped[str] = mapped_column(String(16), default="progress")
    role: Mapped[str] = mapped_column(String(16), default="parent")
    invited_by: Mapped[int] = mapped_column(BigInteger)
    league_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_digest_time: Mapped[time | None] = mapped_column(Time)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)

    __table_args__ = (
        Index("ix_curator_links_curator_status", "curator_id", "status"),
        CheckConstraint("status in ('pending','active','revoked')", name="status"),
        CheckConstraint("access in ('fact','progress','full')", name="access"),
        CheckConstraint("role in ('parent','tutor')", name="role"),
    )


class CuratorInvite(Base):
    """Deep-link token ``cur_<token>`` living 48 hours (9.1)."""

    __tablename__ = "curator_invites"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_id: Mapped[int] = mapped_column(user_fk())
    role: Mapped[str] = mapped_column(String(16), default="parent")
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TZ)
    used_by: Mapped[int | None] = mapped_column(BigInteger)


class CuratorFocus(Base):
    __tablename__ = "curator_focus"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("curator_links.id", ondelete="CASCADE"))
    task_nos: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    week_start: Mapped[date] = mapped_column(Date)


class Nudge(Base):
    __tablename__ = "nudges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("curator_links.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(16))
    sent_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    scheduled_at: Mapped[datetime] = mapped_column(TZ)
    sent_at: Mapped[datetime | None] = mapped_column(TZ)
    opened_at: Mapped[datetime | None] = mapped_column(TZ)
    status: Mapped[str] = mapped_column(String(16), default="scheduled")
    #: One notification of a kind per user per day: sending is idempotent.
    dedupe_key: Mapped[str] = mapped_column(String(128), unique=True)


class IssueReport(Base):
    __tablename__ = "issue_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("instances.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(user_fk())
    text: Mapped[str] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(16), default="open")
    resolution: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(TZ)


class TheoryCard(Base):
    __tablename__ = "theory_cards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_no: Mapped[int] = mapped_column(Integer, index=True)
    subtype_id: Mapped[str | None] = mapped_column(String(64))
    body_md: Mapped[str] = mapped_column(Text)
    code_templates: Mapped[list[str]] = mapped_column(JSONB, default=list)
    version: Mapped[str] = mapped_column(String(32), default="1")


class Event(Base):
    """Product analytics (15.3) when PostHog is not configured. No personal data."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(48), index=True)
    props: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow, index=True)


class RefreshToken(Base):
    """Refresh-token rotation (14.1): each use revokes the token and issues a new one."""

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    expires_at: Mapped[datetime] = mapped_column(TZ)
    revoked_at: Mapped[datetime | None] = mapped_column(TZ)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)


class WebLoginToken(Base):
    """One-time link from the bot to the web version (build prompt, stage 8)."""

    __tablename__ = "web_login_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    expires_at: Mapped[datetime] = mapped_column(TZ)
    used_at: Mapped[datetime | None] = mapped_column(TZ)


class ConfigOverride(Base):
    """Admin-panel changes to prices and flags without a deploy (stage 10)."""

    __tablename__ = "config_overrides"

    section: Mapped[str] = mapped_column(String(32), primary_key=True)
    patch: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)


class AuditLog(Base):
    """Admin actions and money movements outside normal play (14.1)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(128), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)


class Placement(Base):
    """State of the optional placement test (6.5)."""

    __tablename__ = "placements"

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    step_index: Mapped[int] = mapped_column(Integer)
    answered: Mapped[int] = mapped_column(Integer, default=0)
    results: Mapped[list[list[Any]]] = mapped_column(JSONB, default=list)
    current_instance_id: Mapped[int | None] = mapped_column(BigInteger)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)


class FloorTrial(Base):
    """An extern (open a floor for free) or a boss run: three tasks at difficulty 4 (3.3, 5.5)."""

    __tablename__ = "floor_trials"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(user_fk())
    floor_id: Mapped[int] = mapped_column(ForeignKey("floors.id"))
    kind: Mapped[str] = mapped_column(String(8))
    day: Mapped[date] = mapped_column(Date)
    instance_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger))
    correct: Mapped[int] = mapped_column(Integer, default=0)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TZ, default=utcnow)

    __table_args__ = (
        CheckConstraint("kind in ('extern','boss')", name="kind"),
        Index("ix_floor_trials_user_day", "user_id", "day"),
    )


class ConfidenceSnapshot(Base):
    """Daily confidence per task and the forecast (trend arrows, risk sort, 15.1)."""

    __tablename__ = "confidence_snapshots"

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    values: Mapped[dict[str, float]] = mapped_column(JSONB, default=dict)
    forecast_primary: Mapped[float] = mapped_column(Float, default=0.0)
