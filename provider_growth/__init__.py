"""Provider Growth CRM for owner-operated profile workflows.

Compliance boundary: this package stores local lead records, content versions,
manual message drafts, experiment metrics, and audit receipts for accounts the
operator owns or is authorized to manage. It does not bypass access controls or
send messages without explicit human approval.
"""

__all__ = [
    "db",
    "receipts",
    "visitors",
    "messages",
    "profile_content",
    "experiments",
]
