import { describe, expect, it } from "vitest";

import { FormulaError, columnIndex, columnName, evaluate, filterRows, parseCsv, sortRows } from "../src/lib/sheet";

const table = parseCsv("Имя;Балл;Класс\nАня;5;10\nБоря;3;11\nВера;4;10\nГоша;5;11\n");

describe("csv", () => {
  it("detects the delimiter and handles quotes", () => {
    expect(table[1]).toEqual(["Аня", "5", "10"]);
    expect(parseCsv('a,b\n"x, y",2\n')[1]).toEqual(["x, y", "2"]);
    expect(parseCsv('a\n"say ""hi"""\n')[1]).toEqual(['say "hi"']);
  });

  it("names columns like a spreadsheet", () => {
    expect([0, 25, 26, 27, 701].map(columnName)).toEqual(["A", "Z", "AA", "AB", "ZZ"]);
    expect(columnIndex("AB")).toBe(27);
  });

  it("sorts numbers numerically and filters", () => {
    const body = table.slice(1);
    expect(sortRows(body, 1, false).map((r) => r[0])).toEqual(["Боря", "Вера", "Аня", "Гоша"]);
    expect(filterRows(body, "11").map((r) => r[0])).toEqual(["Боря", "Гоша"]);
  });
});

describe("formulas", () => {
  it("computes the functions of the task-9 toolbox", () => {
    expect(evaluate("=СУММ(B2:B5)", table)).toBe(17);
    expect(evaluate("=МАКС(B2:B5)-МИН(B2:B5)", table)).toBe(2);
    expect(evaluate('=СЧЁТЕСЛИ(B2:B5;">=4")', table)).toBe(3);
    expect(evaluate('=СУММЕСЛИ(C2:C5;"10";B2:B5)', table)).toBe(9);
    expect(evaluate("=СРЗНАЧ(B2:B5)", table)).toBe(4.25);
    expect(evaluate("=COUNT(B2:C5)", table)).toBe(8);
    expect(evaluate("=(B2+B3)*2^2/4", table)).toBe(8);
    expect(evaluate("=ОСТАТ(-7;3)", table)).toBe(2);
  });

  it("explains mistakes in Russian", () => {
    expect(() => evaluate("=СУММ(B2:B5", table)).toThrow(FormulaError);
    expect(() => evaluate("=ФОО(1)", table)).toThrow(/Неизвестная функция/);
    expect(() => evaluate("=B2/0", table)).toThrow(/Деление на ноль/);
    expect(() => evaluate("=B2:B5", table)).toThrow(/диапазон/);
  });
});
