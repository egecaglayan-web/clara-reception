"""Notifications use the same persistent email queue as patient replies."""


def handoff_body(sender, action, reason):
    # Never include the raw email, symptoms, or other patients' records.
    return ("Clara reception review required.\n"
            f"Patient email: {sender}\nRequest type: {action}\nHandoff reason: {reason}\n"
            "Please review the original conversation in the mailbox. No medical assessment was made.")


def incident_body(reference, reason):
    return ("Clara operations alert\n"
            f"Operation reference: {reference[:16]}\nReason: {reason}\n"
            "Check uncertain calendar or email operations before running them again.")
