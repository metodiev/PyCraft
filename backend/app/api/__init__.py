"""API layer: dependency wiring and route assembly."""

from app.api import (
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
    "auth",
    "authoring",
    "challenges",
    "dashboard",
    "gamification",
    "github",
    "runtime",
    "submissions",
]
