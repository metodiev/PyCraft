"""Hidden tests — the failure modes that separate a working fanout from a
plausible one.

Everything here is driven by injected time and a seeded RNG, so the suite is
deterministic and never waits on the wall clock.
"""

import time

import pytest

from channels import (
    CLOSED,
    HALF_OPEN,
    OPEN,
    Channel,
    CircuitBreaker,
    DeliveryAttempt,
    PermanentError,
    RetryableError,
    TokenBucket,
)
from dedupe import DedupeStore
from fanout import (
    STATUS_CIRCUIT_OPEN,
    STATUS_DELIVERED,
    STATUS_DUPLICATE,
    STATUS_FAILED,
    STATUS_THROTTLED,
    STATUSES,
    Fanout,
    UnknownChannelError,
)


class FakeClock:
    def __init__(self, now: int = 0) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now

    def advance(self, ms: int) -> None:
        self.now += ms


class Scripted:
    """A transport that fails the first ``failures`` attempts it sees."""

    def __init__(self, failures: int = 0, error: type[Exception] = RetryableError) -> None:
        self.failures = failures
        self.error = error
        self.attempts: list[DeliveryAttempt] = []

    def __call__(self, attempt: DeliveryAttempt) -> None:
        self.attempts.append(attempt)
        if len(self.attempts) <= self.failures:
            raise self.error("scripted failure")

    @property
    def keys(self) -> list[str]:
        return [attempt.idempotency_key for attempt in self.attempts]

    @property
    def recipients(self) -> list[str]:
        return [attempt.recipient for attempt in self.attempts]


def build(
    *channels: Channel,
    clock: FakeClock,
    seed: int = 1,
    **options: object,
) -> Fanout:
    import random

    return Fanout(list(channels), clock=clock, random=random.Random(seed), **options)


def channel_for(
    name: str,
    transport: Scripted,
    clock: FakeClock,
    **options: object,
) -> Channel:
    return Channel(name, transport, clock=clock, **options)  # type: ignore[arg-type]


# =========================================================================
# dedupe.py — TTL and the size bound
# =========================================================================
def test_dedupe_entries_expire_on_the_injected_clock():
    clock = FakeClock(1_000)
    store = DedupeStore(ttl_ms=500, max_size=10, clock=clock)

    assert store.mark("n1") is True
    assert store.is_duplicate("n1") is True

    clock.advance(499)
    assert store.is_duplicate("n1") is True, "an entry must live until its TTL is reached"

    clock.advance(1)
    assert store.is_duplicate("n1") is False, "an entry must expire at its TTL"
    assert len(store) == 0, "expired entries must not be counted as live"
    assert store.expires_at("n1") is None


def test_dedupe_expiry_is_per_entry_not_per_store():
    """A fresh mark must not be swept away by an older entry's expiry."""
    clock = FakeClock()
    store = DedupeStore(ttl_ms=100, max_size=10, clock=clock)

    store.mark("old")
    clock.advance(60)
    store.mark("new")

    clock.advance(40)
    assert store.is_duplicate("old") is False
    assert store.is_duplicate("new") is True, "the new entry has 60ms left"
    assert store.expires_at("new") == 160

    clock.advance(60)
    assert store.is_duplicate("new") is False


def test_dedupe_a_repeated_hit_does_not_extend_the_ttl():
    clock = FakeClock()
    store = DedupeStore(ttl_ms=100, max_size=10, clock=clock)

    store.mark("n1")
    clock.advance(90)
    assert store.mark("n1") is False
    assert store.expires_at("n1") == 100, "a duplicate must not refresh the entry"

    clock.advance(10)
    assert store.is_duplicate("n1") is False


def test_dedupe_reuse_is_possible_after_expiry():
    clock = FakeClock()
    store = DedupeStore(ttl_ms=100, max_size=10, clock=clock)

    assert store.mark("n1") is True
    clock.advance(101)
    assert store.mark("n1") is True, "an expired key is new again"
    assert store.is_duplicate("n1") is True


def test_dedupe_enforces_the_size_bound():
    """Unbounded growth is the classic dedupe-store leak."""
    clock = FakeClock()
    store = DedupeStore(ttl_ms=10_000, max_size=8, clock=clock)

    for index in range(500):
        store.mark(f"n{index}")

    assert len(store) == 8, f"store grew to {len(store)} entries"
    assert store.is_duplicate("n499") is True
    assert store.is_duplicate("n0") is False, "the oldest entry must be evicted first"


def test_dedupe_eviction_keeps_the_newest_live_entries():
    clock = FakeClock()
    store = DedupeStore(ttl_ms=10_000, max_size=3, clock=clock)

    for name in ("a", "b", "c", "d"):
        store.mark(name)
        clock.advance(10)

    live = [name for name in ("a", "b", "c", "d") if store.is_duplicate(name)]
    assert live == ["b", "c", "d"]


def test_dedupe_size_bound_counts_only_live_entries():
    """Expired entries must not occupy room in a bounded store."""
    clock = FakeClock()
    store = DedupeStore(ttl_ms=100, max_size=3, clock=clock)

    for index in range(3):
        store.mark(f"old{index}")
    clock.advance(100)

    store.mark("fresh")
    assert store.is_duplicate("fresh") is True
    assert len(store) == 1
    assert store.purge_expired() == 0, "expired entries were already dropped"
    assert store.is_duplicate("old0") is False


def test_dedupe_lookup_does_not_create_entries():
    clock = FakeClock()
    store = DedupeStore(ttl_ms=100, max_size=4, clock=clock)

    for index in range(50):
        assert store.is_duplicate(f"ghost{index}") is False

    assert len(store) == 0, "reads must not allocate"
    store.mark("real")
    assert len(store) == 1


def test_dedupe_purge_reports_what_it_removed():
    clock = FakeClock()
    store = DedupeStore(ttl_ms=100, max_size=10, clock=clock)

    store.mark("a")
    store.mark("b")
    clock.advance(50)
    store.mark("c")

    assert store.purge_expired() == 0
    clock.advance(50)
    assert store.purge_expired() == 2
    assert len(store) == 1
    assert store.is_duplicate("c") is True


def test_dedupe_backwards_clock_does_not_expire_entries():
    """A clock that stalls or rewinds must not make a live entry vanish."""
    clock = FakeClock(5_000)
    store = DedupeStore(ttl_ms=100, max_size=10, clock=clock)

    store.mark("n1")
    clock.now = 1_000
    assert store.is_duplicate("n1") is True


# =========================================================================
# channels.py — token bucket
# =========================================================================
def test_token_bucket_refill_comes_from_the_injected_clock():
    """Refill must be measured against the injected clock, not the wall clock.

    Real elapsed time is a fraction of a millisecond here and buys nothing, so
    only an advance of the injected clock can produce these tokens.
    """
    clock = FakeClock()
    bucket = TokenBucket(capacity=10_000, refill_per_second=1.0, clock=clock)

    assert bucket.try_acquire(10_000) is True
    assert bucket.tokens == 0.0

    clock.advance(1_000)
    assert bucket.tokens == 1.0, "one injected second is worth exactly one token"

    clock.advance(3_000)
    assert bucket.tokens == 4.0
    clock.advance(0)
    assert bucket.tokens == 4.0, "a stalled clock must not mint tokens"


def test_token_bucket_caps_refill_at_capacity():
    clock = FakeClock()
    bucket = TokenBucket(capacity=3, refill_per_second=100.0, clock=clock)

    for _ in range(3):
        assert bucket.try_acquire()

    clock.advance(60_000)
    assert bucket.tokens == 3.0
    assert [bucket.try_acquire() for _ in range(4)] == [True, True, True, False]


def test_token_bucket_refills_proportionally_to_elapsed_time():
    clock = FakeClock()
    bucket = TokenBucket(capacity=10, refill_per_second=4.0, clock=clock)

    for _ in range(10):
        assert bucket.try_acquire()

    clock.advance(250)
    assert abs(bucket.tokens - 1.0) < 1e-6
    clock.advance(250)
    assert abs(bucket.tokens - 2.0) < 1e-6
    clock.advance(1_000)
    assert abs(bucket.tokens - 6.0) < 1e-6


def test_token_bucket_does_not_refill_without_elapsed_time():
    """Repeated calls at one instant must not mint tokens."""
    clock = FakeClock()
    bucket = TokenBucket(capacity=2, refill_per_second=1.0, clock=clock)

    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is True
    for _ in range(100):
        assert bucket.try_acquire() is False
    assert bucket.tokens == 0.0


def test_token_bucket_acquisition_is_all_or_nothing():
    clock = FakeClock()
    bucket = TokenBucket(capacity=5, refill_per_second=1.0, clock=clock)

    assert bucket.try_acquire(3) is True
    assert bucket.tokens == 2.0
    assert bucket.try_acquire(3) is False
    assert bucket.tokens == 2.0, "a refused acquisition must deduct nothing"
    assert bucket.try_acquire(2) is True
    assert bucket.tokens == 0.0


def test_token_bucket_awards_at_most_capacity_over_a_long_frozen_period():
    clock = FakeClock(0)
    bucket = TokenBucket(capacity=4, refill_per_second=1.0, clock=clock)

    granted = sum(1 for _ in range(50) if bucket.try_acquire())
    assert granted == 4

    clock.advance(1_000)
    granted = sum(1 for _ in range(50) if bucket.try_acquire())
    assert granted == 1, "one second buys exactly one token at 1/s"


# =========================================================================
# channels.py — circuit breaker
# =========================================================================
def test_circuit_breaker_opens_on_the_threshold_retryable_failure():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=3, cooldown_ms=1_000, clock=clock)

    for index in range(3):
        assert breaker.state == CLOSED
        breaker.record_failure()
        assert breaker.failures == index + 1

    assert breaker.state == OPEN
    assert breaker.allow() is False


def test_circuit_breaker_ignores_permanent_failures():
    """A bad payload is not evidence that the channel is down."""
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, cooldown_ms=1_000, clock=clock)

    for _ in range(10):
        breaker.record_failure(retryable=False)

    assert breaker.state == CLOSED
    assert breaker.failures == 0
    assert breaker.allow() is True


def test_circuit_breaker_half_opens_after_the_cooldown():
    clock = FakeClock(1_000)
    breaker = CircuitBreaker(failure_threshold=2, cooldown_ms=500, clock=clock)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == OPEN

    clock.advance(499)
    assert breaker.state == OPEN
    assert breaker.allow() is False

    clock.advance(1)
    assert breaker.state == HALF_OPEN
    assert breaker.allow() is True, "the cooldown must let a trial through"


def test_circuit_breaker_admits_one_trial_at_a_time():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, cooldown_ms=100, clock=clock)
    breaker.record_failure()
    clock.advance(100)
    assert breaker.state == HALF_OPEN

    assert breaker.allow() is True
    assert breaker.allow() is False, "only one trial may be in flight"

    breaker.record_success()
    assert breaker.state == CLOSED
    assert breaker.allow() is True


def test_circuit_breaker_reopens_when_the_trial_fails():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, cooldown_ms=100, clock=clock)
    breaker.record_failure()
    clock.advance(100)
    assert breaker.allow() is True

    breaker.record_failure()
    assert breaker.state == OPEN
    assert breaker.allow() is False, "a failed trial restarts the cooldown"

    clock.advance(100)
    assert breaker.allow() is True


def test_circuit_breaker_success_resets_the_failure_run():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=3, clock=clock)

    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    assert breaker.failures == 0

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CLOSED, "a failure run must start over after a success"


def test_channels_own_their_limiter_and_breaker_over_the_injected_clock():
    clock = FakeClock()
    first = Channel("email", Scripted(), clock=clock, capacity=1, refill_per_second=1.0)
    second = Channel("email", Scripted(), clock=clock, capacity=1, refill_per_second=1.0)

    first.limiter.try_acquire()
    assert first.limiter.try_acquire() is False
    assert second.limiter.try_acquire() is True, "channels must not share a bucket"

    first.breaker.record_failure()
    first.breaker.record_failure()
    first.breaker.record_failure()
    assert first.breaker.state == OPEN
    assert second.breaker.state == CLOSED


# =========================================================================
# fanout.py — at-least-once
# =========================================================================
def test_retryable_failure_is_not_lost_between_submissions():
    """The signature bug: a dropped retryable failure turns at-least-once
    into at-most-once."""
    clock = FakeClock()
    transport = Scripted(failures=99)
    channel = channel_for("email", transport, clock, capacity=10, refill_per_second=1.0)
    fanout = build(channel, clock=clock, max_attempts=2, retry_base_ms=1)

    first = fanout.notify("n1", recipients=["alice"], channels=["email"])
    assert [delivery.status for delivery in first.deliveries] == [STATUS_FAILED]
    assert first.ok is False
    assert len(transport.attempts) == 2

    transport.failures = 0
    second = fanout.notify("n1", recipients=["alice"], channels=["email"])
    assert [delivery.status for delivery in second.deliveries] == [STATUS_DELIVERED]
    assert len(transport.attempts) == 3, "the unfinished unit must be retried"


def test_a_permanent_failure_is_still_replayable():
    clock = FakeClock()
    transport = Scripted(failures=99, error=PermanentError)
    channel = channel_for("email", transport, clock)
    fanout = build(channel, clock=clock, max_attempts=3, retry_base_ms=1)

    fanout.notify("n1", recipients=["alice"], channels=["email"])
    assert len(transport.attempts) == 1, "a permanent failure must not be retried in place"

    transport.failures = 0
    report = fanout.notify("n1", recipients=["alice"], channels=["email"])
    assert [delivery.status for delivery in report.deliveries] == [STATUS_DELIVERED]


def test_only_successful_units_are_recorded():
    clock = FakeClock()
    good = channel_for("email", Scripted(), clock)
    bad = channel_for("sms", Scripted(failures=99, error=PermanentError), clock)
    fanout = build(good, bad, clock=clock, max_attempts=1)

    first = fanout.notify("n1", recipients=["alice"], channels=["email", "sms"])
    assert first.by_status()[STATUS_DELIVERED] == 1
    assert first.by_status()[STATUS_FAILED] == 1

    second = fanout.notify("n1", recipients=["alice"], channels=["email", "sms"])
    assert second.by_status()[STATUS_DUPLICATE] == 1
    assert second.by_status()[STATUS_FAILED] == 1
    assert len(good.sender.attempts) == 1, "a delivered unit must not be re-sent"
    assert len(bad.sender.attempts) == 2, "a failed unit must be retried"


def test_a_retried_unit_is_recorded_exactly_once():
    clock = FakeClock()
    transport = Scripted(failures=1)
    channel = channel_for("email", transport, clock)
    fanout = build(channel, clock=clock, max_attempts=3, retry_base_ms=1)

    first = fanout.notify("n1", recipients=["alice"], channels=["email"])
    assert first.by_status()[STATUS_DELIVERED] == 1
    assert len(transport.attempts) == 2

    second = fanout.notify("n1", recipients=["alice"], channels=["email"])
    assert [delivery.status for delivery in second.deliveries] == [STATUS_DUPLICATE]
    assert len(transport.attempts) == 2, "the retry already finished this unit"


def test_dedupe_scope_is_the_unit_not_the_notification():
    """One channel failing must not mark the whole notification as done."""
    clock = FakeClock()
    good = channel_for("email", Scripted(), clock)
    bad = channel_for("sms", Scripted(failures=99, error=PermanentError), clock)
    fanout = build(good, bad, clock=clock, max_attempts=1)

    fanout.notify("n1", recipients=["alice"], channels=["email", "sms"])
    assert len(good.sender.attempts) == 1
    assert len(bad.sender.attempts) == 1

    fanout.notify("n1", recipients=["alice"], channels=["email", "sms"])
    assert len(good.sender.attempts) == 1, "the sms failure must not re-send the email"
    assert len(bad.sender.attempts) == 2, "the sms retry must not be suppressed by the email"


def test_dedupe_scope_is_per_recipient_too():
    """A success for one recipient must not suppress another recipient."""
    clock = FakeClock()
    transport = Scripted()
    channel = channel_for("email", transport, clock, capacity=10, refill_per_second=1.0)
    fanout = build(channel, clock=clock)

    fanout.notify("n1", recipients=["alice"], channels=["email"])
    report = fanout.notify("n1", recipients=["alice", "bob"], channels=["email"])

    assert [delivery.status for delivery in report.deliveries] == [
        STATUS_DUPLICATE,
        STATUS_DELIVERED,
    ]
    assert transport.recipients == ["alice", "bob"]


def test_a_different_notification_is_never_suppressed():
    clock = FakeClock()
    transport = Scripted()
    channel = channel_for("email", transport, clock)
    fanout = build(channel, clock=clock)

    fanout.notify("n1", recipients=["alice"], channels=["email"])
    report = fanout.notify("n2", recipients=["alice"], channels=["email"])

    assert [delivery.status for delivery in report.deliveries] == [STATUS_DELIVERED]
    assert [attempt.notification_id for attempt in transport.attempts] == ["n1", "n2"]


def test_an_expired_record_no_longer_suppresses_delivery():
    clock = FakeClock()
    transport = Scripted()
    channel = channel_for("email", transport, clock)
    fanout = build(channel, clock=clock, dedupe_ttl_ms=500)

    fanout.notify("n1", recipients=["alice"], channels=["email"])
    clock.advance(500)
    report = fanout.notify("n1", recipients=["alice"], channels=["email"])

    assert [delivery.status for delivery in report.deliveries] == [STATUS_DELIVERED]
    assert len(transport.attempts) == 2


# =========================================================================
# fanout.py — one effect per attempt
# =========================================================================
def test_every_attempt_of_a_unit_shares_one_idempotency_key():
    clock = FakeClock()
    transport = Scripted(failures=2)
    channel = channel_for("email", transport, clock)
    fanout = build(channel, clock=clock, max_attempts=3, retry_base_ms=1)

    fanout.notify("n1", recipients=["alice"], channels=["email"])

    assert len(transport.keys) == 3
    assert len(set(transport.keys)) == 1, "retries must be recognisable as repeats"
    assert transport.keys[0]
    assert [attempt.attempt for attempt in transport.attempts] == [1, 2, 3]


def test_idempotency_keys_are_unique_per_unit():
    clock = FakeClock()
    email_transport = Scripted()
    sms_transport = Scripted()
    email = channel_for("email", email_transport, clock)
    sms = channel_for("sms", sms_transport, clock)
    fanout = build(email, sms, clock=clock)

    fanout.notify("n1", recipients=["alice", "bob"], channels=["email", "sms"])

    keys = email_transport.keys + sms_transport.keys
    assert len(keys) == 4
    assert len(set(keys)) == 4, "each (notification, channel, recipient) needs its own key"


def test_a_non_idempotent_channel_is_attempted_once():
    """Retrying a non-idempotent channel would duplicate the effect."""
    clock = FakeClock()
    transport = Scripted(failures=99)
    channel = channel_for("sms", transport, clock, idempotent=False)
    fanout = build(channel, clock=clock, max_attempts=5, retry_base_ms=1)

    report = fanout.notify("n1", recipients=["alice"], channels=["sms"])

    assert [delivery.status for delivery in report.deliveries] == [STATUS_FAILED]
    assert len(transport.attempts) == 1, "max_attempts must not beat idempotency"

    fanout.notify("n1", recipients=["alice"], channels=["sms"])
    assert len(transport.attempts) == 2, "a new submission is a new opportunity"


def test_a_non_idempotent_channel_does_not_lose_its_first_success():
    clock = FakeClock()
    transport = Scripted(failures=1)
    channel = channel_for("sms", transport, clock, idempotent=False)
    fanout = build(channel, clock=clock, max_attempts=5, retry_base_ms=1)

    first = fanout.notify("n1", recipients=["alice"], channels=["sms"])
    assert [delivery.status for delivery in first.deliveries] == [STATUS_FAILED]
    assert len(transport.attempts) == 1

    second = fanout.notify("n1", recipients=["alice"], channels=["sms"])
    assert [delivery.status for delivery in second.deliveries] == [STATUS_DELIVERED]
    assert len(transport.attempts) == 2


def test_retries_do_not_sleep(monkeypatch):
    """The backoff is reported, never waited out."""
    clock = FakeClock()
    transport = Scripted(failures=99)
    channel = channel_for("email", transport, clock)
    fanout = build(channel, clock=clock, max_attempts=3, retry_base_ms=5_000)

    def forbidden(*args, **kwargs):
        raise AssertionError("notify must not sleep")

    monkeypatch.setattr(time, "sleep", forbidden)

    report = fanout.notify("n1", recipients=["alice"], channels=["email"])

    assert report.deliveries[0].status == STATUS_FAILED
    assert report.deliveries[0].backoff_ms > 0, "the wait must be reported"
    assert clock.now == 0, "retrying must not consume injected time either"


def test_backoff_grows_with_each_retry_and_stays_in_range():
    clock = FakeClock()
    transport = Scripted(failures=99)
    channel = channel_for("email", transport, clock)
    fanout = build(channel, clock=clock, max_attempts=3, retry_base_ms=10)

    one = build(channel_for("a", Scripted(failures=99), clock), clock=clock, max_attempts=1,
                retry_base_ms=10).notify("n1", recipients=["r"], channels=["a"])

    report = fanout.notify("n1", recipients=["alice"], channels=["email"])
    delivery = report.deliveries[0]

    assert one.deliveries[0].backoff_ms == 0, "no retry means no wait"
    assert 30 <= delivery.backoff_ms <= 50, f"unexpected backoff {delivery.backoff_ms}"


def test_backoff_is_reproducible_for_a_given_seed():
    clock = FakeClock()

    def run() -> int:
        transport = Scripted(failures=99)
        channel = channel_for("email", transport, clock)
        fanout = build(channel, clock=clock, seed=17, max_attempts=3, retry_base_ms=10)
        return fanout.notify("n1", recipients=["alice"], channels=["email"]).deliveries[
            0
        ].backoff_ms

    assert run() == run(), "the injected RNG must make retries reproducible"


# =========================================================================
# fanout.py — limits and reporting
# =========================================================================
def test_rate_limit_is_enforced_per_channel_across_recipients():
    clock = FakeClock()
    transport = Scripted()
    channel = channel_for("email", transport, clock, capacity=2, refill_per_second=1.0)
    fanout = build(channel, clock=clock)

    report = fanout.notify("n1", recipients=["a", "b", "c"], channels=["email"])

    assert report.by_status()[STATUS_DELIVERED] == 2
    assert report.by_status()[STATUS_THROTTLED] == 1
    assert report.ok is False
    assert len(transport.attempts) == 2, "a throttled delivery must not reach the transport"


def test_an_idle_channel_cannot_bank_a_burst_above_its_capacity():
    """A quiet period must not accrue credit beyond the channel's cap."""
    clock = FakeClock()
    transport = Scripted()
    channel = channel_for("email", transport, clock, capacity=3, refill_per_second=1.0)
    fanout = build(channel, clock=clock)

    clock.advance(3_600_000)
    report = fanout.notify(
        "n1", recipients=[f"r{i}" for i in range(10)], channels=["email"]
    )

    assert report.by_status()[STATUS_DELIVERED] == 3, "an hour of quiet is still a cap of 3"
    assert report.by_status()[STATUS_THROTTLED] == 7
    assert len(transport.attempts) == 3


def test_rate_limits_are_recomputed_against_the_injected_clock_not_real_time():
    """The limiter must read the injected clock on every call it serves."""
    clock = FakeClock()
    transport = Scripted()
    channel = channel_for("email", transport, clock, capacity=1, refill_per_second=1_000.0)
    fanout = build(channel, clock=clock)

    first = fanout.notify("n1", recipients=["a"], channels=["email"])
    assert first.by_status()[STATUS_DELIVERED] == 1

    second = fanout.notify("n2", recipients=["a"], channels=["email"])
    assert second.by_status()[STATUS_THROTTLED] == 1, "no injected time has passed"

    clock.advance(1)
    third = fanout.notify("n3", recipients=["a"], channels=["email"])
    assert third.by_status()[STATUS_DELIVERED] == 1, "1ms at 1000/s refills one token"


def test_a_throttled_unit_costs_nothing_and_stays_retryable():
    clock = FakeClock()
    transport = Scripted()
    channel = channel_for("email", transport, clock, capacity=1, refill_per_second=1.0)
    fanout = build(channel, clock=clock)

    first = fanout.notify("n1", recipients=["a", "b"], channels=["email"])
    assert [delivery.attempts for delivery in first.deliveries] == [1, 0]
    assert first.deliveries[1].status == STATUS_THROTTLED

    clock.advance(1_000)
    second = fanout.notify("n1", recipients=["a", "b"], channels=["email"])
    assert [delivery.status for delivery in second.deliveries] == [
        STATUS_DUPLICATE,
        STATUS_DELIVERED,
    ]
    assert transport.recipients == ["a", "b"]


def test_limits_are_independent_per_channel():
    clock = FakeClock()
    email_transport = Scripted()
    sms_transport = Scripted()
    email = channel_for("email", email_transport, clock, capacity=1, refill_per_second=1.0)
    sms = channel_for("sms", sms_transport, clock, capacity=1, refill_per_second=1.0)
    fanout = build(email, sms, clock=clock)

    report = fanout.notify("n1", recipients=["a", "b"], channels=["email", "sms"])

    assert report.by_status()[STATUS_DELIVERED] == 2
    assert report.by_status()[STATUS_THROTTLED] == 2
    assert len(email_transport.attempts) == 1
    assert len(sms_transport.attempts) == 1


def test_open_circuit_stops_calls_and_costs_no_attempt():
    clock = FakeClock()
    transport = Scripted(failures=99)
    channel = channel_for(
        "email",
        transport,
        clock,
        capacity=10,
        refill_per_second=1.0,
        failure_threshold=2,
        cooldown_ms=5_000,
    )
    fanout = build(channel, clock=clock, max_attempts=1)

    report = fanout.notify("n1", recipients=["a", "b", "c"], channels=["email"])

    statuses = [delivery.status for delivery in report.deliveries]
    assert statuses == [STATUS_FAILED, STATUS_FAILED, STATUS_CIRCUIT_OPEN]
    assert report.deliveries[2].attempts == 0
    assert len(transport.attempts) == 2, "the breaker must spare the transport"


def test_half_open_trial_can_close_the_circuit_again():
    """A breaker that never resets keeps a recovered channel out of service."""
    clock = FakeClock()
    transport = Scripted(failures=99)
    channel = channel_for(
        "email",
        transport,
        clock,
        capacity=10,
        refill_per_second=1.0,
        failure_threshold=2,
        cooldown_ms=1_000,
    )
    fanout = build(channel, clock=clock, max_attempts=1)

    fanout.notify("n1", recipients=["a", "b", "c"], channels=["email"])
    assert len(transport.attempts) == 2

    transport.failures = 0
    clock.advance(1_000)
    report = fanout.notify("n1", recipients=["a", "b", "c"], channels=["email"])

    assert report.ok is True, [delivery.status for delivery in report.deliveries]
    assert report.by_status()[STATUS_DELIVERED] == 3
    assert len(transport.attempts) == 5

    afterwards = fanout.notify("n2", recipients=["a", "b", "c"], channels=["email"])
    assert afterwards.by_status()[STATUS_DELIVERED] == 3
    assert channel.breaker.state == CLOSED, "a recovered channel must stay closed"


def test_circuit_open_units_are_not_throttled_or_recorded():
    clock = FakeClock()
    transport = Scripted(failures=99)
    channel = channel_for(
        "email",
        transport,
        clock,
        capacity=10,
        refill_per_second=1.0,
        failure_threshold=1,
        cooldown_ms=10_000,
    )
    fanout = build(channel, clock=clock, max_attempts=1)

    fanout.notify("n1", recipients=["a", "b"], channels=["email"])
    assert len(transport.attempts) == 1

    transport.failures = 0
    report = fanout.notify("n1", recipients=["a", "b"], channels=["email"])
    assert report.by_status()[STATUS_CIRCUIT_OPEN] == 2
    assert report.by_status()[STATUS_DUPLICATE] == 0, "nothing was delivered, so nothing is known"
    assert len(transport.attempts) == 1


def test_permanent_failures_alone_do_not_open_the_circuit():
    clock = FakeClock()
    transport = Scripted(failures=99, error=PermanentError)
    channel = channel_for(
        "email", transport, clock, capacity=10, refill_per_second=1.0, failure_threshold=2
    )
    fanout = build(channel, clock=clock, max_attempts=3, retry_base_ms=1)

    report = fanout.notify("n1", recipients=["a", "b", "c"], channels=["email"])

    assert [delivery.status for delivery in report.deliveries] == [STATUS_FAILED] * 3
    assert [delivery.attempts for delivery in report.deliveries] == [1, 1, 1]
    assert channel.breaker.state == CLOSED
    assert len(transport.attempts) == 3, "a permanent error is not a channel outage"


def test_a_partially_failed_fanout_is_not_reported_as_success():
    clock = FakeClock()
    good = channel_for("email", Scripted(), clock)
    bad = channel_for("sms", Scripted(failures=99, error=PermanentError), clock)
    fanout = build(good, bad, clock=clock, max_attempts=1)

    report = fanout.notify("n1", recipients=["alice", "bob"], channels=["email", "sms"])

    assert len(report.deliveries) == 4
    assert report.ok is False
    assert report.by_status()[STATUS_DELIVERED] == 2
    assert report.by_status()[STATUS_FAILED] == 2


def test_report_helpers_agree_with_the_deliveries():
    clock = FakeClock()
    good = channel_for("email", Scripted(), clock)
    bad = channel_for("sms", Scripted(failures=99, error=PermanentError), clock)
    fanout = build(good, bad, clock=clock, max_attempts=1)

    report = fanout.notify("n1", recipients=["alice", "bob"], channels=["email", "sms"])

    assert [delivery.recipient for delivery in report.for_channel("email")] == ["alice", "bob"]
    assert [delivery.channel for delivery in report.for_recipient("alice")] == ["email", "sms"]
    assert report.for_channel("carrier-pigeon") == ()
    assert report.attempts == 4
    assert set(report.by_status()) == set(STATUSES)
    assert sum(report.by_status().values()) == len(report.deliveries)


def test_delivery_order_follows_the_callers_lists():
    clock = FakeClock()
    email = channel_for("email", Scripted(), clock)
    sms = channel_for("sms", Scripted(), clock)
    fanout = build(email, sms, clock=clock)

    report = fanout.notify("n1", recipients=["bob", "alice"], channels=["sms", "email"])

    assert [(delivery.recipient, delivery.channel) for delivery in report.deliveries] == [
        ("bob", "sms"),
        ("bob", "email"),
        ("alice", "sms"),
        ("alice", "email"),
    ]


def test_repeated_names_are_collapsed():
    clock = FakeClock()
    transport = Scripted()
    channel = channel_for("email", transport, clock)
    fanout = build(channel, clock=clock)

    report = fanout.notify(
        "n1", recipients=["alice", "alice"], channels=["email", "email"]
    )

    assert len(report.deliveries) == 1
    assert len(transport.attempts) == 1


def test_a_bare_string_is_one_value_not_a_sequence_of_characters():
    clock = FakeClock()
    transport = Scripted()
    channel = channel_for("email", transport, clock)
    fanout = build(channel, clock=clock)

    report = fanout.notify("n1", recipients="alice", channels="email")

    assert len(report.deliveries) == 1
    assert report.deliveries[0].recipient == "alice"
    assert transport.recipients == ["alice"]


def test_an_unknown_channel_fails_before_anything_is_sent():
    clock = FakeClock()
    transport = Scripted()
    channel = channel_for("email", transport, clock)
    fanout = build(channel, clock=clock)

    try:
        fanout.notify("n1", recipients=["alice"], channels=["email", "carrier-pigeon"])
    except UnknownChannelError:
        pass
    else:  # pragma: no cover - the assertion is the point
        raise AssertionError("an unknown channel must raise UnknownChannelError")

    assert transport.attempts == []
    assert fanout.dedupe.is_duplicate(fanout.unit_key("n1", "email", "alice")) is False
    assert fanout.stats()["submissions"] == 0


def test_empty_requests_are_rejected():
    clock = FakeClock()
    fanout = build(channel_for("email", Scripted(), clock), clock=clock)

    for call in (
        lambda: fanout.notify("", recipients=["alice"], channels=["email"]),
        lambda: fanout.notify("n1", recipients=[], channels=["email"]),
        lambda: fanout.notify("n1", recipients=["alice"], channels=[]),
    ):
        try:
            call()
        except ValueError:
            continue
        raise AssertionError("an empty submission must raise ValueError")


def test_registering_a_channel_twice_is_rejected_and_chains():
    clock = FakeClock()
    fanout = Fanout(clock=clock)
    channel = channel_for("email", Scripted(), clock)

    assert fanout.register_channel(channel) is channel
    assert fanout.channel("email") is channel

    try:
        fanout.register_channel(channel_for("email", Scripted(), clock))
    except ValueError:
        pass
    else:  # pragma: no cover - the assertion is the point
        raise AssertionError("a duplicate channel name must raise ValueError")

    try:
        fanout.channel("nope")
    except UnknownChannelError:
        pass
    else:  # pragma: no cover - the assertion is the point
        raise AssertionError("an unknown name must raise UnknownChannelError")


def test_stats_aggregate_every_submission():
    clock = FakeClock()
    transport = Scripted(failures=99)
    channel = channel_for(
        "email", transport, clock, capacity=10, refill_per_second=1.0, failure_threshold=99
    )
    fanout = build(channel, clock=clock, max_attempts=2, retry_base_ms=1)

    fanout.notify("n1", recipients=["alice", "bob"], channels=["email"])
    fanout.notify("n2", recipients=["alice"], channels=["email"])

    stats = fanout.stats()
    assert stats["submissions"] == 2
    assert stats["deliveries"] == 3
    assert stats["attempts"] == 6, "two attempts per delivery across three deliveries"
    assert stats["by_status"][STATUS_FAILED] == 3
    assert set(stats["by_status"]) == set(STATUSES)
    assert stats["by_channel"]["email"][STATUS_FAILED] == 3
    assert stats["by_channel"]["email"][STATUS_DELIVERED] == 0


def test_stats_are_a_snapshot():
    clock = FakeClock()
    fanout = build(channel_for("email", Scripted(), clock), clock=clock)

    fanout.notify("n1", recipients=["alice"], channels=["email"])
    first = fanout.stats()
    first["by_status"][STATUS_DELIVERED] = 999
    first["by_channel"]["email"][STATUS_DELIVERED] = 999

    second = fanout.stats()
    assert second["by_status"][STATUS_DELIVERED] == 1
    assert second["by_channel"]["email"][STATUS_DELIVERED] == 1


def test_a_fanout_uses_the_dedupe_store_it_exposes():
    clock = FakeClock()
    fanout = build(channel_for("email", Scripted(), clock), clock=clock)
    assert isinstance(fanout.dedupe, DedupeStore)

    fanout.notify("n1", recipients=["alice"], channels=["email"])
    key = fanout.unit_key("n1", "email", "alice")
    assert fanout.dedupe.is_duplicate(key) is True

    fanout.dedupe.clear()
    transport = fanout.channel("email").sender
    report = fanout.notify("n1", recipients=["alice"], channels=["email"])
    assert [delivery.status for delivery in report.deliveries] == [STATUS_DELIVERED]
    assert len(transport.attempts) == 2


def test_an_unexpected_transport_error_is_not_swallowed():
    """A bug in the transport is not a transient fault; retrying hides it."""
    clock = FakeClock()
    attempts: list[DeliveryAttempt] = []

    def broken(attempt: DeliveryAttempt) -> None:
        attempts.append(attempt)
        raise KeyError("misconfigured transport")

    channel = Channel("email", broken, clock=clock)
    fanout = build(channel, clock=clock, max_attempts=3, retry_base_ms=1)

    with pytest.raises(KeyError):
        fanout.notify("n1", recipients=["alice"], channels=["email"])

    assert len(attempts) == 1, "an unexpected exception must not be retried"


def test_the_fanout_bounds_its_own_dedupe_store():
    """A long-lived fanout must not remember every notification forever."""
    clock = FakeClock()
    transport = Scripted()
    channel = channel_for("email", transport, clock)
    fanout = build(channel, clock=clock, dedupe_max_size=2)

    for index in range(3):
        report = fanout.notify(f"n{index}", recipients=["alice"], channels=["email"])
        assert [delivery.status for delivery in report.deliveries] == [STATUS_DELIVERED]

    assert len(fanout.dedupe) == 2
    replay = fanout.notify("n0", recipients=["alice"], channels=["email"])
    assert [delivery.status for delivery in replay.deliveries] == [STATUS_DELIVERED]
    assert len(transport.attempts) == 4, "the evicted record must not suppress a delivery"


def test_more_recipients_than_capacity_are_spread_over_time():
    clock = FakeClock()
    transport = Scripted()
    channel = channel_for("email", transport, clock, capacity=2, refill_per_second=2.0)
    fanout = build(channel, clock=clock)

    report = fanout.notify("n1", recipients=["a", "b", "c", "d"], channels=["email"])
    assert report.by_status()[STATUS_DELIVERED] == 2
    assert report.by_status()[STATUS_THROTTLED] == 2

    clock.advance(500)
    report = fanout.notify("n1", recipients=["c", "d"], channels=["email"])
    assert report.by_status()[STATUS_DELIVERED] == 1
    assert report.by_status()[STATUS_THROTTLED] == 1
    assert len(transport.attempts) == 3


def test_breaker_state_is_visible_on_the_channel():
    clock = FakeClock()
    transport = Scripted(failures=99)
    channel = channel_for(
        "email",
        transport,
        clock,
        capacity=10,
        refill_per_second=1.0,
        failure_threshold=2,
        cooldown_ms=1_000,
    )
    fanout = build(channel, clock=clock, max_attempts=1)

    assert channel.breaker.state == CLOSED
    fanout.notify("n1", recipients=["a", "b"], channels=["email"])
    assert channel.breaker.state == OPEN

    clock.advance(1_000)
    assert channel.breaker.state == HALF_OPEN
