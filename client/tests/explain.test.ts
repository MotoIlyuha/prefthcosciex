import { describe, expect, it } from "vitest";

import { explainLine } from "../src/lib/explain";

describe("explainLine", () => {
  it("explains ranges with the excluded right bound", () => {
    expect(explainLine("for n in range(1, 100):")[0]).toContain("от 1 до 100 − 1");
  });

  it("warns about replace without a limit (task 12)", () => {
    expect(explainLine("s = s.replace('12', '1')")[0]).toContain("ВСЕ вхождения");
    expect(explainLine("s = s.replace('12', '1', 1)")[0]).toContain("ПЕРВОЕ");
  });

  it("names the operators used", () => {
    const notes = explainLine("if x % 10 == 7 and x // 2 > 5:");
    expect(notes).toContain("% — остаток от деления");
    expect(notes.some((n) => n.startsWith("//"))).toBe(true);
  });

  it("ignores operators inside strings and comments", () => {
    expect(explainLine("print('%')  # 50 % 3")).toEqual(["Выводим на экран: '%'."]);
  });

  it("reads base conversions and caching", () => {
    expect(explainLine("n = int(s, 3)").join(" ")).toContain("основанием 3");
    expect(explainLine("@lru_cache(None)")[0]).toContain("кэш");
  });
});
