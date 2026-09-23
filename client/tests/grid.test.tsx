import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Grid } from "../src/components/Grid";
import { parseCsv } from "../src/lib/sheet";

describe("Grid", () => {
  it("sorts on header click and evaluates the formula bar", () => {
    const table = parseCsv("x;y\n3;a\n1;b\n2;c\n");
    const { container } = render(<Grid table={table} />);
    fireEvent.click(screen.getByText("x", { exact: false, selector: "th" }));
    const first = () => container.querySelector("tbody tr td:nth-child(2)")?.textContent;
    expect(first()).toBe("1");
    fireEvent.click(screen.getByText("x", { exact: false, selector: "th" }));
    expect(first()).toBe("3");
    fireEvent.change(screen.getByLabelText("Формула"), { target: { value: "=СУММ(A2:A4)" } });
    expect(screen.getByText("6")).toBeTruthy();
  });
});
