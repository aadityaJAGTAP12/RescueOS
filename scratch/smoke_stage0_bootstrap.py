"""
ReliefOS Smoke Stage 0 — synthetic actor bootstrap.

Creates the synthetic organizations and users used by every later stage.
Everything is tagged with the run tag. Runs BEFORE the production server is
started (uses the service layer directly with PBKDF2 hashing; the API
deliberately forbids self-service org binding when AUTH_ENFORCED=true).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from smoke_lib import (  # noqa: E402
    ROOT, HERE, new_tag, save_manifest, check, finish_stage,
)

# Load .env so the expired-token test in stage1 signs with the same secret
# the production server uses.
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(ROOT, ".env"))

os.environ.pop("RELIEFOS_MEMORY", None)
os.environ.setdefault("DATABASE_URL", "postgresql://reliefos:reliefos@localhost:5433/reliefos")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(ROOT, ".env"))

from agent.data.repository import get_repository  # noqa: E402
from agent.data.models import Organization  # noqa: E402
from agent.auth.service import AuthService  # noqa: E402
from agent.auth.models import UserRole  # noqa: E402

tag = new_tag()
repo = get_repository()
print(f"repository backend: {type(repo).__name__}")
check(type(repo).__name__ == "PostgresRepository", "stage0 runs against PostgreSQL")

auth = AuthService(repository=repo, secret_key=os.environ.get(
    "RELIEFOS_SECRET_KEY", "reliefos-default-secret-key-change-in-prod"))

# --- Organizations ---------------------------------------------------------
org_alpha = f"org_alpha_{tag}"
org_beta = f"org_beta_{tag}"
for oid, name in ((org_alpha, "Smoke Alpha NGO"), (org_beta, "Smoke Beta NGO")):
    if not repo.get_organization(oid):
        repo.create_organization(Organization(
            id=oid, name=name, organization_type="ngo",
            description=f"Synthetic smoke org {tag}"))

# --- Users ------------------------------------------------------------------
# alpha_admin: ORG_ADMIN in alpha (can approve publications)
# alpha_op:    ORG_OPERATOR in alpha (can publish offers, evaluate)
# beta_admin:  ORG_ADMIN in beta  (adversarial cross-org attempts)
# netop:       NETWORK_OPERATOR (coordination proposals, audit reads)
def _mkuser(prefix, org_id, role):
    user, membership = auth.register_user(
        username=f"{prefix}_{tag}",
        email=f"{prefix}_{tag}@smoke.test",
        password="Sm0keTest-Passw0rd!",
        full_name=f"Smoke {prefix}",
        initial_org_id=org_id,
        initial_role=role,
    )
    return user, membership

alpha_admin, _ = _mkuser("alpha_admin", org_alpha, UserRole.ORG_ADMIN)
alpha_op, _ = _mkuser("alpha_op", org_alpha, UserRole.ORG_OPERATOR)
beta_admin, _ = _mkuser("beta_admin", org_beta, UserRole.ORG_ADMIN)
netop, _ = _mkuser("netop", org_alpha, UserRole.NETWORK_OPERATOR)

save_manifest({
    "tag": tag,
    "org_alpha": org_alpha,
    "org_beta": org_beta,
    "users": {
        "alpha_admin": {"username": alpha_admin.username, "id": alpha_admin.id, "role": "ORG_ADMIN"},
        "alpha_op": {"username": alpha_op.username, "id": alpha_op.id, "role": "ORG_OPERATOR"},
        "beta_admin": {"username": beta_admin.username, "id": beta_admin.id, "role": "ORG_ADMIN"},
        "netop": {"username": netop.username, "id": netop.id, "role": "NETWORK_OPERATOR"},
    },
    "password": "Sm0keTest-Passw0rd!",
})

print(f"org_alpha={org_alpha}")
print(f"org_beta={org_beta}")
print(f"users: alpha_admin, alpha_op, beta_admin, netop (tag {tag})")
finish_stage("stage0_bootstrap")
