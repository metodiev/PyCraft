"""Visible tests — the basic contract for each module."""

import pytest

from control_plane import ControlPlane, TenantExistsError
from repository import RecordNotFoundError, SharedStore, TenantRepository
from tenancy import (
    EntitlementError,
    PLANS,
    QuotaLedger,
    Tenant,
    TenantSettings,
    assert_feature,
    can_add_seat,
    has_feature,
    plan_for,
    seat_count,
)


# --- plans and entitlements ----------------------------------------------
def test_plans_include_the_expected_ids():
    assert {"free", "pro", "enterprise"} <= set(PLANS)


def test_plan_for_returns_the_plan():
    assert plan_for("pro").id == "pro"


def test_plan_for_rejects_an_unknown_plan():
    with pytest.raises(EntitlementError):
        plan_for("platinum")


def test_has_feature_reports_plan_features():
    tenant = Tenant(id="t", name="T", plan_id="pro")

    assert has_feature(tenant, "api") is True
    assert has_feature(tenant, "sso") is False


def test_assert_feature_raises_for_a_missing_feature():
    tenant = Tenant(id="t", name="T", plan_id="free")

    with pytest.raises(EntitlementError):
        assert_feature(tenant, "sso")


def test_seat_count_counts_the_seats():
    tenant = Tenant(id="t", name="T", plan_id="pro")
    tenant = Tenant(id="t", name="T", plan_id="pro", seats=frozenset({"u1", "u2"}))

    assert seat_count(tenant) == 2


def test_a_plan_at_its_seat_limit_cannot_add_more():
    tenant = Tenant(id="t", name="T", plan_id="free", seats=frozenset({"u1"}))

    assert can_add_seat(tenant, plan_for("free")) is False


# --- settings ------------------------------------------------------------
def test_settings_round_trip_a_value():
    settings = TenantSettings()

    settings.set("timezone", "UTC")

    assert settings.get("timezone") == "UTC"


def test_settings_return_a_default_for_an_absent_key():
    assert TenantSettings().get("missing", "fallback") == "fallback"


# --- quota ---------------------------------------------------------------
def test_quota_consumption_is_tracked():
    ledger = QuotaLedger()

    assert ledger.consume("t", 10, 100) == 10
    assert ledger.remaining("t", 100) == 90


def test_quota_reset_starts_a_new_period():
    ledger = QuotaLedger()
    ledger.consume("t", 10, 100)

    ledger.reset("t")

    assert ledger.used("t") == 0


def test_quota_rejects_an_over_charge():
    ledger = QuotaLedger()

    with pytest.raises(EntitlementError):
        ledger.consume("t", 101, 100)


# --- repository ----------------------------------------------------------
def test_a_repository_round_trips_a_row():
    repo = TenantRepository(SharedStore(), "acme")
    repo.add("r1", {"value": 1})

    assert repo.get("r1") == {"value": 1}


def test_a_missing_row_raises():
    repo = TenantRepository(SharedStore(), "acme")

    with pytest.raises(RecordNotFoundError):
        repo.get("r1")


def test_rows_are_isolated_between_tenants():
    store = SharedStore()
    acme = TenantRepository(store, "acme")
    globex = TenantRepository(store, "globex")

    acme.add("r1", {"value": "acme"})
    globex.add("r1", {"value": "globex"})

    assert acme.get("r1") == {"value": "acme"}
    assert globex.get("r1") == {"value": "globex"}


def test_all_lists_only_this_tenants_rows():
    store = SharedStore()
    acme = TenantRepository(store, "acme")
    TenantRepository(store, "globex").add("other", {})

    acme.add("r1", {})
    acme.add("r2", {})

    assert len(acme.all()) == 2
    assert acme.count() == 2


def test_delete_removes_the_row():
    repo = TenantRepository(SharedStore(), "acme")
    repo.add("r1", {})
    repo.delete("r1")

    with pytest.raises(RecordNotFoundError):
        repo.get("r1")


# --- control plane -------------------------------------------------------
def test_provision_creates_a_tenant():
    plane = ControlPlane()

    tenant = plane.provision("acme", "Acme Inc", "pro")

    assert tenant.id == "acme"
    assert plane.get_tenant("acme").plan_id == "pro"


def test_provisioning_a_duplicate_is_rejected():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "pro")

    with pytest.raises(TenantExistsError):
        plane.provision("acme", "Other", "free")


def test_provisioning_an_unknown_plan_is_rejected():
    plane = ControlPlane()

    with pytest.raises(EntitlementError):
        plane.provision("acme", "Acme Inc", "platinum")


def test_seats_can_be_added_and_removed():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "pro")

    plane.add_seat("acme", "u1")
    assert seat_count(plane.get_tenant("acme")) == 1

    plane.remove_seat("acme", "u1")
    assert seat_count(plane.get_tenant("acme")) == 0


def test_the_seat_limit_is_enforced():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "free")
    plane.add_seat("acme", "u1")

    with pytest.raises(EntitlementError):
        plane.add_seat("acme", "u2")


def test_quota_is_consumed_through_the_plane():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "pro")

    plane.consume_quota("acme", 100)

    assert plane.quota_remaining("acme") == plan_for("pro").api_quota - 100


def test_the_audit_log_records_actions():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "pro")
    plane.add_seat("acme", "u1")

    actions = [entry.action for entry in plane.audit_log("acme")]

    assert actions == ["tenant.provisioned", "seat.added"]


def test_a_repository_from_the_plane_is_scoped():
    plane = ControlPlane()
    plane.provision("acme", "Acme Inc", "pro")
    plane.provision("globex", "Globex", "pro")

    plane.repo("acme").add("r1", {"value": "acme"})

    with pytest.raises(RecordNotFoundError):
        plane.repo("globex").get("r1")
