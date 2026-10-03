"""Shared read-only selection semantics for current materialized account state."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.models import AccountStateSnapshot, Workspace


def current_materialized_state_snapshot(
    session: Session,
    *,
    workspace: Workspace,
    account_id: UUID,
    strategy_version_id: UUID,
) -> AccountStateSnapshot | None:
    """Select current persisted state without recomputation or materialization."""

    statement = select(AccountStateSnapshot).where(
        AccountStateSnapshot.workspace_id == workspace.workspace_id,
        AccountStateSnapshot.account_id == account_id,
        AccountStateSnapshot.strategy_version_id == strategy_version_id,
    )
    if workspace.demo_mode:
        if workspace.demo_as_of is None:
            raise RuntimeError("demo workspace requires demo_as_of")
        statement = statement.where(AccountStateSnapshot.state_as_of == workspace.demo_as_of)
        statement = statement.order_by(
            AccountStateSnapshot.computed_at.desc(),
            AccountStateSnapshot.state_snapshot_id.desc(),
        )
    else:
        statement = statement.order_by(
            AccountStateSnapshot.state_as_of.desc(),
            AccountStateSnapshot.computed_at.desc(),
            AccountStateSnapshot.state_snapshot_id.desc(),
        )
    return session.scalar(statement.limit(1))
