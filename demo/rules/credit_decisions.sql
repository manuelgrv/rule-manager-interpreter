SELECT
    c.client_id,
    CASE
        WHEN c.age < 18 THEN 'REJECT'
        WHEN c.account_status <> 'ACTIVE' THEN 'REJECT'
        WHEN cp.credit_score IS NULL OR i.monthly_income IS NULL THEN 'REVIEW'
        WHEN cp.credit_score >= 650
         AND i.monthly_income >= 4500
         AND cp.credit_utilization < 0.75 THEN 'APPROVE'
        ELSE 'REJECT'
    END AS outcome,
    CASE
        WHEN c.age < 18 THEN 'UNDERAGE'
        WHEN c.account_status <> 'ACTIVE' THEN 'INACTIVE_ACCOUNT'
        WHEN cp.credit_score IS NULL OR i.monthly_income IS NULL THEN 'MISSING_DATA'
        WHEN cp.credit_score >= 650
         AND i.monthly_income >= 4500
         AND cp.credit_utilization < 0.75 THEN 'POLICY_PASSED'
        ELSE 'POLICY_FAILED'
    END AS reason,
    CASE
        WHEN cp.credit_score IS NULL OR i.monthly_income IS NULL THEN 'MANUAL_REVIEW'
        ELSE NULL
    END AS action
FROM clients AS c
LEFT JOIN income AS i ON i.client_id = c.client_id
LEFT JOIN credit_profiles AS cp ON cp.client_id = c.client_id
ORDER BY c.client_id;
