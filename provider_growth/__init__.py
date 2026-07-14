"""Provider Growth CRM for owner-operated profile workflows.

Compliance boundary: this package stores local engagement records, content
versions, manual draft queue items, policy decisions, outbox states, KPI events,
conversation receipts, and audit receipts for accounts the operator owns or is
authorized to manage. It does not bypass access controls or transmit messages
without explicit human approval.
"""

__all__ = [
    "db",
    "receipts",
    "engagement",
    "drafts",
    "policy",
    "outbox",
    "kpi",
    "profile_content",
    "experiments",
    "imac_relay",
]
