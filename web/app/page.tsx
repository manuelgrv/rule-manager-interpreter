"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Condition = { field: string; operator: string; value: string };
type ClientRow = Record<string, string | number | null>;
type Rule = { id: number; rule_id: string; name: string; version: number; author: string; status: string; created_at: string };
type DemoData = { total: number; fields: number; sample: ClientRow[]; rules: Rule[]; distributions: { label: string; value: number }[] };

const fields = [
  ["monthly_income", "Ingreso mensual", "number"],
  ["credit_score", "Score crediticio", "number"],
  ["credit_utilization", "Utilización", "number"],
  ["delinquency_count", "Moras", "number"],
  ["months_employed", "Antigüedad laboral", "number"],
  ["age", "Edad", "number"],
  ["customer_segment", "Segmento", "text"],
  ["account_status", "Estado de cuenta", "text"],
  ["country", "País", "text"],
] as const;

const initialConditions: Condition[] = [
  { field: "monthly_income", operator: ">=", value: "4500" },
  { field: "credit_score", operator: ">=", value: "650" },
  { field: "delinquency_count", operator: "<=", value: "1" },
];

function Icon({ name }: { name: "spark" | "data" | "code" | "play" | "upload" | "check" | "plus" | "book" }) {
  const glyphs = { spark: "✦", data: "◫", code: "</>", play: "▶", upload: "⇧", check: "✓", plus: "+", book: "▤" };
  return <span className={`icon icon-${name}`} aria-hidden="true">{glyphs[name]}</span>;
}

export default function Home() {
  const [data, setData] = useState<DemoData | null>(null);
  const [mode, setMode] = useState<"visual" | "script">("visual");
  const [language, setLanguage] = useState<"sql" | "python">("sql");
  const [name, setName] = useState("Política de elegibilidad retail");
  const [conditions, setConditions] = useState<Condition[]>(initialConditions);
  const [source, setSource] = useState(`SELECT client_id, monthly_income, credit_score,
  CASE WHEN monthly_income >= 4500
        AND credit_score >= 650
        AND delinquency_count <= 1
       THEN 'APROBAR' ELSE 'REVISAR' END AS decision
FROM clients`);
  const [dsl, setDsl] = useState<Record<string, unknown> | null>(null);
  const [result, setResult] = useState<{ rows: ClientRow[]; summary: { decision: string; count: number; pct: number }[]; elapsed_ms: number } | null>(null);
  const [panel, setPanel] = useState<"dsl" | "results">("dsl");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    const response = await fetch("/api/demo");
    setData(await response.json());
  };

  useEffect(() => { load(); }, []);

  const api = async (body: Record<string, unknown>) => {
    const response = await fetch("/api/demo", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "No se pudo completar la operación");
    return payload;
  };

  const compile = async () => {
    setBusy("compile"); setNotice(""); setResult(null);
    try {
      const payload = await api({ action: "compile", name, language: mode === "visual" ? "visual" : language, source, conditions });
      setDsl(payload.dsl); setPanel("dsl"); setNotice("DSL generado y validado");
    } catch (error) { setNotice(error instanceof Error ? error.message : "Error al compilar"); }
    finally { setBusy(""); }
  };

  const execute = async () => {
    if (!dsl) return;
    setBusy("execute"); setNotice("");
    try {
      const payload = await api({ action: "execute", dsl });
      setResult(payload); setPanel("results"); setNotice(`Ejecución completada sobre ${data?.total.toLocaleString("es-PE")} clientes`);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Error al ejecutar"); }
    finally { setBusy(""); }
  };

  const publish = async () => {
    if (!dsl || !result) return;
    setBusy("publish"); setNotice("");
    try {
      const payload = await api({ action: "publish", name, source, language: mode === "visual" ? "visual" : language, dsl, summary: result.summary });
      setNotice(`${payload.name} v${payload.version} publicada en DDV`); await load();
    } catch (error) { setNotice(error instanceof Error ? error.message : "Error al publicar"); }
    finally { setBusy(""); }
  };

  const updateCondition = (index: number, patch: Partial<Condition>) => setConditions(current => current.map((condition, i) => i === index ? { ...condition, ...patch } : condition));
  const approval = result?.summary.find(item => item.decision === "APROBAR");
  const maxDistribution = useMemo(() => Math.max(...(data?.distributions.map(item => item.value) || [1])), [data]);

  return (
    <main>
      <header className="topbar">
        <div className="brand"><span className="brand-mark">◇</span><span>Rule Studio</span><em>Databricks App demo</em></div>
        <div className="top-actions"><span className="environment"><i />EDV · Experimentación</span><span className="avatar">MR</span></div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow"><Icon name="spark" /> POLÍTICAS DE RIESGO DETERMINÍSTICAS</p>
          <h1>Diseña una regla.<br /><span>Inspecciona cada decisión.</span></h1>
          <p className="hero-copy">Convierte criterios de negocio, SQL o Python en un DSL auditable. Prueba contra una cartera sintética y publica una versión lista para consumo.</p>
        </div>
        <div className="hero-stats">
          <div><strong>{data ? data.total.toLocaleString("es-PE") : "10.000"}</strong><span>clientes sintéticos</span></div>
          <div><strong>{data?.fields ?? 15}</strong><span>características</span></div>
          <div><strong>{data?.rules.length ?? 0}</strong><span>reglas publicadas</span></div>
        </div>
      </section>

      <section className="workspace">
        <aside className="stepper" aria-label="Flujo de la regla">
          {["Definir", "Compilar", "Ejecutar", "Publicar"].map((step, index) => <div key={step} className={index === 0 || dsl && index < 3 || result && index === 3 ? "step active" : "step"}><span>{index + 1}</span><b>{step}</b></div>)}
        </aside>

        <div className="builder card">
          <div className="card-heading">
            <div><p className="kicker">01 · DEFINICIÓN</p><h2>Nueva regla</h2></div>
            <label className="field rule-name"><span>Nombre de la regla</span><input value={name} onChange={event => setName(event.target.value)} /></label>
          </div>

          <div className="mode-tabs">
            <button className={mode === "visual" ? "selected" : ""} onClick={() => setMode("visual")}><Icon name="book" /> Diseñador visual</button>
            <button className={mode === "script" ? "selected" : ""} onClick={() => setMode("script")}><Icon name="code" /> SQL / Python</button>
          </div>

          {mode === "visual" ? (
            <div className="conditions">
              <div className="logic-line"><span>SI TODAS</span><div /></div>
              {conditions.map((condition, index) => {
                const type = fields.find(field => field[0] === condition.field)?.[2];
                return <div className="condition-row" key={`${condition.field}-${index}`}>
                  <span className="joiner">{index ? "Y" : ""}</span>
                  <select value={condition.field} onChange={event => updateCondition(index, { field: event.target.value })}>{fields.map(field => <option value={field[0]} key={field[0]}>{field[1]}</option>)}</select>
                  <select value={condition.operator} onChange={event => updateCondition(index, { operator: event.target.value })}>{[">=", "<=", ">", "<", "=", "!="].map(op => <option key={op}>{op}</option>)}</select>
                  <input type={type === "number" ? "number" : "text"} value={condition.value} onChange={event => updateCondition(index, { value: event.target.value })} />
                  <button className="remove" aria-label="Eliminar condición" onClick={() => setConditions(current => current.filter((_, i) => i !== index))}>×</button>
                </div>;
              })}
              <button className="add-condition" onClick={() => setConditions(current => [...current, { field: "age", operator: ">=", value: "18" }])}><Icon name="plus" /> Agregar condición</button>
              <div className="decision-strip"><span>ENTONCES</span><strong>APROBAR</strong><span>DE LO CONTRARIO</span><strong className="review">REVISAR</strong></div>
            </div>
          ) : (
            <div className="script-area">
              <div className="script-toolbar">
                <div className="language-toggle"><button className={language === "sql" ? "selected" : ""} onClick={() => setLanguage("sql")}>SQL</button><button className={language === "python" ? "selected" : ""} onClick={() => setLanguage("python")}>Python / PySpark</button></div>
                <button className="upload" onClick={() => fileRef.current?.click()}><Icon name="upload" /> Subir .sql / .py</button>
                <input ref={fileRef} type="file" accept=".sql,.py,text/plain" hidden onChange={async event => { const file = event.target.files?.[0]; if (!file) return; setSource(await file.text()); setLanguage(file.name.endsWith(".py") ? "python" : "sql"); setNotice(`${file.name} cargado`); }} />
              </div>
              <textarea aria-label="Código de la regla" value={source} onChange={event => setSource(event.target.value)} spellCheck={false} />
              <p className="safe-note">◈ Solo se aceptan expresiones y columnas del catálogo. No se ejecuta el código original.</p>
            </div>
          )}

          <div className="primary-actions">
            <button className="primary" onClick={compile} disabled={!!busy}><Icon name="spark" />{busy === "compile" ? "Compilando…" : "Generar DSL"}</button>
            <button onClick={execute} disabled={!dsl || !!busy}><Icon name="play" />{busy === "execute" ? "Ejecutando…" : "Ejecutar en cartera"}</button>
            <button className="publish" onClick={publish} disabled={!result || !!busy}><Icon name="upload" />{busy === "publish" ? "Publicando…" : "Publicar versión"}</button>
          </div>
          {notice && <div className="notice"><Icon name="check" />{notice}</div>}
        </div>

        <div className="output card">
          <div className="output-tabs"><button className={panel === "dsl" ? "selected" : ""} onClick={() => setPanel("dsl")}>DSL generado</button><button className={panel === "results" ? "selected" : ""} onClick={() => setPanel("results")}>Resultados {result && <span>{data?.total.toLocaleString("es-PE")}</span>}</button></div>
          {panel === "dsl" ? dsl ? <pre>{JSON.stringify(dsl, null, 2)}</pre> : <div className="empty"><Icon name="code" /><h3>El contrato aparecerá aquí</h3><p>Define una regla y genera el DSL para inspeccionar su plan, entradas e integridad.</p></div> : result ? <div className="results-panel">
            <div className="result-summary"><div className="donut" style={{ "--pct": `${approval?.pct || 0}%` } as React.CSSProperties}><strong>{approval?.pct || 0}%</strong><span>aprobación</span></div><div className="summary-list">{result.summary.map(item => <div key={item.decision}><i className={item.decision === "APROBAR" ? "approved" : "reviewed"} /><span>{item.decision}</span><strong>{item.count.toLocaleString("es-PE")}</strong><em>{item.pct}%</em></div>)}<small>Tiempo de ejecución: {result.elapsed_ms} ms</small></div></div>
            <div className="table-wrap"><table><thead><tr><th>Cliente</th><th>Ingreso</th><th>Score</th><th>Utilización</th><th>Decisión</th></tr></thead><tbody>{result.rows.slice(0, 8).map(row => <tr key={String(row.client_id)}><td>CL-{String(row.client_id).padStart(5, "0")}</td><td>S/ {Number(row.monthly_income || 0).toLocaleString("es-PE")}</td><td>{row.credit_score ?? "N/D"}</td><td>{Math.round(Number(row.credit_utilization || 0) * 100)}%</td><td><span className={`pill ${row.decision === "APROBAR" ? "ok" : "warn"}`}>{row.decision}</span></td></tr>)}</tbody></table></div>
          </div> : <div className="empty"><Icon name="play" /><h3>Ejecuta el DSL validado</h3><p>Verás la distribución de decisiones y una muestra de clientes.</p></div>}
        </div>
      </section>

      <section className="portfolio-section">
        <div className="section-heading"><div><p className="kicker">DATOS DE PRUEBA</p><h2>Cartera con señales realistas</h2></div><p>Datos sintéticos y determinísticos; no representan personas reales.</p></div>
        <div className="portfolio-grid">
          <div className="card distribution"><h3>Distribución por segmento</h3>{data?.distributions.map(item => <div className="bar-row" key={item.label}><span>{item.label}</span><div><i style={{ width: `${item.value / maxDistribution * 100}%` }} /></div><strong>{item.value.toLocaleString("es-PE")}</strong></div>)}</div>
          <div className="card data-preview"><div className="mini-heading"><h3>Muestra de clientes</h3><span><Icon name="data" /> RDV.clients</span></div><div className="table-wrap"><table><thead><tr><th>ID</th><th>Segmento</th><th>Ingreso</th><th>Score</th><th>Moras</th></tr></thead><tbody>{data?.sample.slice(0, 5).map(row => <tr key={String(row.client_id)}><td>CL-{String(row.client_id).padStart(5, "0")}</td><td>{row.customer_segment}</td><td>S/ {Number(row.monthly_income || 0).toLocaleString("es-PE")}</td><td>{row.credit_score ?? "N/D"}</td><td>{row.delinquency_count}</td></tr>)}</tbody></table></div></div>
        </div>
      </section>

      <section className="published-section">
        <div className="section-heading"><div><p className="kicker">DDV · REGLAS PUBLICADAS</p><h2>Historial versionado</h2></div><span className="catalog-status"><i /> Disponible para procesos productivos</span></div>
        <div className="rules-list card">{data?.rules.length ? data.rules.map(rule => <div className="rule-row" key={rule.id}><div className="rule-icon"><Icon name="check" /></div><div><strong>{rule.name}</strong><span>{rule.rule_id}</span></div><b>v{rule.version}</b><span>{rule.author}</span><time>{new Date(rule.created_at).toLocaleString("es-PE", { dateStyle: "medium", timeStyle: "short" })}</time><em>PUBLICADA</em></div>) : <div className="empty-rules">Publica la primera regla para crear el historial de DDV.</div>}</div>
      </section>

      <footer><span><span className="brand-mark">◇</span> Rule Studio</span><p>Demo de arquitectura determinística · SQL/Python → DSL → Ejecución</p><b>Datos 100% sintéticos</b></footer>
    </main>
  );
}
