import { describe, expect, it } from "vitest";

import { decodeAuthResult } from "../src/screens/WebLogin";

describe("Telegram login redirect", () => {
  it("decodes tgAuthResult", () => {
    const payload = { id: 42, first_name: "Аня", auth_date: 1700000000, hash: "abc" };
    const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(payload)))).replace(/\+/g, "-").replace(/\//g, "_");
    expect(decodeAuthResult(`#tgAuthResult=${encoded}`)).toEqual(payload);
    expect(decodeAuthResult("#nothing")).toBeNull();
    expect(decodeAuthResult("#tgAuthResult=%%%")).toBeNull();
  });
});
