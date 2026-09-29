# Data model

## M0

M0 contains no GTM domain model.

The baseline Alembic revision exists to establish ordered, repeatable schema evolution. Applying it
creates Alembic's own `alembic_version` marker and no artificial application tables.

Database readiness is validated with `SELECT 1`; it does not infer that domain data exists.

## M1 boundary

The first domain migration will start the smallest canonical model required for one traceable
synthetic vertical slice. Its tables and constraints will be reviewed against the master brief
before implementation.

