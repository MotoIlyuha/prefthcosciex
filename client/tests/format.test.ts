import { describe, expect, it } from "vitest";

import { answerWarning, clock, fileSize, plural } from "../src/lib/format";

describe("format", () => {
  it("pluralises Russian nouns", () => {
    expect([1, 2, 5, 11, 21, 22, 25].map((n) => plural(n, "день", "дня", "дней"))).toEqual([
      "день", "дня", "дней", "дней", "день", "дня", "дней",
    ]);
  });

  it("formats time and sizes", () => {
    expect(clock(65)).toBe("01:05");
    expect(clock(3 * 3600 + 55 * 60)).toBe("3:55:00");
    expect(fileSize(43063)).toBe("42 КБ");
    expect(fileSize(7 * 1024 * 1024)).toBe("7.0 МБ");
  });

  it("warns about the answer format before sending", () => {
    expect(answerWarning("int", "12a")).toBe("Ожидается целое число");
    expect(answerWarning("int", " 1 024 ")).toBeNull();
    expect(answerWarning("two_ints", "12")).toBe("Нужно два числа");
    expect(answerWarning("two_ints", "12 30")).toBeNull();
    expect(answerWarning("letters", "ab1")).not.toBeNull();
    expect(answerWarning("letters", "")).toBe("Введите ответ");
  });
});
