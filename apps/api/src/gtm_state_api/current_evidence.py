"""One reusable eligibility rule for NEW materialization from canonical Evidence."""

from __future__ import annotations

from sqlalchemy import exists, or_, select
from sqlalchemy.sql.elements import ColumnElement

from gtm_state_api.models import Evidence, EvidenceSupersession


def current_evidence_condition() -> ColumnElement[bool]:
    """Legacy Evidence stays eligible; promoted replacements exclude old imports only."""
    return or_(
        Evidence.normalization_result_id.is_(None),
        ~exists(
            select(EvidenceSupersession.id).where(
                EvidenceSupersession.old_evidence_id == Evidence.id
            )
        ),
    )
