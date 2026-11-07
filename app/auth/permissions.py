"""Role-based access control: which role may do what.

Routes depend on a *permission* ("review.decide"), never on a role name, so the policy
lives in this one table and can change without touching routers.
"""

from enum import StrEnum

from app.auth.models import Role


class Permission(StrEnum):
    NOTE_CREATE = "note.create"
    NOTE_READ = "note.read"
    REVIEW_QUEUE_READ = "review.queue.read"
    REVIEW_DECIDE = "review.decide"
    AUDIT_READ = "audit.read"
    SCHEDULE_SOLVE = "schedule.solve"
    SCHEDULE_READ = "schedule.read"
    WORKFORCE_READ = "workforce.read"


P = Permission
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    # Carers write notes from visits. Reading notes back needs object-level checks
    # (only their own notes), which arrive with the carer app in Tier 5.
    Role.CARER: frozenset({P.NOTE_CREATE}),
    # Coordinators run the day: log notes, decide flags, plan rotas. No attrition scores
    # (the model card limits those to managers) and no audit-log access.
    Role.COORDINATOR: frozenset(
        {P.NOTE_CREATE, P.NOTE_READ, P.REVIEW_QUEUE_READ, P.REVIEW_DECIDE}
        | {P.SCHEDULE_SOLVE, P.SCHEDULE_READ}
    ),
    # Managers oversee: read everything operational, the audit trail and workforce risk.
    # They don't decide flags or run the solver (separation of duties: oversight vs action).
    Role.MANAGER: frozenset(
        {P.NOTE_READ, P.REVIEW_QUEUE_READ, P.AUDIT_READ, P.SCHEDULE_READ, P.WORKFORCE_READ}
    ),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]
