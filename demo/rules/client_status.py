decision(
    outcome=when(client.age < 18, "REJECT", when(client.account_status == "ACTIVE", "APPROVE", "REJECT")),
    reason=when(client.age < 18, "UNDERAGE", when(client.account_status == "ACTIVE", "ACTIVE_ADULT", "INACTIVE_ACCOUNT")),
    action=None,
)
