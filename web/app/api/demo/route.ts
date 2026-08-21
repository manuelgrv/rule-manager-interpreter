import { env } from "cloudflare:workers";

export const runtime = "edge";

type Condition = { field: string; operator: string; value: string | number };
type DSL = Record<string, any>;

const allowedFields: Record<string, "number" | "text"> = {
  client_id: "number", age: "number", country: "text", customer_segment: "text", account_status: "text",
  monthly_income: "number", employment_status: "text", months_employed: "number", credit_score: "number",
  current_debt: "number", credit_utilization: "number", delinquency_count: "number", tenure_months: "number",
  products_count: "number", has_mortgage: "number",
};
const allowedOperators = new Set([">=", "<=", ">", "<", "=", "!="]);

async function ensureDatabase() {
  const db = env.DB;
  await db.batch([
    db.prepare(`CREATE TABLE IF NOT EXISTS clients (
      client_id INTEGER PRIMARY KEY, age INTEGER NOT NULL, country TEXT NOT NULL, customer_segment TEXT NOT NULL,
      account_status TEXT NOT NULL, monthly_income REAL, employment_status TEXT NOT NULL, months_employed INTEGER NOT NULL,
      credit_score INTEGER, current_debt REAL NOT NULL, credit_utilization REAL, delinquency_count INTEGER NOT NULL,
      tenure_months INTEGER NOT NULL, products_count INTEGER NOT NULL, channel_preference TEXT NOT NULL, has_mortgage INTEGER NOT NULL
    )`),
    db.prepare(`CREATE TABLE IF NOT EXISTS published_rules (
      id INTEGER PRIMARY KEY AUTOINCREMENT, rule_id TEXT NOT NULL, name TEXT NOT NULL, version INTEGER NOT NULL,
      author TEXT NOT NULL, source_language TEXT NOT NULL, source TEXT NOT NULL, dsl_json TEXT NOT NULL,
      summary_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PUBLISHED', created_at TEXT NOT NULL,
      UNIQUE(rule_id, version)
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_clients_segment ON clients(customer_segment)"),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_clients_credit_income ON clients(credit_score, monthly_income)"),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_rules_rule_version ON published_rules(rule_id, version DESC)"),
  ]);
  const count = await db.prepare("SELECT COUNT(*) AS total FROM clients").first<{ total: number }>();
  if (!count?.total) {
    await db.prepare(`WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 10000)
      INSERT INTO clients
      SELECT n,
        18 + (n * 17 % 58),
        CASE n % 10 WHEN 0 THEN 'CO' WHEN 1 THEN 'CL' ELSE 'PE' END,
        CASE n % 10 WHEN 0 THEN 'PYME' WHEN 1 THEN 'PYME' WHEN 2 THEN 'PREMIUM' WHEN 3 THEN 'PREMIUM' ELSE 'RETAIL' END,
        CASE WHEN n % 19 = 0 THEN 'INACTIVE' ELSE 'ACTIVE' END,
        CASE WHEN n % 31 = 0 THEN NULL ELSE ROUND(1200 + (n * 137 % 16800) + ((n % 7) * 83.5), 2) END,
        CASE n % 8 WHEN 0 THEN 'SELF_EMPLOYED' WHEN 1 THEN 'INDEPENDENT' WHEN 2 THEN 'RETIRED' ELSE 'EMPLOYED' END,
        n * 7 % 181,
        CASE WHEN n % 37 = 0 THEN NULL ELSE 430 + (n * 29 % 421) END,
        ROUND(n * 311 % 62000, 2),
        CASE WHEN n % 41 = 0 THEN NULL ELSE ROUND((n * 13 % 100) / 100.0, 2) END,
        n * 5 % 6,
        2 + (n * 11 % 238),
        1 + (n * 3 % 7),
        CASE n % 4 WHEN 0 THEN 'BRANCH' WHEN 1 THEN 'WEB' ELSE 'MOBILE' END,
        CASE WHEN n % 5 = 0 THEN 1 ELSE 0 END
      FROM seq`).run();
    await db.prepare("PRAGMA optimize").run();
  }
}

function slugify(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "regla-demo";
}

function normalizeConditions(input: unknown): Condition[] {
  if (!Array.isArray(input) || !input.length) throw new Error("La regla debe contener al menos una condición");
  return input.map((item: any) => {
    const field = String(item.field || "").replace(/^(c|i|cp)\./, "");
    const operator = String(item.operator || "");
    if (!allowedFields[field]) throw new Error(`La columna ${field || "indicada"} no pertenece al catálogo`);
    if (!allowedOperators.has(operator)) throw new Error(`El operador ${operator} no está permitido`);
    const raw = item.value;
    const value = allowedFields[field] === "number" ? Number(raw) : String(raw).replace(/^['"]|['"]$/g, "");
    if (allowedFields[field] === "number" && !Number.isFinite(value)) throw new Error(`El valor de ${field} debe ser numérico`);
    return { field, operator, value };
  });
}

function parseSource(source: string): Condition[] {
  if (!source.trim()) throw new Error("El script está vacío");
  if (/\b(drop|delete|update|insert|alter|create|grant|import|exec|eval)\b/i.test(source)) throw new Error("El script contiene una operación no permitida");
  const escapedFields = Object.keys(allowedFields).join("|");
  const regex = new RegExp(`(?:\\b(?:c|i|cp)\\.)?(${escapedFields})\\s*(>=|<=|!=|==|=|>|<)\\s*(?:lit\\()?['\"]?([A-Za-z0-9_.-]+)['\"]?\\)?`, "gi");
  const conditions: Condition[] = [];
  for (const match of source.matchAll(regex)) conditions.push({ field: match[1], operator: match[2] === "==" ? "=" : match[2], value: match[3] });
  if (!conditions.length) throw new Error("No se encontraron condiciones compatibles. Usa columnas del catálogo con operadores de comparación.");
  return normalizeConditions(conditions);
}

async function sha256(value: unknown) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
}

async function compile(name: string, language: string, source: string, requested: unknown) {
  const conditions = language === "visual" ? normalizeConditions(requested) : parseSource(source);
  const ruleId = slugify(name);
  const expression = { expr: "boolean", operator: "and", operands: conditions.map(condition => ({
    expr: "compare", operator: ({ ">=": "gte", "<=": "lte", ">": "gt", "<": "lt", "=": "eq", "!=": "neq" } as Record<string, string>)[condition.operator],
    left: { expr: "column", relation: "clients", name: condition.field, type: allowedFields[condition.field] === "number" ? "double" : "string" },
    right: { expr: "literal", type: allowedFields[condition.field] === "number" ? "double" : "string", value: condition.value },
  })) };
  const document: DSL = {
    dsl_version: "1.0",
    rule: { id: ruleId, version: 1, kind: "query", name, source_language: language },
    inputs: [{ source: "clients", catalog: "RDV", schema_version: "1" }],
    parameters: [],
    plan: { op: "project", input: { op: "scan", source: "clients", alias: "clients" }, columns: [
      { name: "client_id", value: { expr: "column", relation: "clients", name: "client_id", type: "int64" } },
      { name: "decision", value: { expr: "decision", outcome: { expr: "case", branches: [{ when: expression, then: { expr: "literal", type: "string", value: "APROBAR" } }], else: { expr: "literal", type: "string", value: "REVISAR" } }, reason: { expr: "literal", type: "string", value: "POLITICA_ELEGIBILIDAD" } } },
    ], conditions },
    output: { schema: [{ name: "client_id", type: "int64", nullable: false }, { name: "decision", type: "string", nullable: false }] },
    compiler: { name: "rule-manager-interpreter", version: "0.1.0-demo", deterministic: true },
  };
  document.integrity = { algorithm: "sha256", digest: await sha256(document) };
  return document;
}

async function validateDsl(dsl: DSL) {
  if (dsl?.dsl_version !== "1.0" || dsl?.plan?.op !== "project") throw new Error("El DSL no cumple el contrato 1.0");
  const integrity = dsl.integrity;
  const semantic = structuredClone(dsl); delete semantic.integrity;
  if (integrity?.algorithm !== "sha256" || integrity.digest !== await sha256(semantic)) throw new Error("La verificación de integridad del DSL falló");
  return normalizeConditions(dsl.plan.conditions);
}

function sqlPredicate(conditions: Condition[]) {
  const clauses: string[] = []; const values: unknown[] = [];
  for (const condition of conditions) { clauses.push(`\"${condition.field}\" ${condition.operator === "!=" ? "<>" : condition.operator} ?`); values.push(condition.value); }
  return { clause: clauses.join(" AND "), values };
}

export async function GET() {
  await ensureDatabase();
  const [count, sample, rules, distribution] = await Promise.all([
    env.DB.prepare("SELECT COUNT(*) AS total FROM clients").first<{ total: number }>(),
    env.DB.prepare("SELECT client_id, customer_segment, monthly_income, credit_score, delinquency_count FROM clients ORDER BY client_id LIMIT 8").all(),
    env.DB.prepare("SELECT id, rule_id, name, version, author, status, created_at FROM published_rules ORDER BY created_at DESC LIMIT 8").all(),
    env.DB.prepare("SELECT customer_segment AS label, COUNT(*) AS value FROM clients GROUP BY customer_segment ORDER BY value DESC").all(),
  ]);
  return Response.json({ total: count?.total || 0, fields: 15, sample: sample.results, rules: rules.results, distributions: distribution.results });
}

export async function POST(request: Request) {
  try {
    await ensureDatabase();
    const body = await request.json() as any;
    if (body.action === "compile") return Response.json({ dsl: await compile(String(body.name || "Regla demo"), String(body.language || "visual"), String(body.source || ""), body.conditions) });
    if (body.action === "execute") {
      const started = Date.now(); const conditions = await validateDsl(body.dsl); const predicate = sqlPredicate(conditions);
      const decision = `CASE WHEN ${predicate.clause} THEN 'APROBAR' ELSE 'REVISAR' END`;
      const summary = await env.DB.prepare(`SELECT decision, COUNT(*) AS count FROM (SELECT ${decision} AS decision FROM clients) GROUP BY decision ORDER BY decision`).bind(...predicate.values).all<any>();
      const rows = await env.DB.prepare(`SELECT client_id, monthly_income, credit_score, credit_utilization, ${decision} AS decision FROM clients ORDER BY client_id LIMIT 40`).bind(...predicate.values).all();
      const total = summary.results.reduce((sum: number, item: any) => sum + Number(item.count), 0);
      return Response.json({ rows: rows.results, summary: summary.results.map((item: any) => ({ decision: item.decision, count: Number(item.count), pct: Math.round(Number(item.count) / total * 1000) / 10 })), elapsed_ms: Date.now() - started });
    }
    if (body.action === "publish") {
      await validateDsl(body.dsl);
      const ruleId = String(body.dsl.rule.id); const latest = await env.DB.prepare("SELECT MAX(version) AS version FROM published_rules WHERE rule_id = ?").bind(ruleId).first<{ version: number | null }>();
      const version = Number(latest?.version || 0) + 1; const createdAt = new Date().toISOString();
      await env.DB.prepare("INSERT INTO published_rules(rule_id,name,version,author,source_language,source,dsl_json,summary_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)")
        .bind(ruleId, String(body.name), version, "riesgos.demo@banco.pe", String(body.language), String(body.source || "Diseñador visual"), JSON.stringify(body.dsl), JSON.stringify(body.summary), "PUBLISHED", createdAt).run();
      return Response.json({ rule_id: ruleId, name: body.name, version, created_at: createdAt });
    }
    return Response.json({ error: "Acción no reconocida" }, { status: 400 });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Error inesperado" }, { status: 400 });
  }
}
