// The mini-grid's engine (design doc 7.3): CSV parsing, sort/filter and a small
// formula evaluator — СУММ, МАКС, МИН, СЧЁТ, СЧЁТЕСЛИ, СУММЕСЛИ, СРЗНАЧ and the
// same names in English, with arithmetic, parentheses and A1:B7 ranges.

export type Cell = string;
export type Table = Cell[][];

export function parseCsv(text: string): Table {
  const firstLine = text.slice(0, text.indexOf("\n") >>> 0);
  const delimiter = (firstLine.match(/;/g)?.length ?? 0) > (firstLine.match(/,/g)?.length ?? 0) ? ";" : ",";
  const rows: Table = [];
  let row: Cell[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]!;
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (ch === '"') {
        quoted = false;
      } else {
        field += ch;
      }
    } else if (ch === '"' && field === "") {
      quoted = true;
    } else if (ch === delimiter) {
      row.push(field);
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += ch;
    }
  }
  if (field !== "" || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

export function columnName(index: number): string {
  let name = "";
  let n = index + 1;
  while (n > 0) {
    const rem = (n - 1) % 26;
    name = String.fromCharCode(65 + rem) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

export function columnIndex(name: string): number {
  let n = 0;
  for (const ch of name.toUpperCase()) n = n * 26 + (ch.charCodeAt(0) - 64);
  return n - 1;
}

export function toNumber(value: Cell | undefined): number | null {
  if (value === undefined) return null;
  const text = value.trim().replace(/\s/g, "").replace(",", ".");
  if (!text || !/^[-+]?\d*\.?\d+(e[-+]?\d+)?$/i.test(text)) return null;
  return Number(text);
}

export function sortRows(rows: Table, column: number, descending: boolean): Table {
  const copy = [...rows];
  copy.sort((a, b) => {
    const x = a[column] ?? "";
    const y = b[column] ?? "";
    const nx = toNumber(x);
    const ny = toNumber(y);
    const order = nx !== null && ny !== null ? nx - ny : x.localeCompare(y, "ru");
    return descending ? -order : order;
  });
  return copy;
}

export function filterRows(rows: Table, query: string): Table {
  const needle = query.trim().toLowerCase();
  if (!needle) return rows;
  return rows.filter((row) => row.some((cell) => cell.toLowerCase().includes(needle)));
}

// ---- formulas --------------------------------------------------------------

export class FormulaError extends Error {}

type Value = number | string | Value[];
type Token =
  | { t: "num"; v: number }
  | { t: "str"; v: string }
  | { t: "ref"; v: string }
  | { t: "range"; from: string; to: string }
  | { t: "name"; v: string }
  | { t: "op"; v: string };

const FUNCTIONS: Record<string, string> = {
  СУММ: "SUM", SUM: "SUM",
  МАКС: "MAX", MAX: "MAX",
  МИН: "MIN", MIN: "MIN",
  СЧЁТ: "COUNT", СЧЕТ: "COUNT", COUNT: "COUNT",
  СЧЁТЕСЛИ: "COUNTIF", СЧЕТЕСЛИ: "COUNTIF", COUNTIF: "COUNTIF",
  СУММЕСЛИ: "SUMIF", SUMIF: "SUMIF",
  СРЗНАЧ: "AVERAGE", AVERAGE: "AVERAGE",
  ABS: "ABS", ОСТАТ: "MOD", MOD: "MOD",
};

function tokenize(src: string): Token[] {
  const tokens: Token[] = [];
  const re =
    /\s*(?:(\d+(?:[.,]\d+)?)|"([^"]*)"|([A-Za-z]{1,3}\d+):([A-Za-z]{1,3}\d+)|([A-Za-z]{1,3}\d+)(?![\wА-Яа-яЁё(])|([A-Za-zА-Яа-яЁё]+)|(<=|>=|<>|[-+*/();,:<>=^&]))/y;
  let pos = 0;
  while (pos < src.length) {
    re.lastIndex = pos;
    const m = re.exec(src);
    if (!m || m[0].length === 0) {
      if (/^\s*$/.test(src.slice(pos))) break;
      throw new FormulaError(`Не понимаю: «${src.slice(pos, pos + 8)}»`);
    }
    pos = re.lastIndex;
    if (m[1] !== undefined) tokens.push({ t: "num", v: Number(m[1].replace(",", ".")) });
    else if (m[2] !== undefined) tokens.push({ t: "str", v: m[2] });
    else if (m[3] !== undefined) tokens.push({ t: "range", from: m[3].toUpperCase(), to: m[4]!.toUpperCase() });
    else if (m[5] !== undefined) tokens.push({ t: "ref", v: m[5].toUpperCase() });
    else if (m[6] !== undefined) tokens.push({ t: "name", v: m[6].toUpperCase() });
    else if (m[7] !== undefined) tokens.push({ t: "op", v: m[7] });
  }
  return tokens;
}

function splitRef(ref: string): [number, number] {
  const m = /^([A-Z]+)(\d+)$/.exec(ref);
  if (!m) throw new FormulaError(`Неверная ссылка ${ref}`);
  return [columnIndex(m[1]!), Number(m[2]) - 1];
}

function matches(value: Value, criterion: Value): boolean {
  const text = String(criterion);
  const op = /^(<=|>=|<>|<|>|=)?(.*)$/.exec(text)!;
  const operator = op[1] ?? "=";
  const target = op[2] ?? "";
  const numTarget = toNumber(target);
  const numValue = typeof value === "number" ? value : toNumber(String(value));
  if (numTarget !== null && numValue !== null) {
    switch (operator) {
      case "<": return numValue < numTarget;
      case ">": return numValue > numTarget;
      case "<=": return numValue <= numTarget;
      case ">=": return numValue >= numTarget;
      case "<>": return numValue !== numTarget;
      default: return numValue === numTarget;
    }
  }
  const equal = String(value).toLowerCase() === target.toLowerCase();
  return operator === "<>" ? !equal : equal;
}

function flat(values: Value[]): Value[] {
  return values.flatMap((v) => (Array.isArray(v) ? flat(v) : [v]));
}

function numbers(values: Value[]): number[] {
  return flat(values)
    .map((v) => (typeof v === "number" ? v : toNumber(String(v))))
    .filter((v): v is number => v !== null);
}

export function evaluate(formula: string, table: Table): number | string {
  const src = formula.trim().replace(/^=/, "");
  const tokens = tokenize(src);
  let i = 0;
  const peek = () => tokens[i];
  const take = () => tokens[i++];
  const expectOp = (op: string) => {
    const tok = take();
    if (!tok || tok.t !== "op" || tok.v !== op) throw new FormulaError(`Ожидается «${op}»`);
  };
  const cell = (ref: string): Value => {
    const [c, r] = splitRef(ref);
    const raw = table[r]?.[c] ?? "";
    return toNumber(raw) ?? raw;
  };
  const range = (from: string, to: string): Value[] => {
    const [c1, r1] = splitRef(from);
    const [c2, r2] = splitRef(to);
    const out: Value[] = [];
    for (let r = Math.min(r1, r2); r <= Math.max(r1, r2); r++) {
      for (let c = Math.min(c1, c2); c <= Math.max(c1, c2); c++) {
        const raw = table[r]?.[c] ?? "";
        out.push(toNumber(raw) ?? raw);
      }
    }
    return out;
  };

  const num = (v: Value): number => {
    if (typeof v === "number") return v;
    if (Array.isArray(v)) throw new FormulaError("Диапазон нельзя использовать как число");
    const n = toNumber(v);
    if (n === null) throw new FormulaError(`«${v}» — не число`);
    return n;
  };

  function call(name: string): Value {
    const fn = FUNCTIONS[name];
    if (!fn) throw new FormulaError(`Неизвестная функция ${name}`);
    expectOp("(");
    const args: Value[] = [];
    if (!(peek()?.t === "op" && (peek() as { v: string }).v === ")")) {
      args.push(expr());
      while (peek()?.t === "op" && [";", ","].includes((peek() as { v: string }).v)) {
        take();
        args.push(expr());
      }
    }
    expectOp(")");
    switch (fn) {
      case "SUM": return numbers(args).reduce((a, b) => a + b, 0);
      case "MAX": return Math.max(...numbers(args));
      case "MIN": return Math.min(...numbers(args));
      case "COUNT": return numbers(args).length;
      case "AVERAGE": {
        const values = numbers(args);
        if (!values.length) throw new FormulaError("Нет чисел для среднего");
        return values.reduce((a, b) => a + b, 0) / values.length;
      }
      case "COUNTIF": {
        const [where, criterion] = args;
        if (!Array.isArray(where) || criterion === undefined) throw new FormulaError("СЧЁТЕСЛИ(диапазон; условие)");
        return where.filter((v) => matches(v, criterion)).length;
      }
      case "SUMIF": {
        const [where, criterion, sumRange] = args;
        if (!Array.isArray(where) || criterion === undefined) throw new FormulaError("СУММЕСЛИ(диапазон; условие; [сумма])");
        const target = Array.isArray(sumRange) ? sumRange : where;
        return where.reduce<number>((acc, v, k) => (matches(v, criterion) ? acc + (toNumber(String(target[k] ?? "")) ?? 0) : acc), 0);
      }
      case "ABS": return Math.abs(num(args[0] ?? 0));
      case "MOD": {
        const b = num(args[1] ?? 1);
        const a = num(args[0] ?? 0);
        return ((a % b) + b) % b;
      }
    }
    throw new FormulaError(`Неизвестная функция ${name}`);
  }

  function primary(): Value {
    const tok = take();
    if (!tok) throw new FormulaError("Формула оборвалась");
    switch (tok.t) {
      case "num": return tok.v;
      case "str": return tok.v;
      case "ref": return cell(tok.v);
      case "range": return range(tok.from, tok.to);
      case "name": return call(tok.v);
      case "op":
        if (tok.v === "(") {
          const v = expr();
          expectOp(")");
          return v;
        }
        if (tok.v === "-") return -num(primary());
        if (tok.v === "+") return num(primary());
    }
    throw new FormulaError("Неожиданный символ");
  }

  function power(): Value {
    let left = primary();
    while (peek()?.t === "op" && (peek() as { v: string }).v === "^") {
      take();
      left = num(left) ** num(primary());
    }
    return left;
  }

  function term(): Value {
    let left = power();
    while (peek()?.t === "op" && ["*", "/"].includes((peek() as { v: string }).v)) {
      const op = (take() as { v: string }).v;
      const right = num(power());
      if (op === "/" && right === 0) throw new FormulaError("Деление на ноль");
      left = op === "*" ? num(left) * right : num(left) / right;
    }
    return left;
  }

  function expr(): Value {
    let left = term();
    while (peek()?.t === "op" && ["+", "-"].includes((peek() as { v: string }).v)) {
      const op = (take() as { v: string }).v;
      const right = num(term());
      left = op === "+" ? num(left) + right : num(left) - right;
    }
    return left;
  }

  const result = expr();
  if (i < tokens.length) throw new FormulaError("Лишние символы в конце формулы");
  if (Array.isArray(result)) throw new FormulaError("Результат — диапазон; оберните его в СУММ или МАКС");
  return typeof result === "number" ? Math.round(result * 1e9) / 1e9 : result;
}
