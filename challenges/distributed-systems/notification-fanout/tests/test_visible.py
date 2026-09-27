"""Visible tests — the basic contract for each module."""

import random

from channels import (
    CLOSED,
    OPEN,
    Channel,
    CircuitBreaker,
    DeliveryAttempt,
    DeliveryError,
    PermanentError,
    RetryableError,
    TokenBucket,
)
from dedupe import DedupeStore
from fanout import (
    STATUS_DELIVERED,
    STATUS_DUPLICATE,
    STATUS_FAILED,
    Fanout,
    UnknownChannelError,
)


class FakeClock:
    """A hand-wound clock: time only moves when the test moves it."""

    def __init__(self, now: int = 0) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now

    def advance(self, ms: int) -> None:
        self.now += ms


class Recorder:
    """A fake transport that records every attempt and fails on demand."""

    def __init__(self, failures: int = 0, error: type[DeliveryError] = RetryableError) -> None:
        self.attempts: list[DeliveryAttempt] = []
        self.failures = failures
        self.error = error

    def __call__(self, attempt: DeliveryAttempt) -> None:
        self.attempts.append(attempt)
        if len(self.attempts) <= self.failures:
            raise self.error("simulated transport failure")


def make_channel(
    name: str = "email",
    *,
    recorder: Recorder | None = None,
    clock: FakeClock | None = None,
    **options: object,
) -> tuple[Channel, Recorder]:
    transport = recorder if recorder is not None else Recorder()
    channel = Channel(name, transport, clock=clock or FakeClock(), **options)  # type: ignore[arg-type]
    return channel, transport


# --- channels.py ---------------------------------------------------------
def test_token_bucket_starts_full_and_then_refuses():
    bucket = TokenBucket(capacity=3, refill_per_second=1.0, clock=FakeClock())

    assert bucket.tokens == 3.0
    assert [bucket.try_acquire() for _ in range(4)] == [True, True, True, False]
    assert bucket.tokens == 0.0


def test_token_bucket_refills_for_elapsed_time():
    clock = FakeClock()
    bucket = TokenBucket(capacity=4, refill_per_second=2.0, clock=clock)

    for _ in range(4):
        assert bucket.try_acquire()

    clock.advance(500)
    assert abs(bucket.tokens - 1.0) < 1e-9
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False


def test_circuit_breaker_opens_after_consecutive_failures():
    breaker = CircuitBreaker(failure_threshold=3, cooldown_ms=1_000, clock=FakeClock())

    assert breaker.state == CLOSED
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CLOSED
    assert breaker.failures == 2
    assert breaker.allow() is True

    breaker.record_failure()
    assert breaker.state == OPEN
    assert breaker.allow() is False


def test_circuit_breaker_success_closes_it_again():
    breaker = CircuitBreaker(failure_threshold=2, clock=FakeClock())
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == OPEN

    breaker.record_success()
    assert breaker.state == CLOSED
    assert breaker.failures == 0
    assert breaker.allow() is True


def test_channel_forwards_attempts_to_its_transport():
    channel, transport = make_channel()
    attempt = DeliveryAttempt("n1", "alice", "email", {"text": "hi"}, "n1:email:alice", 1)

    channel.send(attempt)

    assert transport.attempts == [attempt]
    assert channel.name == "email"
    assert channel.idempotent is True


def test_channel_builds_its_own_limiter_and_breaker():
    first, _ = make_channel("email")
    second, _ = make_channel("sms")

    assert isinstance(first.limiter, TokenBucket)
    assert isinstance(first.breaker, CircuitBreaker)
    assert first.limiter is not second.limiter
    assert first.breaker is not second.breaker


# --- dedupe.py -----------------------------------------------------------
def test_dedupe_marks_keys_and_counts_live_entries():
    store = DedupeStore(ttl_ms=5_000, max_size=10, clock=FakeClock())

    assert store.mark("a") is True
    assert store.mark("a") is False
    assert store.is_duplicate("a") is True
    assert store.is_duplicate("b") is False
    assert len(store) == 1
    assert "a" in store


def test_dedupe_forgets_and_clears():
    store = DedupeStore(clock=FakeClock())
    store.mark("a")
    store.mark("b")

    assert store.forget("a") is True
    assert store.forget("a") is False
    assert store.is_duplicate("a") is False
    assert store.is_duplicate("b") is True

    store.clear()
    assert len(store) == 0


def test_dedupe_stores_are_independent():
    clock = FakeClock()
    first = DedupeStore(clock=clock)
    second = DedupeStore(clock=clock)

    first.mark("a")
    assert second.is_duplicate("a") is False


# --- fanout.py -----------------------------------------------------------
def test_fanout_delivers_every_recipient_on_every_channel():
    clock = FakeClock()
    email, email_transport = make_channel("email", clock=clock)
    sms, sms_transport = make_channel("sms", clock=clock)
    fanout = Fanout([email, sms], clock=clock, random=random.Random(7))

    report = fanout.notify(
        "n1", {"text": "hi"}, recipients=["alice", "bob"], channels=["email", "sms"]
    )

    assert report.notification_id == "n1"
    assert report.ok is True
    assert len(report.deliveries) == 4
    assert {delivery.status for delivery in report.deliveries} == {STATUS_DELIVERED}
    assert [(d.recipient, d.channel) for d in report.deliveries] == [
        ("alice", "email"),
        ("alice", "sms"),
        ("bob", "email"),
        ("bob", "sms"),
    ]
    assert len(email_transport.attempts) == 2
    assert len(sms_transport.attempts) == 2
    assert email_transport.attempts[0].payload == {"text": "hi"}


def test_fanout_returns_a_duplicate_for_a_repeated_submission():
    clock = FakeClock()
    email, transport = make_channel(clock=clock)
    fanout = Fanout([email], clock=clock)

    fanout.notify("n1", recipients=["alice", "bob"], channels=["email"])
    report = fanout.notify("n1", recipients=["alice", "bob"], channels=["email"])

    assert [delivery.status for delivery in report.deliveries] == [STATUS_DUPLICATE] * 2
    assert len(transport.attempts) == 2


def test_fanout_rejects_an_unknown_channel():
    clock = FakeClock()
    email, transport = make_channel(clock=clock)
    fanout = Fanout([email], clock=clock)

    for unknown in ("carrier-pigeon", "sms"):
        try:
            fanout.notify("n1", recipients=["alice"], channels=[unknown])
        except UnknownChannelError:
            pass
        else:  # pragma: no cover - the assertion is the point
            raise AssertionError(f"{unknown!r} must not be a known channel")

    assert transport.attempts == []


def test_fanout_retries_a_retryable_failure():
    clock = FakeClock()
    channel, transport = make_channel(clock=clock, recorder=Recorder(failures=2))
    fanout = Fanout([channel], clock=clock, random=random.Random(11), max_attempts=3, retry_base_ms=1)

    report = fanout.notify("n1", recipients=["alice"], channels=["email"])

    delivery = report.deliveries[0]
    assert delivery.status == STATUS_DELIVERED
    assert delivery.attempts == 3
    assert [attempt.attempt for attempt in transport.attempts] == [1, 2, 3]
    assert report.ok is True


def test_fanout_does_not_retry_a_permanent_failure():
    clock = FakeClock()
    channel, transport = make_channel(
        clock=clock, recorder=Recorder(failures=99, error=PermanentError)
    )
    fanout = Fanout([channel], clock=clock, random=random.Random(5), max_attempts=3, retry_base_ms=1)

    report = fanout.notify("n1", recipients=["alice"], channels=["email"])

    delivery = report.deliveries[0]
    assert delivery.status == STATUS_FAILED
    assert delivery.attempts == 1
    assert delivery.error is not None
    assert len(transport.attempts) == 1


def test_fanout_reports_backoff_without_sleeping():
    clock = FakeClock()
    channel, _ = make_channel(clock=clock, recorder=Recorder(failures=1))
    fanout = Fanout([channel], clock=clock, random=random.Random(3), max_attempts=2,
                    retry_base_ms=5)

    report = fanout.notify("n1", recipients=["alice"], channels=["email"])

    assert report.deliveries[0].backoff_ms > 0
    assert clock.now == 0


def test_fanout_stats_describe_the_submissions():
    clock = FakeClock()
    email, _ = make_channel(clock=clock)
    sms, _ = make_channel("sms", clock=clock)
    fanout = Fanout([email, sms], clock=clock)

    fanout.notify("n1", recipients=["alice"], channels=["email", "sms"])
    stats = fanout.stats()

    assert stats["submissions"] == 1
    assert stats["deliveries"] == 2
    assert stats["attempts"] == 2
    assert stats["by_status"][STATUS_DELIVERED] == 2
    assert set(stats["by_channel"]) == {"email", "sms"}
