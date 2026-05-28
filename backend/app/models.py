from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    Boolean, Column, Date, ForeignKey, Integer, Numeric,
    String, Table, Text, UniqueConstraint, DateTime, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .database import Base


# Association tables (composite PKs, no extra payload beyond created_at)
user_groups = Table(
    "user_groups",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

group_properties = Table(
    "group_properties",
    Base.metadata,
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    Column("property_id", Integer, ForeignKey("properties.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)


class User(Base):
    __tablename__ = "users"
    id                    = Column(Integer, primary_key=True)
    username              = Column(String(50), unique=True, nullable=False)
    password_hash         = Column(String(255), nullable=False)
    force_password_change = Column(Boolean, default=True)
    role                  = Column(String(20), nullable=False, default="user")
    is_active             = Column(Boolean, nullable=False, default=True)
    email                 = Column(String(200))
    created_at            = Column(DateTime(timezone=True), server_default=func.now())

    profile = relationship(
        "UserProfile", uselist=False, back_populates="user",
        cascade="all, delete-orphan",
    )
    groups = relationship("Group", secondary=user_groups, back_populates="users")


class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id              = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    landlord_name        = Column(String(200), default="")
    landlord_address     = Column(Text, default="")
    landlord_phone       = Column(String(20), default="")
    landlord_email       = Column(String(200), default="")
    signature_encrypted  = Column(Text)  # base64(nonce || ciphertext+tag), AES-256-GCM
    updated_at           = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="profile")


class Group(Base):
    __tablename__ = "groups"
    id          = Column(Integer, primary_key=True)
    name        = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    users      = relationship("User",     secondary=user_groups,      back_populates="groups")
    properties = relationship("Property", secondary=group_properties, back_populates="groups")


class Property(Base):
    __tablename__ = "properties"
    id              = Column(Integer, primary_key=True)
    name            = Column(String(100), nullable=False)
    type            = Column(String(20), nullable=False)
    address_street  = Column(String(200), nullable=False)
    address_city    = Column(String(100), nullable=False)
    address_zip     = Column(String(10), nullable=False)
    address_country = Column(String(100), nullable=False, default="France")
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    groups = relationship("Group", secondary=group_properties, back_populates="properties")


class Tenant(Base):
    __tablename__ = "tenants"
    id             = Column(Integer, primary_key=True)
    first_name     = Column(String(100), nullable=False)
    last_name      = Column(String(100), nullable=False)
    email          = Column(String(200))
    phone          = Column(String(20))
    guarantor_name = Column(String(200))
    created_at     = Column(DateTime(timezone=True), server_default=func.now())


class Lease(Base):
    __tablename__ = "leases"
    id                      = Column(Integer, primary_key=True)
    property_id             = Column(Integer, ForeignKey("properties.id"), nullable=False)
    tenant_id               = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    parent_lease_id         = Column(Integer, ForeignKey("leases.id", ondelete="SET NULL"))
    lease_type              = Column(String(20), nullable=False, default="unfurnished")
    start_date              = Column(Date, nullable=False)
    end_date                = Column(Date)
    security_deposit_amount = Column(Numeric(10, 2))
    security_deposit_date   = Column(Date)
    is_active               = Column(Boolean, default=True)
    created_at              = Column(DateTime(timezone=True), server_default=func.now())
    # Rent and charges are NOT stored on the lease — they live in
    # rent_revisions. See app.lease_rules for the access helpers.


class RentRevision(Base):
    __tablename__ = "rent_revisions"
    __table_args__ = (UniqueConstraint("lease_id", "effective_from"),)
    id              = Column(Integer, primary_key=True)
    lease_id        = Column(Integer, ForeignKey("leases.id", ondelete="CASCADE"), nullable=False)
    effective_from  = Column(Date, nullable=False)
    monthly_rent    = Column(Numeric(10, 2), nullable=False)
    monthly_charges = Column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    reason          = Column(String(20), nullable=False, default="initial")
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("lease_id", "year", "month"),)
    id                  = Column(Integer, primary_key=True)
    lease_id            = Column(Integer, ForeignKey("leases.id"), nullable=False)
    year                = Column(Integer, nullable=False)
    month               = Column(Integer, nullable=False)
    expected_amount     = Column(Numeric(10, 2), nullable=False)
    received_amount     = Column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    payment_date        = Column(Date)
    status              = Column(String(20), nullable=False, default="unpaid")
    outstanding_balance = Column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    notes               = Column(Text)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())


class ChargesRegularization(Base):
    __tablename__ = "charges_regularizations"
    __table_args__ = (UniqueConstraint("lease_id", "year"),)
    id                         = Column(Integer, primary_key=True)
    lease_id                   = Column(Integer, ForeignKey("leases.id"), nullable=False)
    year                       = Column(Integer, nullable=False)
    total_actual_charges       = Column(Numeric(10, 2), nullable=False)
    total_provisions_collected = Column(Numeric(10, 2), nullable=False)
    balance                    = Column(Numeric(10, 2), nullable=False)
    notes                      = Column(Text)
    created_at                 = Column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    id          = Column(Integer, primary_key=True)
    lease_id    = Column(Integer, ForeignKey("leases.id"), nullable=False)
    type        = Column(String(20), nullable=False)
    file_name   = Column(String(255), nullable=False)
    stored_path = Column(String(500), nullable=False)
    upload_date = Column(DateTime(timezone=True), server_default=func.now())


class Procedure(Base):
    __tablename__ = "procedures"
    id                  = Column(Integer, primary_key=True)
    lease_id            = Column(Integer, ForeignKey("leases.id", ondelete="CASCADE"), nullable=False)
    parent_procedure_id = Column(Integer, ForeignKey("procedures.id", ondelete="SET NULL"))
    procedure_type      = Column(String(40), nullable=False, default="commandement_payer")
    notification_date   = Column(Date, nullable=False)
    deadline_date       = Column(Date, nullable=False)
    amount_rent         = Column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    amount_fees         = Column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    amount_other        = Column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    status              = Column(String(20), nullable=False, default="in_progress")
    bailiff_name        = Column(Text)
    act_reference       = Column(Text)
    notes               = Column(Text)
    created_at          = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ProcedurePayment(Base):
    """Manual association of a Payment to a Procedure — used when a payment
    received outside the [notification, deadline] window must still count
    toward solving the procedure (typical case: rent paid between the day
    the landlord requested the act and the day the bailiff actually served
    it). Auto-imputation by date range stays implicit and is computed at
    read time; this table only stores extras."""
    __tablename__ = "procedure_payments"
    procedure_id = Column(Integer, ForeignKey("procedures.id", ondelete="CASCADE"), primary_key=True)
    payment_id   = Column(Integer, ForeignKey("payments.id",   ondelete="CASCADE"), primary_key=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AuditLog(Base):
    """Append-only audit trail.

    Application code MUST NOT issue UPDATE or DELETE on this table outside
    the dedicated admin-only "Supprimer les logs" action; routine writes go
    through `app.audit_log.log_event`. `user_display_name` and
    `entity_label` are *snapshots* at the time of the event so logs remain
    readable even after the underlying user or entity is deleted.
    """
    __tablename__ = "audit_logs"
    id                = Column(Integer, primary_key=True)
    created_at        = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    user_id           = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_display_name = Column(Text, nullable=False, default="system")
    action            = Column(String(20), nullable=False)
    entity_type       = Column(String(40), nullable=False)
    entity_id         = Column(Text)
    entity_label      = Column(Text)
    before            = Column(JSONB)
    after             = Column(JSONB)
    ip_address        = Column(Text)
