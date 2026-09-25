// Build "PromoFlow_Database_Schema.docx" from docs/schema.json and docs/er_overview.png.
//   npm install docx        (once, in this folder or globally)
//   node scripts/build_schema_doc.js <output.docx>
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, AlignmentType,
  HeadingLevel, LevelFormat, BorderStyle, Header, Footer, PageNumber, TableOfContents, PageBreak, ImageRun,
  TableLayoutType,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const data = JSON.parse(fs.readFileSync(path.join(ROOT, "docs", "schema.json"), "utf8"));
const INK = "1D2733", GOLD = "7A5A16", GREY = "4D596B", FONT = "Calibri", W = 10080;

function runs(text, base = {}) {
  const out = []; const re = /(\*\*[^*]+\*\*|`[^`]+`)/g; let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), ...base, bold: true }));
    else out.push(new TextRun({ text: t.slice(1, -1), ...base, font: "Consolas", size: (base.size || 21) - 2 }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}
const P = (t, o = {}) => new Paragraph({ children: runs(t, o.run || {}), spacing: { after: 120, line: 276 }, ...o.para });
const H1 = (t, br = true) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], pageBreakBefore: br });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const B = (t) => new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: runs(t), spacing: { after: 50, line: 260 } });
const gap = () => new Paragraph({ spacing: { after: 100 }, children: [] });

const cb = { style: BorderStyle.SINGLE, size: 2, color: "C9CED6" };
const borders = { top: cb, bottom: cb, left: cb, right: cb };
function cell(text, width, { head = false, fill, mono = false, bold = false } = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA }, borders,
    shading: fill ? { fill, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 40, bottom: 40, left: 70, right: 70 },
    children: String(text).split("\n").map((line) => new Paragraph({ spacing: { after: 10, line: 235 },
      children: mono && !head
        ? [new TextRun({ text: line, font: "Consolas", size: 15, bold })]
        : runs(line, { size: 16, color: head ? "FFFFFF" : "000000", bold: head || bold }) })),
  });
}
function table(headers, rows, widths, monoCols = []) {
  if (widths.reduce((a, b) => a + b, 0) !== W) throw new Error("widths " + headers);
  return [new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: widths, layout: TableLayoutType.FIXED,
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, widths[i], { head: true, fill: INK })) }),
      ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((c, i) =>
        cell(c, widths[i], { fill: ri % 2 ? "F4F6F9" : undefined, mono: monoCols.includes(i), bold: i === 0 && monoCols.includes(0) })) })),
    ],
  }), gap()];
}

const c = [];
const nTables = data.tables.length, nEnums = Object.keys(data.enums).length;

// ---------- title ----------
c.push(
  new Paragraph({ spacing: { before: 2200, after: 200 }, children: [new TextRun({ text: "PromoFlow", bold: true, size: 64, color: INK, font: FONT })] }),
  new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: "Database Schema", size: 40, color: GOLD, font: FONT })] }),
  new Paragraph({ spacing: { after: 500 }, children: [new TextRun({ text: `PostgreSQL 16 + pgvector · ${nTables} tables · ${nEnums} enum types`, italics: true, size: 24, color: GREY, font: FONT })] }),
  ...table(["Item", "Value"], [
    ["Status", "Draft v0.1 – migration 0001 (initial schema)"],
    ["Date", "25 September 2026"],
    ["Derived from", "PromoFlow Dossier Data Entry Specification (reviewed version), Agent Specifications, SCHESR policy briefing V3 (May 2026)"],
    ["Source of truth", "The SQLAlchemy models in `promoflow/db/models/`. Sections 8–10 of this document are generated from them, so the document and the database cannot disagree. Regenerate with `scripts/export_schema.py` + `scripts/build_schema_doc.js`."],
    ["Repository", "promoflow (git) – run instructions in README.md"],
  ], [2200, 7880]),
  new Paragraph({ children: [new PageBreak()] }),
  new Paragraph({ children: [new TextRun({ text: "Contents", bold: true, size: 32, color: INK, font: FONT })], spacing: { after: 200 } }),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-1" }),
);

// ---------- 1 ----------
c.push(H1("1. Purpose and Technology"));
c.push(P("This document specifies the database behind PromoFlow: every table, column, constraint and fixed value list, the decisions behind the design, and how the schema maps to the dossier sections the professor fills in."));
c.push(...table(["Layer", "Choice", "Why"], [
  ["Database", "PostgreSQL 16, run locally (Docker image pgvector/pgvector:pg16)", "Privacy: real faculty data may be stored; a personal cloud free tier has no institutional data agreement"],
  ["Vector search", "pgvector extension in the same database", "Hybrid RAG (full-text + embeddings) without a separate vector-database service"],
  ["ORM", "SQLAlchemy 2 (typed declarative models)", "Streamlit and LangGraph call Python directly; no REST layer"],
  ["Migrations", "Alembic", "Every schema change is a versioned script; all teammates stay in sync"],
  ["Workflow state", "LangGraph PostgreSQL checkpointer", "Paused cases survive a restart; its tables are managed by LangGraph, not by these migrations"],
], [1700, 3900, 4480]));

// ---------- 2 ----------
c.push(H1("2. Design Decisions"));
const decisions = [
  ["Structured entries, one table per dossier sub-section", "Each repeatable group of the data entry specification (a paper, a course, a committee...) is a table. Deterministic checks become SQL queries instead of document reading."],
  ["Every dossier entry belongs to one case", "Entry tables carry `case_id → promotion_case` with ON DELETE CASCADE, always the second column."],
  ["Section 0 is a snapshot on the case", "Rank, dates and identifiers are stored on `promotion_case`, not on the user, so a submitted case keeps exactly what was submitted even if the profile changes later."],
  ["Policy versioning", "Thresholds live in `promotion_criteria` per `policy_version`; each case points to the version in force on its submission date, so a policy change never alters a case under review."],
  ["Typed thresholds, not key–value", "`promotion_criteria` has one named column per threshold (e.g. `min_class_a_main_author`) so rules read clear, typed values. Per-type book caps are rows in `research_item_cap`."],
  ["Enums for rules, lookup table for descriptions", `Lists the rules depend on (rank, status, author role, journal class...) are ${nEnums} PostgreSQL enum types. Descriptive dropdowns that Admin may edit (committee role, activity type...) are rows in \`lookup_value\`, referenced by foreign key. Multi-select answers are text arrays of lookup codes, validated in code.`],
  ["Inputs are never overwritten by results", "Journal class, counts, pass/fail and referee averages are computed by the deterministic rules at run time and recorded in `criterion_result` / `item_result`. What the professor entered stays untouched."],
  ["One document table for all files", "`case_document` links a file to any entry through (`entity_table`, `entity_id`). This avoids ~30 separate file tables; the trade-off is that this link is validated in application code rather than by a foreign key. Files keep a SHA-256 hash, and a replaced file is kept (`superseded_by_id`)."],
  ["Agent suggestion and human decision stored separately", "`rubric_score` keeps the agent's suggested points next to the HoD's and the Dean's values and the reason for any change; `gate_decision` records each approval or return-for-revision with the sections to unlock."],
  ["Claims are checkable", "Each factual statement an agent makes is a `claim` row with the table and record IDs it cites; `verify_claims()` checks them and records the result."],
  ["Reproducible agent runs", "`agent_run` stores the model name, prompt version and a hash of the input for every run."],
  ["Login is SSO-ready", "Passwords are argon2id hashes; sessions store only a SHA-256 of the token. `auth_provider` and `external_subject` let university single sign-on replace passwords later without schema changes. Roles are scoped (a HoD to a department, a Dean to a college) and one person may hold several."],
  ["RAG in the same database", "`policy_chunk` has a generated full-text column (GIN index) and an embedding column (HNSW cosine index). The vector size is a setting (`EMBEDDING_DIM`, default 1536) that must match the chosen embedding model."],
  ["Append-only audit log", "`audit_log_entry` records who did what and when, with before/after values as JSONB."],
  ["Referee confidentiality", "Referee identities are only in the referee tables; the application's permission layer never shows them to the applicant."],
];
c.push(...table(["Decision", "What and why"], decisions, [2800, 7280]));

// ---------- 3 ----------
c.push(H1("3. Domain Overview"));
c.push(P(`The ${nTables} tables fall into nine groups. Each row in the diagram shows a table and the tables it references.`));
const img = fs.readFileSync(path.join(ROOT, "docs", "er_overview.png"));
const iw = 660, ih = Math.round(iw * 2122 / 3440);
c.push(new Paragraph({ children: [new ImageRun({ type: "png", data: img, transformation: { width: iw, height: ih },
  altText: { title: "Domain overview", description: "Tables grouped by domain", name: "er" } })] }));
c.push(...table(["Group", "Tables", "Covers"], data.domains.map((d) => [
  d.title, String(data.tables.filter((t) => t.module === d.module).length), d.spec]), [3600, 900, 5580]));

// ---------- 4 ----------
c.push(H1("4. Dossier Sections → Tables"));
c.push(...table(["Spec section", "Table(s)"], [
  ["§0 Identity (user profile)", "app_user, user_role, college, department"],
  ["§0 Track, rank, dates, identifiers, special conditions", "promotion_case"],
  ["§1 Application form declaration", "promotion_case (decl_* columns); signed form in case_document"],
  ["§2 CV", "case_document (kind = cv)"],
  ["§3 Degrees & equivalency", "degree (+ certificates in case_document)"],
  ["§4A / §4B Ranks & experience", "rank_history, non_academic_position"],
  ["§5A Research papers", "publication, publication_author, coauthored_paper_evaluation (provisional)"],
  ["§5A-2 Creative / studio works", "creative_work"],
  ["§5B Books & chapters", "book (caps in research_item_cap)"],
  ["§5C Conference papers", "conference_paper"],
  ["§5D Funded projects", "funded_project"],
  ["§5E Journal classification", "journal, journal_ranking (reference); journal_criteria_confirmation (journals not in the table)"],
  ["§5F Scopus evidence", "scopus_evidence; verified values in researcher_profile"],
  ["§5G Patents / §5H Awards", "patent, award"],
  ["§6A–6C Courses, peer observation, student satisfaction", "course_taught, peer_observation, student_satisfaction"],
  ["§6D Curriculum development", "curriculum_contribution"],
  ["§6E Academic advising", "advising_semester"],
  ["§6F–6I Course files, innovation, supervision, development", "course_file, teaching_innovation, supervision, teaching_development"],
  ["§7A University service", "committee_membership, administrative_position, workshop_delivered, training_delivered, policy_contribution"],
  ["§7B Community service", "community_activity"],
  ["§8 Recommendation letters", "recommendation_letter"],
  ["§9 Conditions form / §10 Cover letter", "case_document (kind = signed_form, signed_date)"],
  ["§11 Statuses", "promotion_case.status, case_status_history"],
  ["§14.1 Appendix E / F scoring", "rubric, rubric_item, rubric_score"],
  ["§14.2 Dean's report (Appendix D)", "dean_evaluation"],
  ["§14.3 Referees (Appendix J/K)", "referee, referee_candidate, reviewer_assignment, outreach_message, referee_report, referee_paper_grade"],
  ["Agents, Report Builder, gates", "agent_run, agent_assessment, criterion_result, item_result, claim, flag, case_report, gate_decision"],
], [4200, 5880]));

// ---------- 5 ----------
c.push(H1("5. Sensitive Data"));
c.push(P("These columns hold personal data. They are shown only to the owner and authorised reviewers and are **never sent to the LLM**; agents receive record IDs instead."));
c.push(...table(["Column(s)", "Why it is stored"], [
  ["app_user.full_name, employee_id, email", "Identity on the generated forms; login"],
  ["supervision.student_name", "Only to match co-authors of papers for the supervision rule"],
  ["peer_observation.observer_name", "Optional, as printed on the report"],
  ["recommendation_letter.writer_name", "As on the letter"],
  ["referee.full_name, email, university", "Referee contact; confidential from the applicant"],
  ["case_document files", "Evidence on local disk only (EVIDENCE_DIR), never a third-party cloud"],
  ["auth_session.token_hash, app_user.password_hash", "Hashes only; raw tokens and passwords are never stored"],
], [4200, 5880]));
c.push(P("Advising (§6E) deliberately stores counts only, never student names. Nationality was removed from the specification and is not stored."));

// ---------- 6 ----------
c.push(H1("6. Where Each Rule Is Enforced"));
c.push(P("Simple, single-row rules are database constraints, so bad data cannot be saved by any path. Rules that compare several tables or depend on the policy version are in the deterministic rules code, where they are unit-tested and produce explanations for the reviewer."));
c.push(...table(["Rule", "Enforced in"], [
  ["A HoD role names a department; a Dean role names a college", "Database (CHECK)"],
  ["Local accounts have a password hash; SSO accounts have an external subject", "Database (CHECK)"],
  ["Exceptional-case request has a justification; previous rejection has a date", "Database (CHECK)"],
  ["Published paper has an issue date; accepted paper has an acceptance date", "Database (CHECK)"],
  ["Main-author claim has a basis; 'other' basis has an explanation", "Database (CHECK)"],
  ["Supervised-student paper links to a supervision entry", "Database (CHECK)"],
  ["Author position within 1…total authors; ratings within their scale", "Database (CHECK)"],
  ["Advising: cleared ≤ on warning; improved ≤ remaining", "Database (CHECK)"],
  ["Files ≤ 25 MB", "Database (CHECK) + upload code"],
  ["Rubric item points within range", "Database (CHECK on rubric_item) + review page"],
  ["Return for revision names the sections to unlock", "Database (CHECK)"],
  ["Referee grades 0–100 %", "Database (CHECK)"],
  ["Time in rank, early application, reapplication", "Eligibility Checker (code)"],
  ["Counts vs thresholds, journal class, caps, supervision cap", "Research Agent deterministic part (code)"],
  ["Rubric totals capped at 30 / 10; pass marks", "Teaching / Service Agents + review pages (code)"],
  ["Respondents ≤ students of the linked course; files attached to valid entries", "Application code (cross-table)"],
  ["≤ 10 referee candidates; 5-year non-reuse; 3-month replacement", "Chancellor's Office Agent + Reminder worker (code)"],
  ["Referee identity hidden from the applicant", "Permission layer (code)"],
], [6600, 3480]));

// ---------- 7 ----------
c.push(H1("7. Seeded Reference Data"));
c.push(P("`python -m promoflow.db.seed` loads the following (idempotent)."));
c.push(H2("7.1 Promotion criteria (policy SCHESR-2026-05)"));
const keys = Object.keys(data.criteria.to_associate);
c.push(...table(["Threshold", "Associate", "Full"], keys.map((k) => [k, data.criteria.to_associate[k], data.criteria.to_full[k]]), [5480, 2300, 2300], [0]));
c.push(H2("7.2 Appendix E – Teaching & Academic Advising (30 points, pass 24)"));
c.push(...table(["#", "Item", "Points", "Notes"], data.teaching_items.map((i) => [String(i[0]), i[1], `${i[2]}–${i[3]}`,
  [i[4] ? "Full Professor only" : "", i[5] ? "Redistributable (departments without degrees)" : ""].filter(Boolean).join("; ")]),
  [500, 5600, 900, 3080]));
c.push(H2(`7.3 Appendix F – University & Community Service (10 points, pass ${data.service_pass_points})`));
c.push(...table(["#", "Item", "Points"], data.service_items.map((i) => [String(i[0]), i[1], `${i[2]}–${i[3]}`]), [500, 8680, 900]));
c.push(P("The service pass mark is a setting (`SERVICE_PASS_POINTS`): the official form says \"80% (i.e. 7 points out of 10)\" but 80% of 10 is 8. Seeded as 8 until confirmed."));
c.push(H2("7.4 Admin-editable lists (lookup_value)"));
c.push(...table(["list_code", "Values"], Object.entries(data.lookups).map(([k, v]) => [k, v.map((x) => x[1]).join(" · ")]), [3000, 7080], [0]));
c.push(H2("7.5 Development accounts"));
c.push(P("Five test accounts (applicant, HoD, Dean, Chancellor, Admin) in a fictional college, with the password from `DEV_PASSWORD`. Never used with real data."));

// ---------- 8 ----------
c.push(H1("8. Table Reference"));
c.push(P("Generated from the models. Columns: **Null** = may be empty; **Key** = primary key (PK), foreign key (FK → table.column, with its ON DELETE rule) or unique."));
const CW = [2150, 1750, 550, 2530, 3100];
for (const d of data.domains) {
  c.push(H2(d.title));
  for (const t of data.tables.filter((x) => x.module === d.module)) {
    c.push(H3(t.name));
    if (t.doc) c.push(P(t.doc, { run: { italics: true, color: GREY } }));
    c.push(...table(["Column", "Type", "Null", "Key / default", "Notes"], t.columns.map((col) => [
      col.name, col.type.length > 28 ? col.type.slice(0, 28) + "…" : col.type, col.nullable ? "yes" : "",
      [col.key, col.default].filter(Boolean).join(" · "), col.note]), CW, [0, 1]));
    for (const con of t.constraints) c.push(B("`" + con + "`"));
    if (t.constraints.length) c.push(gap());
  }
}

// ---------- 9 ----------
c.push(H1("9. Enum Types"));
c.push(...table(["Type", "Values", "Used in"], Object.entries(data.enums).map(([k, v]) => [k, v.values.join(", "), v.used_in.join(", ")]),
  [1900, 3900, 4280], [0]));

// ---------- 10 ----------
c.push(H1("10. Outside This Schema"));
c.push(B("**LangGraph checkpoint tables** (`checkpoint*`) are created by LangGraph's PostgreSQL checkpointer in the same database; Alembic is configured to ignore them."));
c.push(B("**Evidence files** are stored on local disk under `EVIDENCE_DIR`; the database holds their path, type, size and SHA-256."));
c.push(B("**Journal ranking data** (SJR/Scopus) will be loaded by an import script from the SJR data files; the tables are ready but empty."));
c.push(B("**The full SQL** of migration 0001 is in `docs/schema.sql` (`alembic upgrade head --sql`)."));

// ---------- 11 ----------
c.push(H1("11. Open Points Affecting the Schema"));
c.push(...table(["#", "Point", "Current handling"], [
  ["1", "Co-authored Papers & Evaluation Form (Appendix H) columns", "`coauthored_paper_evaluation` is provisional; adjust when the 5A template arrives"],
  ["2", "Service pass mark 7/10 or 8/10", "`rubric.pass_points`, seeded from SERVICE_PASS_POINTS (8)"],
  ["3", "Definition of \"main author\"", "`main_author_basis` records the basis; the rule decides which bases count"],
  ["4", "Do conference papers / book chapters count?", "Stored; counting decided in the rules, not the schema"],
  ["5", "Embedding model (vector size)", "EMBEDDING_DIM = 1536; changing it later needs a migration"],
  ["6", "Journals Classification Form (5E), Conditions Form (9), Committee Summary Report (C)", "Stored as signed documents for now; structured tables can be added by migration"],
], [400, 4600, 5080]));

// ---------- 12 ----------
c.push(H1("12. How to Create the Database"));
[
  "Install Docker Desktop, then in the repository: `docker compose up -d`",
  "`python -m venv .venv` and activate it, then `pip install -e .[dev]`",
  "Copy `.env.example` to `.env`",
  "`alembic upgrade head`  (creates all tables)",
  "`python -m promoflow.db.seed`  (criteria, rubrics, lists, dev accounts)",
  "`streamlit run app/Home.py`",
].forEach((s) => c.push(new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: runs(s), spacing: { after: 60 } })));

const doc = new Document({
  creator: "PromoFlow team", title: "PromoFlow – Database Schema",
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: FONT, color: INK },
        paragraph: { spacing: { before: 240, after: 160 }, outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: GOLD, space: 4 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: FONT, color: GOLD },
        paragraph: { spacing: { before: 300, after: 120 }, outlineLevel: 1, keepNext: true } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: "Consolas", color: INK },
        paragraph: { spacing: { before: 220, after: 60 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
    { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
      children: [new TextRun({ text: "PromoFlow · Database Schema · Draft v0.1", size: 16, color: GREY })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "Page ", size: 16, color: GREY }), new TextRun({ children: [PageNumber.CURRENT], size: 16, color: GREY })] })] }) },
    children: c,
  }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(process.argv[2], buf); console.log("wrote", process.argv[2]); });
