from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, field_validator


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ProfileLite(BaseModel):
    landlord_name: str = ""
    landlord_address: str = ""
    landlord_phone: str = ""
    landlord_email: str = ""

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool
    force_password_change: bool
    profile: Optional[ProfileLite] = None

    model_config = {"from_attributes": True}


# ── Profile (per-user landlord info + signature) ─────────────────────────────

class ProfileUpdate(BaseModel):
    landlord_name: str = ""
    landlord_address: str = ""
    landlord_phone: str = ""
    landlord_email: str = ""


class ProfileOut(ProfileUpdate):
    has_signature: bool = False
    model_config = {"from_attributes": True}


# ── Admin: users management ───────────────────────────────────────────────────

ROLES = ("admin", "supervisor", "user")


class AdminUserCreate(BaseModel):
    username: str
    email: Optional[str] = None
    role: str = "user"
    temporary_password: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        return v


class AdminUserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v is not None and v not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        return v


class AdminUserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool
    created_at: Optional[datetime] = None
    force_password_change: bool

    model_config = {"from_attributes": True}


class TempPasswordOut(BaseModel):
    temporary_password: str


# ── Admin: groups management ──────────────────────────────────────────────────

class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class GroupOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    member_count: int = 0
    property_count: int = 0
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class GroupDetailOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    user_ids: list[int] = []
    property_ids: list[int] = []
    model_config = {"from_attributes": True}


class GroupMembersUpdate(BaseModel):
    user_ids: list[int] = []


class GroupPropertiesUpdate(BaseModel):
    property_ids: list[int] = []


# ── Property ──────────────────────────────────────────────────────────────────

class PropertyCreate(BaseModel):
    name: str
    type: str
    address_street: str
    address_city: str
    address_zip: str
    address_country: str = "France"

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        if v not in ("apartment", "parking"):
            raise ValueError("type must be apartment or parking")
        return v


class PropertyUpdate(PropertyCreate):
    pass


class PropertyOut(PropertyCreate):
    id: int
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── Tenant ────────────────────────────────────────────────────────────────────

class TenantCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    guarantor_name: Optional[str] = None


class TenantUpdate(TenantCreate):
    pass


class TenantOut(TenantCreate):
    id: int
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── Lease ─────────────────────────────────────────────────────────────────────

LEASE_TYPES = ("unfurnished", "furnished", "furnished_student")


class LeaseCreate(BaseModel):
    property_id: int
    tenant_id: int
    parent_lease_id: Optional[int] = None
    lease_type: str = "unfurnished"
    start_date: date
    # These two go into the lease's `initial` rent_revision — not stored on the
    # leases row. For amendments, they create the child's own initial revision.
    monthly_rent: Decimal
    monthly_charges: Decimal = Decimal("0")
    security_deposit_amount: Optional[Decimal] = None
    security_deposit_date: Optional[date] = None
    is_active: bool = True

    @field_validator("lease_type")
    @classmethod
    def validate_lease_type(cls, v):
        if v not in LEASE_TYPES:
            raise ValueError(f"lease_type must be one of {LEASE_TYPES}")
        return v


class LeaseUpdate(LeaseCreate):
    pass


class LeaseOut(BaseModel):
    id: int
    property_id: int
    tenant_id: int
    parent_lease_id: Optional[int] = None
    lease_type: str
    start_date: date
    end_date: Optional[date] = None
    security_deposit_amount: Optional[Decimal] = None
    security_deposit_date: Optional[date] = None
    is_active: bool
    created_at: Optional[datetime] = None
    # Computed read-only fields
    is_amendment: bool = False
    next_irl_revision_date: Optional[date] = None
    notice_period_open: bool = False
    # Rent values — all read from rent_revisions
    initial_monthly_rent: Optional[Decimal] = None
    initial_monthly_charges: Optional[Decimal] = None
    initial_monthly_total: Optional[Decimal] = None
    current_monthly_rent: Optional[Decimal] = None
    current_monthly_charges: Optional[Decimal] = None
    current_monthly_total: Optional[Decimal] = None
    model_config = {"from_attributes": True}


class LeaseDetailOut(LeaseOut):
    property: PropertyOut
    tenant: TenantOut
    parent_lease: Optional["LeaseSummary"] = None
    amendments: list["LeaseSummary"] = []


class LeaseSummary(BaseModel):
    """Compact lease representation used inside LeaseDetailOut for the
    parent/amendments links — avoids deep recursion."""
    id: int
    tenant_first_name: str
    tenant_last_name: str
    start_date: date
    end_date: Optional[date] = None
    current_monthly_total: Optional[Decimal] = None
    is_active: bool


LeaseDetailOut.model_rebuild()


# ── Rent revisions ────────────────────────────────────────────────────────────

REVISION_REASONS = ("initial", "irl_revision", "amicable", "other")


class RentRevisionCreate(BaseModel):
    effective_from: date
    monthly_rent: Decimal
    monthly_charges: Decimal = Decimal("0")
    reason: str = "irl_revision"

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v):
        if v not in REVISION_REASONS:
            raise ValueError(f"reason must be one of {REVISION_REASONS}")
        return v


class RentRevisionOut(BaseModel):
    id: int
    lease_id: int
    effective_from: date
    monthly_rent: Decimal
    monthly_charges: Decimal
    reason: str
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── Payment ───────────────────────────────────────────────────────────────────

class PaymentCreate(BaseModel):
    lease_id: int
    year: int
    month: int
    expected_amount: Decimal
    received_amount: Decimal = Decimal("0")
    payment_date: Optional[date] = None
    notes: Optional[str] = None


class PaymentUpdate(BaseModel):
    received_amount: Decimal
    payment_date: Optional[date] = None
    notes: Optional[str] = None


class PaginatedPaymentsOut(BaseModel):
    """Paginated envelope for GET /api/payments.

    `total` is the total number of rows that match the filters (not the
    page slice), so the frontend can render an accurate pagination bar
    without a second count request."""
    items: list["PaymentOut"]
    total: int
    page: int
    page_size: int


class PaymentOut(BaseModel):
    id: int
    lease_id: int
    year: int
    month: int
    expected_amount: Decimal
    received_amount: Decimal
    payment_date: Optional[date]
    status: str
    outstanding_balance: Decimal
    notes: Optional[str]
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


PaginatedPaymentsOut.model_rebuild()


class ExpectedAmountOut(BaseModel):
    lease_id: int
    year: int
    month: int
    expected_amount: Decimal
    monthly_rent: Decimal
    monthly_charges: Decimal
    revision_effective_from: Optional[date] = None


# ── Charges Regularization ────────────────────────────────────────────────────

class ChargesCreate(BaseModel):
    lease_id: int
    year: int
    total_actual_charges: Decimal
    total_provisions_collected: Decimal
    notes: Optional[str] = None


class ChargesUpdate(BaseModel):
    total_actual_charges: Decimal
    total_provisions_collected: Decimal
    notes: Optional[str] = None


class ChargesOut(BaseModel):
    id: int
    lease_id: int
    year: int
    total_actual_charges: Decimal
    total_provisions_collected: Decimal
    balance: Decimal
    notes: Optional[str]
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── Document ──────────────────────────────────────────────────────────────────

class DocumentOut(BaseModel):
    id: int
    lease_id: int
    type: str
    file_name: str
    upload_date: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── Procedure ─────────────────────────────────────────────────────────────────

PROCEDURE_TYPES = ("commandement_payer",)
PROCEDURE_STATUSES = ("in_progress", "paid", "expired_unpaid", "cancelled")


class ProcedureCreate(BaseModel):
    lease_id: int
    parent_procedure_id: Optional[int] = None
    procedure_type: str = "commandement_payer"
    notification_date: date
    # Optional — when omitted, server fills with notification_date + 2 months
    # for procedure_type='commandement_payer'.
    deadline_date: Optional[date] = None
    amount_rent: Decimal = Decimal("0")
    amount_fees: Decimal = Decimal("0")
    amount_other: Decimal = Decimal("0")
    bailiff_name: Optional[str] = None
    act_reference: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("procedure_type")
    @classmethod
    def _ptype(cls, v):
        if v not in PROCEDURE_TYPES:
            raise ValueError(f"procedure_type must be one of {PROCEDURE_TYPES}")
        return v


class ProcedureUpdate(BaseModel):
    notification_date: Optional[date] = None
    deadline_date: Optional[date] = None
    amount_rent: Optional[Decimal] = None
    amount_fees: Optional[Decimal] = None
    amount_other: Optional[Decimal] = None
    bailiff_name: Optional[str] = None
    act_reference: Optional[str] = None
    notes: Optional[str] = None


class ProcedureAttachedPayment(BaseModel):
    """A payment counted toward a procedure, with the source of the link."""
    payment: PaymentOut
    source: str  # 'auto' (date window) or 'manual' (explicit attach)


class ProcedureOut(BaseModel):
    id: int
    lease_id: int
    parent_procedure_id: Optional[int] = None
    procedure_type: str
    notification_date: date
    deadline_date: date
    amount_rent: Decimal
    amount_fees: Decimal
    amount_other: Decimal
    status: str  # recomputed at read time, never trusted from the row
    bailiff_name: Optional[str] = None
    act_reference: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Derived
    total_due: Decimal = Decimal("0")
    total_paid: Decimal = Decimal("0")
    remaining_due: Decimal = Decimal("0")
    days_remaining: Optional[int] = None  # negative if past deadline
    attached_payments_count: int = 0
    model_config = {"from_attributes": True}


class ProcedureDetailOut(ProcedureOut):
    attached_payments: list[ProcedureAttachedPayment] = []


class ProcedurePaymentAttach(BaseModel):
    payment_id: int


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    properties_total: int
    active_leases: int
    current_month_paid: int
    current_month_partial: int
    current_month_unpaid: int
    total_expected: Decimal
    total_received: Decimal
    # Sum of outstanding balances for the CURRENT month only, across all
    # active leases. Same value as the v2.0 `total_outstanding`.
    total_outstanding_current_month: Decimal = Decimal("0")
    # Sum of outstanding balances across ALL months (past + present) and
    # all active leases. This is the real total debt owed to the landlord.
    total_outstanding_all_months: Decimal = Decimal("0")
    # Backwards-compat alias — equal to total_outstanding_current_month.
    # Older clients still read this field; new UI reads the two named
    # fields above.
    total_outstanding: Decimal = Decimal("0")
    # Procedures (commandement de payer) overview.
    cdp_active_count: int = 0       # status=in_progress, all deadlines
    cdp_alerts_count: int = 0       # in_progress AND 0 <= days_remaining <= 7
    cdp_expired_unpaid_count: int = 0  # past deadline, not paid/cancelled


class LeaseRow(BaseModel):
    """One row of the dashboard — represents either an active lease or a
    vacant property (lease_id is None for vacant rows)."""
    property_id: int
    property_name: str
    property_type: str
    address: str
    lease_id: Optional[int] = None
    tenant_name: Optional[str] = None
    monthly_rent: Optional[Decimal] = None
    monthly_charges: Optional[Decimal] = None
    monthly_total: Optional[Decimal] = None
    current_payment: Optional[dict] = None
    # Current-month outstanding (kept for backwards compatibility with the
    # old "Solde dû" column).
    outstanding: Decimal = Decimal("0")
    # All-months outstanding for this lease — sum of every payment's
    # outstanding_balance where status in ('unpaid','partial').
    outstanding_total: Decimal = Decimal("0")
    outstanding_months_count: int = 0
    irl_alert: bool = False
    notice_alert: bool = False
    overdue_alert: bool = False


class DashboardOut(BaseModel):
    stats: DashboardStats
    rows: list[LeaseRow]


# ── Audit log ─────────────────────────────────────────────────────────────────

AUDIT_ACTIONS = ("create", "update", "delete", "export", "login", "login_failed")
AUDIT_ENTITY_TYPES = (
    "property", "lease", "tenant", "payment", "rent_revision",
    "charge_regularization", "document", "user", "group", "audit_log",
    "auth", "procedure",
)


class AuditLogOut(BaseModel):
    id: int
    created_at: datetime
    user_id: Optional[int] = None
    user_display_name: str
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    entity_label: Optional[str] = None
    before: Optional[dict] = None
    after: Optional[dict] = None
    ip_address: Optional[str] = None
    model_config = {"from_attributes": True}


# ── Bulk payment entry ────────────────────────────────────────────────────────

class BulkPaymentRow(BaseModel):
    year: int
    month: int
    received_amount: Decimal = Decimal("0")
    notes: Optional[str] = None


class BulkPaymentCreate(BaseModel):
    lease_id: int
    rows: list[BulkPaymentRow]


class BulkPaymentPreviewQuery(BaseModel):
    lease_id: int
    from_year: int
    from_month: int
    to_year: int
    to_month: int


class BulkPaymentPreviewRow(BaseModel):
    year: int
    month: int
    expected_amount: Decimal
    has_existing: bool


class BulkPaymentPreviewOut(BaseModel):
    lease_id: int
    rows: list[BulkPaymentPreviewRow]


class BulkPaymentResult(BaseModel):
    created_count: int
    total_expected: Decimal
    total_received: Decimal
    total_outstanding: Decimal
    payments: list[PaymentOut] = []
