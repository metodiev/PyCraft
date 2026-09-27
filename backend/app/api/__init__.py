"""API layer: dependency wiring and route assembly."""

from app.api import (
    ai,
    auth,
    authoring,
    challenges,
    dashboard,
    gamification,
    github,
    runtime,
    submissions,
)

__all__ = [
    "ai",
    "auth",
    "authoring",
    "challenges",
    "dashboard",
    "gamification",
    "github",
    "runtime",
    "submissions",
]
