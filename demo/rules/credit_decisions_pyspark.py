def build_rule(clients, income, credit_profiles, F):
    return (
        clients.alias("c")
        .join(income.alias("i"), F.col("i.client_id") == F.col("c.client_id"), "left")
        .join(
            credit_profiles.alias("cp"),
            F.col("cp.client_id") == F.col("c.client_id"),
            "left",
        )
        .select(
            F.col("c.client_id").alias("client_id"),
            F.when(F.col("c.age") < F.lit(18), F.lit("REJECT"))
            .when(F.col("c.account_status") != F.lit("ACTIVE"), F.lit("REJECT"))
            .when(
                F.col("cp.credit_score").isNull() | F.col("i.monthly_income").isNull(),
                F.lit("REVIEW"),
            )
            .when(
                (F.col("cp.credit_score") >= F.lit(650))
                & (F.col("i.monthly_income") >= F.lit(4500))
                & (F.col("cp.credit_utilization") < F.lit(0.75)),
                F.lit("APPROVE"),
            )
            .otherwise(F.lit("REJECT"))
            .alias("outcome"),
            F.when(F.col("c.age") < F.lit(18), F.lit("UNDERAGE"))
            .when(
                F.col("c.account_status") != F.lit("ACTIVE"),
                F.lit("INACTIVE_ACCOUNT"),
            )
            .when(
                F.col("cp.credit_score").isNull() | F.col("i.monthly_income").isNull(),
                F.lit("MISSING_DATA"),
            )
            .when(
                (F.col("cp.credit_score") >= F.lit(650))
                & (F.col("i.monthly_income") >= F.lit(4500))
                & (F.col("cp.credit_utilization") < F.lit(0.75)),
                F.lit("POLICY_PASSED"),
            )
            .otherwise(F.lit("POLICY_FAILED"))
            .alias("reason"),
            F.when(
                F.col("cp.credit_score").isNull() | F.col("i.monthly_income").isNull(),
                F.lit("MANUAL_REVIEW"),
            )
            .otherwise(F.lit(None))
            .alias("action"),
        )
        .orderBy(F.col("client_id").asc_nulls_last())
    )
