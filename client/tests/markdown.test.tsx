import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown, parseBlocks } from "../src/lib/markdown";

describe("parseBlocks", () => {
  it("reads the statement shapes the generators produce", () => {
    const blocks = parseBlocks(
      "# Задание\n\nТекст **жирный** и `код`.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\n```python\nprint(1)\n```\n\n- раз\n- два\n",
    );
    expect(blocks.map((b) => b.type)).toEqual(["heading", "paragraph", "table", "code", "list"]);
    const table = blocks[2];
    expect(table?.type === "table" && table.rows).toEqual([["1", "2"], ["3", "4"]]);
  });

  it("keeps multi-line paragraphs together", () => {
    const blocks = parseBlocks("строка один\nстрока два\n\nновый абзац");
    expect(blocks).toEqual([
      { type: "paragraph", text: "строка один строка два" },
      { type: "paragraph", text: "новый абзац" },
    ]);
  });
});

describe("Markdown", () => {
  it("never injects raw HTML", () => {
    const { container } = render(<Markdown source={'<img src=x onerror="alert(1)"> **ok**'} />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("ok").tagName).toBe("STRONG");
  });

  it("renders tables and code", () => {
    const { container } = render(<Markdown source={"| x |\n|---|\n| 7 |\n\n```\nfor i in range(3): pass\n```"} />);
    expect(container.querySelector("td")?.textContent).toBe("7");
    expect(container.querySelector("pre code")?.textContent).toContain("range(3)");
  });
});
