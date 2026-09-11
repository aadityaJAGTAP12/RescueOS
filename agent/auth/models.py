"""
ReliefOS Authentication & Authorization Models — Production Hardening

Defines domain contracts for users, organization memberships, roles,
and authenticated principals.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class UserRole(str, Enum):
    NETWORK_OPERATOR = "NETWORK_OPERATOR"  # Cross-network coordinator / system authority
    ORG_ADMIN = "ORG_ADMIN"                # Organization administrator (manage members & settings)
    ORG_OPERATOR = "ORG_OPERATOR"          # Organization responder (manage inventory, teams, missions, offers)
    ORG_VIEWER = "ORG_VIEWER"              # Organization read-only observer

    @classmethod
    def has_sufficient_role(cls, user_role: str | UserRole, required_role: str | UserRole) -> bool:
        """
        Check if user_role meets or exceeds required_role in the organizational hierarchy.
        NETWORK_OPERATOR has top-level authority.
        ORG_ADMIN > ORG_OPERATOR > ORG_VIEWER.
        """
        user_r = user_role.value if isinstance(user_role, UserRole) else str(user_role)
        req_r = required_role.value if isinstance(required_role, UserRole) else str(required_role)

        if user_r == cls.NETWORK_OPERATOR.value:
            return True

        hierarchy = {
            cls.ORG_VIEWER.value: 1,
            cls.ORG_OPERATOR.value: 2,
            cls.ORG_ADMIN.value: 3,
        }

        user_level = hierarchy.get(user_r, 0)
        req_level = hierarchy.get(req_r, 99)
        return user_level >= req_level


@dataclass
class User:
    """
    An authenticated human or machine user in ReliefOS.
    """
    id: str = field(default_factory=lambda: f"usr_{str(uuid.uuid4())[:12]}")
    username: str = ""
    email: str = ""
    password_hash: str = ""
    full_name: str = ""
    is_active: bool = True
    created_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    def to_dict(self, include_sensitive: bool = False) -> dict[str, Any]:
        d = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.metadata,
        }
        if include_sensitive:
            d["password_hash"] = self.password_hash
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> User:
        def _parse_dt(val):
            if val is None or isinstance(val, datetime):
                return val
            try:
                return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except Exception:
                return None

        return cls(
            id=data.get("id") or f"usr_{str(uuid.uuid4())[:12]}",
            username=data.get("username", ""),
            email=data.get("email", ""),
            password_hash=data.get("password_hash", ""),
            full_name=data.get("full_name", ""),
            is_active=bool(data.get("is_active", True)),
            created_at=_parse_dt(data.get("created_at")),
            metadata=data.get("metadata", {}),
        )


@dataclass
class OrganizationMembership:
    """
    Binding between a User and an Organization with an assigned role.
    """
    id: str = field(default_factory=lambda: f"mem_{str(uuid.uuid4())[:12]}")
    user_id: str = ""
    organization_id: str = ""
    role: str = UserRole.ORG_VIEWER.value
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "role": self.role if isinstance(self.role, str) else self.role.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrganizationMembership:
        def _parse_dt(val):
            if val is None or isinstance(val, datetime):
                return val
            try:
                return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except Exception:
                return None

        return cls(
            id=data.get("id") or f"mem_{str(uuid.uuid4())[:12]}",
            user_id=data.get("user_id", ""),
            organization_id=data.get("organization_id", ""),
            role=data.get("role", UserRole.ORG_VIEWER.value),
            created_at=_parse_dt(data.get("created_at")),
        )


@dataclass
class AuthenticatedPrincipal:
    """
    Resolved security context for an authenticated request.
    """
    user: User
    memberships: list[OrganizationMembership] = field(default_factory=list)

    @property
    def user_id(self) -> str:
        return self.user.id

    @property
    def username(self) -> str:
        return self.user.username

    @property
    def is_network_operator(self) -> bool:
        return any(m.role == UserRole.NETWORK_OPERATOR.value for m in self.memberships)

    def get_role_for_org(self, org_id: str) -> Optional[str]:
        if self.is_network_operator:
            return UserRole.NETWORK_OPERATOR.value
        for m in self.memberships:
            if m.organization_id == org_id:
                return m.role
        return None

    def has_org_access(self, org_id: str, required_role: str | UserRole = UserRole.ORG_VIEWER) -> bool:
        role = self.get_role_for_org(org_id)
        if not role:
            return False
        return UserRole.has_sufficient_role(role, required_role)
