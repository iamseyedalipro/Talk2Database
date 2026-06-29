"""Schema introspection, serialization, persistence and cost-aware selection.

The user-data schema is introspected once per import and stored as a snapshot,
then reused as a cacheable prompt prefix. For very large schemas only the tables
relevant to a question are sent. This is what keeps AI costs bounded.
"""
