"""Hidden tests — isolation, accounting and audit guarantees under stress."""

import pytest

from control_plane import ControlPlane, TenantExistsError
from repository import RecordNotFoundError, SharedStore, TenantRepository
from tenancy import (
    EntitlementError,
    PLANS,
    QuotaLedger,
    Tenant,
    TenantSettings,
    can_add_seat,
    plan_for,
    seat_count,
)


# --- isolation is structural ---------------------------------------------
def test_a_repository_exposes_no_cross_tenant_read():
    """Isolation must be impossible to bypass by passing a tenant id."""
    repo = TenantRepository(SharedStore(), "acme")
    public = [name for name in dir(repo) if not name.startswith("_")]

    for method in ("all_for", "for_tenant", "get_for", "cross_tenant_all"):
        assert method not in public, f"{method} would allow a cross-tenant read"


def test_the_same_record_id_in_two_tenants_does_not_collide():
    """Keying only on the record id silently overwrites the other tenant."""
    store = SharedStore()
    acme = TenantRepository(store, "acme")
    globex = TenantRepository(store, "globex")

    acme.add("1", {"owner": "acme"})
    globex.add("1", {"owner": "globex"})

    assert acme.get("1") == {"owner": "acme"}
    assert globex.get("1") == {"owner": "globex"}
    assert acme.count() == 1
    assert globex.count() == 1


def test_a_cross_tenant_read_is_indistinguishable_from_a_missing_row():
    """Leaking *which* case it is is itself an information disclosure."""
    store = SharedStore()
    TenantRepository(store, "globex").add("secret", {"value": 1})
    acme = TenantRepository(store, "acme")

    with pytest.raises(RecordNotFoundError):
        acme.get("secret")


def test_deleting_through_one_tenant_leaves_the_other_intact():
    store = SharedStore()
    acme = TenantRepository(store, "acme")
    globex = TenantRepository(store, "globex")
    acme.add("1", {"owner": "acme"})
    globex.add("1", {"owner": "globex"})

    acme.delete("1")

    assert globex.get("1") == {"owner": "globex"}


def test_counting_only_sees_the_owning_tenant():
    store = SharedStore()
    acme = TenantRepository(store, "acme")
    globex = TenantRepository(store, "globex")
    for index in range(5):
        acme.add(f"a{index}", {})
    for index in range(3):
        globex.add(f"g{index}", {})

    assert acme.count() == 5
    assert globex.count() == 3


def test_an_update_cannot_reach_another_tenants_row():
    store = SharedStore()
    TenantRepository(store, "globex").add("1", {"value": "globex"})
    acme = TenantRepository(store, "acme")

    with pytest.raises(RecordNotFoundError):
        acme.update("1", {"value": "hijacked"})

    assert TenantRepository(store, "globex").get("1") == {"value": "globex"}


def test_an_empty_repository_lists_nothing_even_when_others_have_rows():
    store = SharedStore()
    TenantRepository(store, "globex").add("r1", {})

    assert TenantRepository(store, "acme").all() == []


def test_rows_are_returned_sorted_and_stable():
    repo = TenantRepository(SharedStore(), "acme")
    for key in ("c", "a", "b"):
        repo.add(key, {"key": key})

    first = repo.all()
    second = repo.all()

    assert [row["key"] for row in first] == ["a", "b", "c"]
    assert first == second


def test_rows_are_isolated_after_many_tenants():
    store = SharedStore()
    for index in range(20):
        repo = TenantRepository(store, f"tenant-{index}")
        repo.add("shared-id", {"index": index})

    for index in range(20):
        repo = TenantRepository(store, f"tenant-{index}")
        assert repo.get("shared-id") == {"index": index}
        assert repo.count() == 1


# --- shared mutable state -------------------------------------------------
def test_settings_are_not_shared_between_instances():
    """A mutable class-level default leaks configuration across tenants."""
    first = TenantSettings()
    second = TenantSettings()

    first.set("feature_flag", True)

    assert second.get("feature_flag") is None


def test_two_settings_objects_have_independent_dicts():
    first = TenantSettings()
    second = TenantSettings()

    assert first.values is not second.values


# --- quota accounting -----------------------------------------------------
def test_a_rejected_charge_does_not_partially_apply():
    """Decrement-then-correct leaves a window where the counter is wrong."""
    ledger = QuotaLedger()
    ledger.consume("t", 60, 100)

    with pytest.raises(EntitlementError):
        ledger.consume("t", 50, 100)

    assert ledger.used("t") == 60
    assert ledger.remaining("t", 100) == 40


def test_a_charge_exactly_equal_to_the_remainder_is_allowed():
    ledger = QuotaLedger()
    ledger.consume("t", 60, 100)

    assert ledger.consume("t", 40, 100) == 100
    assert ledger.remaining("t", 100) == 0


def test_remaining_never_goes_negative():
    ledger = QuotaLedger()
    ledger.consume("t", 100, 100)

    assert ledger.remaining("t", 100) == 0


def test_a_non_positive_charge_is_rejected():
    ledger = QuotaLedger()

    with pytest.raises(ValueError):
        ledger.consume("t", 0, 100)
    with pytest.raises(ValueError):
        ledger.consume("t", -5, 100)


def test_quota_reset_affects_only_one_tenant():
    ledger = QuotaLedger()
    ledger.consume("a", 10, 100)
    ledger.consume("b", 20, 100)

    ledger.reset("a")

    assert ledger.used("a") == 0
    assert ledger.used("b") == 20


def test_quotas_of_different_tenants_are_independent():
    ledger = QuotaLedger()
    ledger.consume("a", 90, 100)

    assert ledger.remaining("b", 100) == 100


# --- entitlements ---------------------------------------------------------
def test_plans_are_ordered_by_capability():
    assert PLANS["free"].seat_limit < PLANS["pro"].seat_limit < PLANS["enterprise"].seat_limit
    assert PLANS["free"].api_quota < PLANS["pro"].api_quota < PLANS["enterprise"].api_quota


def test_enterprise_includes_every_lower_plan_feature():
    for plan in ("free", "pro"):
        assert PLANS[plan].features <= PLANS["enterprise"].features


def test_an_exact_plan_lookup_does_not_accept_a_near_miss():
    with pytest.raises(EntitlementError):
        plan_for("PRO")


def test_a_tenant_exactly_at_the_seat_limit_cannot_grow():
    plan = plan_for("pro")
    filled = Tenant(
        id="t",
        name="T",
        plan_id="pro",
        seats=frozenset(f"u{index}" for index in range(plan.seat_limit)),
    )

    assert can_add_seat(filled, plan) is False


def test_a_tenant_with_room_can_grow():
    plan = plan_for("pro")
    partly = Tenant(id="t", name="T", plan_id="pro", seats=frozenset({"u1"}))

    assert can_add_seat(partly, plan) is True


# --- control plane --------------------------------------------------------
def test_a_failed_provisioning_is_not_audited():
    """An audit log that records events which did not happen is worthless."""
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "free")

    with pytest.raises(TenantExistsError):
        plane.provision("acme", "Impostor", "free")

    assert [entry.action for entry in plane.audit_log("acme")] == ["tenant.provisioned"]


def test_an_unknown_plan_is_not_audited():
    plane = ControlPlane()

    with pytest.raises(EntitlementError):
        plane.provision("acme", "Acme Inc", "platinum")

    assert plane.audit_log("acme") == []


def test_a_rejected_seat_is_not_audited():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "free")
    plane.add_seat("acme", "u1")

    with pytest.raises(EntitlementError):
        plane.add_seat("acme", "u2")

    # Only the provisioning and the one successful seat.
    assert [entry.action for entry in plane.audit_log("acme")] == [
        "tenant.provisioned",
        "seat.added",
    ]


def test_a_rejected_quota_charge_is_not_audited():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "free")

    with pytest.raises(EntitlementError):
        plane.consume_quota("acme", PLANS["free"].api_quota + 1)

    assert [entry.action for entry in plane.audit_log("acme")] == ["tenant.provisioned"]
    assert plane.quota_remaining("acme") == PLANS["free"].api_quota


def test_adding_an_existing_seat_is_a_no_op_and_is_not_audited():
    """Nothing happened, so nothing should be logged."""
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "pro")
    plane.add_seat("acme", "u1")

    plane.add_seat("acme", "u1")

    assert seat_count(plane.get_tenant("acme")) == 1
    assert [entry.action for entry in plane.audit_log("acme")].count("seat.added") == 1


def test_removing_an_absent_seat_is_a_no_op_and_is_not_audited():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "pro")

    plane.remove_seat("acme", "never-added")

    assert [entry.action for entry in plane.audit_log("acme")] == ["tenant.provisioned"]


def test_audit_entries_are_ordered_and_sequenced():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "pro")
    plane.add_seat("acme", "u1")
    plane.consume_quota("acme", 5)

    entries = plane.audit_log("acme")

    assert [entry.seq for entry in entries] == sorted(entry.seq for entry in entries)
    assert len({entry.seq for entry in entries}) == len(entries)


def test_audit_logs_are_isolated_between_tenants():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "pro")
    plane.provision("globex", "Globex", "pro")
    plane.add_seat("acme", "u1")

    globex_actions = [entry.action for entry in plane.audit_log("globex")]

    assert globex_actions == ["tenant.provisioned"]
    assert all(entry.tenant_id == "globex" for entry in plane.audit_log("globex"))


def test_the_audit_log_records_the_actor():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "pro")

    plane.add_seat("acme", "u1", actor="admin@acme.test")

    entry = plane.audit_log("acme")[-1]
    assert entry.actor == "admin@acme.test"


def test_repositories_from_the_plane_remain_isolated():
    plane = ControlPlane()
    for index in range(5):
        plane.provision(f"tenant-{index}", f"Tenant {index}", "pro")
        plane.repo(f"tenant-{index}").add("shared", {"index": index})

    for index in range(5):
        assert plane.repo(f"tenant-{index}").get("shared") == {"index": index}


def test_getting_an_unknown_tenant_raises():
    plane = ControlPlane()

    with pytest.raises(KeyError):
        plane.get_tenant("nope")


def test_seats_of_different_tenants_do_not_interfere():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "pro")
    plane.provision("globex", "Globex", "pro")

    plane.add_seat("acme", "u1")
    plane.add_seat("globex", "u1")
    plane.remove_seat("acme", "u1")

    assert seat_count(plane.get_tenant("acme")) == 0
    assert seat_count(plane.get_tenant("globex")) == 1


def test_two_control_planes_do_not_share_state():
    """A shared registry would leak tenants between environments."""
    first = ControlPlane()
    second = ControlPlane()
    first.provision("acme", "Acme Inc", "pro")

    with pytest.raises(KeyError):
        second.get_tenant("acme")


def test_quota_consumption_accumulates_across_calls():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "pro")
    quota = PLANS["pro"].api_quota

    for _ in range(10):
        plane.consume_quota("acme", 100)

    assert plane.quota_remaining("acme") == quota - 1000
