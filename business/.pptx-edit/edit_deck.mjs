import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const STARTER = "/Users/manuelrodval/projects/toy-projects/rule-manager-interpreter/business/.pptx-edit/template-starter.pptx";
const FINAL = "/Users/manuelrodval/projects/toy-projects/rule-manager-interpreter/business/interprete_reglas_deterministico.pptx";

const presentation = await PresentationFile.importPptx(await FileBlob.load(STARTER));

function rewrite(slideIndex, name, value) {
  const slide = presentation.slides.getItem(slideIndex);
  const shape = slide.shapes.getItem(name);
  if (!shape) throw new Error(`No se encontró ${name} en la diapositiva ${slideIndex + 1}`);
  shape.text = value;
}

function rewriteNotes(slideIndex, value) {
  presentation.slides.getItem(slideIndex).speakerNotes.textFrame.setText(value);
}

// 1. Beneficios — conserva la comparación de la diapositiva fuente 3.
rewrite(0, "title-3", "Beneficios: control, velocidad y menor costo");
rewrite(0, "page-3", "01");
rewrite(0, "left-label", "PARA EL NEGOCIO");
rewrite(0, "right-label", "PARA TECNOLOGÍA Y RIESGO");
rewrite(0, "l-0", "✓  Cambios sin desplegar la aplicación");
rewrite(0, "l-1", "✓  Resultado reproducible");
rewrite(0, "l-2", "✓  Revisión antes de publicar");
rewrite(0, "l-3", "✓  Auditoría por versión");
rewrite(0, "l-4", "✓  IA fuera de la ruta crítica");
rewrite(0, "r-0", "✓  Un IR común para SQL y PySpark");
rewrite(0, "r-1", "✓  Ejecución en DuckDB y Spark");
rewrite(0, "r-2", "✓  Catálogo limita datos y columnas");
rewrite(0, "r-3", "✓  Pruebas comparan ambos motores");
rewrite(0, "r-4", "✓  Sin inferencia recurrente");
rewrite(0, "decision", "La IA acelera la autoría; el DSL conserva el control de producción.");
rewriteNotes(0, "Idea central: separar la asistencia de IA de la ejecución productiva.\n\n[Sources]\n- README.md — diseño, validación y ejecución.\n- notebooks/rule_manager_demo.ipynb — equivalencia entre lenguajes y motores.");

// 2. Flujo — conserva el diagrama de la diapositiva fuente 4.
rewrite(1, "title-4", "Flujo: del código aprobado a la ejecución");
rewrite(1, "page-4", "02");
rewrite(1, "node-text-0", "SQL o\nPySpark");
rewrite(1, "node-text-1", "Parser\nAST");
rewrite(1, "node-text-2", "Validación\nsemántica");
rewrite(1, "node-text-3", "DSL JSON\nversionado");
rewrite(1, "node-text-4", "DuckDB o\nSpark");
rewrite(1, "control-a", "Catálogo");
rewrite(1, "control-b", "Tipos y nulos");
rewrite(1, "control-c", "Integridad");
rewrite(1, "architecture-callout", "El código original no llega al ejecutor: solo llega un plan validado con operaciones conocidas.");
rewriteNotes(1, "El parser transforma AST de SQL o PySpark; el ejecutor recibe únicamente DSL validado.\n\n[Sources]\n- README.md — arquitectura y representación intermedia.\n- src/rule_interpreter/parsers/ y src/rule_interpreter/executors/ — implementación.");

// 3. DSL envelope — conserva el panel JSON de la diapositiva fuente 5.
rewrite(2, "title-5", "DSL (1/2): una regla de crédito en datos");
rewrite(2, "page-5", "03");
rewrite(2, "json", '{\n "dsl_version": "1.0",\n "rule": { "id": "credit-policy" },\n "inputs": [{ "source": "clients" }],\n "plan": {\n  "op": "project",\n  "input": {\n   "op": "filter",\n   "input": { "op": "scan",\n              "source": "clients" },\n   "where": { "op": "and", "args": [\n    { "op": "gte", "column": "income",\n      "value": 3000 },\n    { "op": "gte", "column": "credit_score",\n      "value": 650 }\n   ]}\n  },\n  "columns": ["client_id", "income",\n   { "as": "decision", "expr": { "op": "case",\n     "when": "eligible", "then": "APPROVE",\n     "else": "REVIEW" }}]\n },\n "integrity": { "algorithm": "sha256" }\n}');
rewrite(2, "dsl-h-0", "SCAN");
rewrite(2, "dsl-b-0", "Lee clientes desde una fuente autorizada del catálogo.");
rewrite(2, "dsl-h-1", "FILTER + AND");
rewrite(2, "dsl-b-1", "Conserva ingresos ≥ 3.000 y score ≥ 650; los nulos no califican.");
rewrite(2, "dsl-h-2", "PROJECT");
rewrite(2, "dsl-b-2", "Define exactamente los datos que recibirá el proceso de negocio.");
rewrite(2, "dsl-h-3", "CASE");
rewrite(2, "dsl-b-3", "Asigna APPROVE al elegible y REVIEW al resto, de forma auditable.");
rewriteNotes(2, "Lectura de negocio del ejemplo: se consultan clientes autorizados, se aplican simultáneamente los umbrales de ingreso y score, se limita la salida y se genera una decisión trazable.\n\n[Sources]\n- README.md — catálogo, envelope DSL y plan relacional.\n- src/rule_interpreter/dsl.py — versión e integridad SHA-256.");

// 4. DSL nodes — conserva la cuadrícula de la diapositiva fuente 7.
rewrite(3, "title-7", "DSL (2/2): estructura y semántica");
rewrite(3, "page-7", "04");
rewrite(3, "sec-num-0", "01");
rewrite(3, "sec-head-0", "Nodos relacionales");
rewrite(3, "sec-body-0", "scan · join · filter · project · sort · limit");
rewrite(3, "sec-num-1", "02");
rewrite(3, "sec-head-1", "Nodos de expresión");
rewrite(3, "sec-body-1", "column · literal · compare · boolean · case · call");
rewrite(3, "sec-num-2", "03");
rewrite(3, "sec-head-2", "Tipos y nulos");
rewrite(3, "sec-body-2", "Tipos explícitos y lógica SQL de tres valores.");
rewrite(3, "sec-num-3", "04");
rewrite(3, "sec-head-3", "Capacidades por backend");
rewrite(3, "sec-body-3", "El plan falla antes de ejecutar si el motor no lo soporta.");
rewriteNotes(3, "Los adapters implementan la misma semántica y declaran qué nodos soportan.\n\n[Sources]\n- README.md — IR, nulos y capacidades.\n- src/rule_interpreter/executors/ — renderers DuckDB y Spark.");

const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(FINAL);
