# Failed Payments policy

P1. A failed payment is retried automatically 3 times over 7 days.
P2. Customers receive an email after each failed attempt.
P3. Access continues for a 7 day grace period after the first failure.
P4. After the grace period the account moves to read only mode.
P5. A payment method can be updated in Settings, then Billing, then Payment methods.
P6. Updating the card triggers an immediate retry of the outstanding invoice.
P7. Accounts in read only mode for 60 days are scheduled for deletion.
P8. Declines caused by the bank must be resolved with the bank; we cannot override them.
