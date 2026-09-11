"""
ReliefOS Authentication & Identity Service — Production Hardening

Provides secure password hashing (PBKDF2-HMAC-SHA256 with 600,000 rounds),
tamper-evident session token minting/verification, and user authentication lifecycle.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import TYPE_CHECKING, Any, Optional, Tuple

from agent.auth.models import AuthenticatedPrincipal, OrganizationMembership, User, UserRole

if TYPE_CHECKING:
    from agent.data.repository import Repository

logger = logging.getLogger("reliefos.auth")

PBKDF2_ROUNDS = 600_000
DEFAULT_SESSION_DURATION = 86_400  # 24 hours


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using PBKDF2-HMAC-SHA256 with a 16-byte random salt.
    Format: pbkdf2:sha256:<rounds>$<salt_hex>$<hash_hex>
    """
    if not password:
        raise ValueError("Password cannot be empty")
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2:sha256:{PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a plaintext password against a stored PBKDF2-HMAC-SHA256 hash.
    Constant-time comparison protects against timing attacks.
    """
    if not password or not password_hash:
        return False
    try:
        parts = password_hash.split("$")
        if len(parts) != 3:
            return False
        algo_info, salt_hex, hash_hex = parts
        _, _, rounds_str = algo_info.split(":")
        rounds = int(rounds_str)
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)

        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
        return hmac.compare_digest(dk, expected_hash)
    except Exception as e:
        logger.warning(f"Password verification error: {e}")
        return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data_str: str) -> bytes:
    padding = 4 - (len(data_str) % 4)
    if padding != 4:
        data_str += "=" * padding
    return base64.urlsafe_b64decode(data_str.encode("ascii"))


def create_session_token(
    user_id: str,
    username: str,
    secret_key: str,
    expires_in_seconds: int = DEFAULT_SESSION_DURATION,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """
    Create a tamper-evident signed token (header.payload.signature).
    """
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "iat": now,
        "exp": now + expires_in_seconds,
        "jti": secrets.token_hex(8),
    }
    if extra_claims:
        payload.update(extra_claims)

    hdr_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    pay_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{hdr_b64}.{pay_b64}".encode("ascii")
    sig = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)

    return f"{hdr_b64}.{pay_b64}.{sig_b64}"


def verify_session_token(token: str, secret_key: str) -> Optional[dict[str, Any]]:
    """
    Verify signature and expiration of a session token.
    Returns the payload dictionary if valid, None otherwise.
    """
    if not token or not secret_key:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        hdr_b64, pay_b64, sig_b64 = parts

        signing_input = f"{hdr_b64}.{pay_b64}".encode("ascii")
        expected_sig = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
        provided_sig = _b64url_decode(sig_b64)

        if not hmac.compare_digest(expected_sig, provided_sig):
            logger.debug("Token signature mismatch")
            return None

        payload_bytes = _b64url_decode(pay_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        # Verify expiration
        exp = payload.get("exp")
        if exp is not None and time.time() > exp:
            logger.debug("Token expired")
            return None

        return payload
    except Exception as e:
        logger.debug(f"Token verification failed: {e}")
        return None


class AuthService:
    """
    Coordinates user registration, credential verification, and principal construction.
    """

    def __init__(self, repository: Repository, secret_key: Optional[str] = None):
        self.repository = repository
        self.secret_key = secret_key or os.environ.get("RELIEFOS_SECRET_KEY", "reliefos-default-secret-key-change-in-prod")

    def register_user(
        self,
        username: str,
        email: str,
        password: str,
        full_name: str = "",
        initial_org_id: Optional[str] = None,
        initial_role: UserRole | str = UserRole.ORG_OPERATOR,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Tuple[User, Optional[OrganizationMembership]]:
        """
        Create a new user with hashed password and optionally assign initial org membership.
        """
        if not username or not password:
            raise ValueError("Username and password are required")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")

        # Check uniqueness
        if self.repository.get_user_by_username(username):
            raise ValueError(f"Username '{username}' already exists")
        if email and self.repository.get_user_by_email(email):
            raise ValueError(f"Email '{email}' already registered")

        pw_hash = hash_password(password)
        user = User(
            username=username.strip(),
            email=email.strip().lower() if email else "",
            password_hash=pw_hash,
            full_name=full_name.strip(),
            metadata=metadata or {},
        )
        saved_user = self.repository.create_user(user)

        membership = None
        if initial_org_id:
            role_str = initial_role.value if isinstance(initial_role, UserRole) else str(initial_role)
            membership = OrganizationMembership(
                user_id=saved_user.id,
                organization_id=initial_org_id,
                role=role_str,
            )
            saved_membership = self.repository.create_membership(membership)
            membership = saved_membership

        return saved_user, membership

    def authenticate(self, username_or_email: str, password: str) -> Optional[User]:
        """
        Authenticate a user by username or email. Returns User if valid, None otherwise.
        """
        if not username_or_email or not password:
            return None

        user = self.repository.get_user_by_username(username_or_email.strip())
        if not user and "@" in username_or_email:
            user = self.repository.get_user_by_email(username_or_email.strip().lower())

        if not user or not user.is_active:
            return None

        if verify_password(password, user.password_hash):
            return user
        return None

    def get_principal(self, user_id: str) -> Optional[AuthenticatedPrincipal]:
        """
        Build an AuthenticatedPrincipal object containing user and all organization memberships.
        """
        user = self.repository.get_user_by_id(user_id)
        if not user or not user.is_active:
            return None

        memberships = self.repository.list_memberships_for_user(user_id)
        return AuthenticatedPrincipal(user=user, memberships=memberships)

    def create_token_for_user(self, user: User, expires_in: int = DEFAULT_SESSION_DURATION) -> str:
        return create_session_token(
            user_id=user.id,
            username=user.username,
            secret_key=self.secret_key,
            expires_in_seconds=expires_in,
        )

    def get_principal_from_token(self, token: str) -> Optional[AuthenticatedPrincipal]:
        payload = verify_session_token(token, self.secret_key)
        if not payload:
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        return self.get_principal(user_id)
