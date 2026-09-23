// Mini spreadsheet for tasks 3, 9, 18, 22 (design doc 7.3): sort, filter, search and
// a formula bar with СУММ/МАКС/СЧЁТЕСЛИ over the task's CSV.
import { useMemo, useState } from "react";

import { FormulaError, columnName, evaluate, filterRows, sortRows, type Table } from "../lib/sheet";

const PAGE = 200;

export function Grid({ table }: { table: Table }) {
  const [sort, setSort] = useState<{ column: number; desc: boolean } | null>(null);
  const [query, setQuery] = useState("");
  const [formula, setFormula] = useState("");
  const [page, setPage] = useState(0);
  const header = table[0] ?? [];
  const body = table.slice(1);
  const view = useMemo(() => {
    const filtered = filterRows(body, query);
    return sort ? sortRows(filtered, sort.column, sort.desc) : filtered;
  }, [body, query, sort]);
  const result = useMemo(() => {
    if (!formula.trim().startsWith("=")) return null;
    try {
      return { ok: true, text: String(evaluate(formula, table)) };
    } catch (error) {
      return { ok: false, text: error instanceof FormulaError ? error.message : "Ошибка в формуле" };
    }
  }, [formula, table]);
  const shown = view.slice(page * PAGE, (page + 1) * PAGE);
  return (
    <div className="grid-wrap">
      <div className="grid-tools">
        <input className="input" placeholder="Поиск по таблице" value={query} onChange={(e) => { setQuery(e.target.value); setPage(0); }} />
        <input
          className="input mono"
          placeholder="=СЧЁТЕСЛИ(B2:B100;&quot;>5&quot;)"
          value={formula}
          onChange={(e) => setFormula(e.target.value)}
          aria-label="Формула"
        />
        {result ? <div className={result.ok ? "formula-ok" : "formula-err"}>{result.text}</div> : null}
        <small className="muted">
          Строка 1 — заголовки, данные с A2. Строк: {view.length}
          {query ? ` из ${body.length}` : ""}
        </small>
      </div>
      <div className="table-scroll grid">
        <table>
          <thead>
            <tr>
              <th className="rownum">#</th>
              {header.map((h, i) => (
                <th key={i} onClick={() => setSort((s) => ({ column: i, desc: s?.column === i ? !s.desc : false }))}>
                  <span className="colname">{columnName(i)}</span> {h}
                  {sort?.column === i ? (sort.desc ? " ▼" : " ▲") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, r) => (
              <tr key={r}>
                <td className="rownum">{page * PAGE + r + 2}</td>
                {header.map((_, c) => (
                  <td key={c}>{row[c] ?? ""}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {view.length > PAGE ? (
        <div className="pager">
          <button className="btn btn-ghost btn-small" disabled={page === 0} onClick={() => setPage(page - 1)}>←</button>
          <span>{page + 1} / {Math.ceil(view.length / PAGE)}</span>
          <button className="btn btn-ghost btn-small" disabled={(page + 1) * PAGE >= view.length} onClick={() => setPage(page + 1)}>→</button>
        </div>
      ) : null}
    </div>
  );
}
