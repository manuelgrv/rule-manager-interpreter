import { index, integer, real, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const clients = sqliteTable("clients", {
  clientId: integer("client_id").primaryKey(), age: integer("age").notNull(), country: text("country").notNull(),
  customerSegment: text("customer_segment").notNull(), accountStatus: text("account_status").notNull(), monthlyIncome: real("monthly_income"),
  employmentStatus: text("employment_status").notNull(), monthsEmployed: integer("months_employed").notNull(), creditScore: integer("credit_score"),
  currentDebt: real("current_debt").notNull(), creditUtilization: real("credit_utilization"), delinquencyCount: integer("delinquency_count").notNull(),
  tenureMonths: integer("tenure_months").notNull(), productsCount: integer("products_count").notNull(), channelPreference: text("channel_preference").notNull(), hasMortgage: integer("has_mortgage").notNull(),
}, table => [index("idx_clients_segment").on(table.customerSegment), index("idx_clients_credit_income").on(table.creditScore, table.monthlyIncome)]);

export const publishedRules = sqliteTable("published_rules", {
  id: integer("id").primaryKey({ autoIncrement: true }), ruleId: text("rule_id").notNull(), name: text("name").notNull(), version: integer("version").notNull(),
  author: text("author").notNull(), sourceLanguage: text("source_language").notNull(), source: text("source").notNull(), dslJson: text("dsl_json").notNull(),
  summaryJson: text("summary_json").notNull(), status: text("status").notNull().default("PUBLISHED"), createdAt: text("created_at").notNull(),
}, table => [uniqueIndex("idx_rules_rule_version").on(table.ruleId, table.version)]);
