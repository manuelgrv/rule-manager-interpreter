CREATE TABLE `clients` (
	`client_id` integer PRIMARY KEY NOT NULL,
	`age` integer NOT NULL,
	`country` text NOT NULL,
	`customer_segment` text NOT NULL,
	`account_status` text NOT NULL,
	`monthly_income` real,
	`employment_status` text NOT NULL,
	`months_employed` integer NOT NULL,
	`credit_score` integer,
	`current_debt` real NOT NULL,
	`credit_utilization` real,
	`delinquency_count` integer NOT NULL,
	`tenure_months` integer NOT NULL,
	`products_count` integer NOT NULL,
	`channel_preference` text NOT NULL,
	`has_mortgage` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_clients_segment` ON `clients` (`customer_segment`);--> statement-breakpoint
CREATE INDEX `idx_clients_credit_income` ON `clients` (`credit_score`,`monthly_income`);--> statement-breakpoint
CREATE TABLE `published_rules` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`rule_id` text NOT NULL,
	`name` text NOT NULL,
	`version` integer NOT NULL,
	`author` text NOT NULL,
	`source_language` text NOT NULL,
	`source` text NOT NULL,
	`dsl_json` text NOT NULL,
	`summary_json` text NOT NULL,
	`status` text DEFAULT 'PUBLISHED' NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_rules_rule_version` ON `published_rules` (`rule_id`,`version`);