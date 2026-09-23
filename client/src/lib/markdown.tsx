// A small, safe Markdown renderer for task statements and method cards.
// It builds React elements (never innerHTML), so generated text cannot inject markup.
// Supported: headings, paragraphs, lists, fenced code, tables, **bold**, *italic*,
// `code`, and $…$ kept as plain text.
import { Fragment, type ReactNode } from "react";

export type Block =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "code"; lang: string; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "table"; header: string[]; rows: string[][] }
  | { type: "quote"; text: string }
  | { type: "rule" };

const TABLE_SEPARATOR = /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

function splitRow(line: string): string[] {
  let body = line.trim();
  if (body.startsWith("|")) body = body.slice(1);
  if (body.endsWith("|")) body = body.slice(0, -1);
  return body.split("|").map((cell) => cell.trim());
}

export function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    if (!line.trim()) {
      i++;
      continue;
    }
    const fence = /^```(\w*)\s*$/.exec(line.trim());
    if (fence) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test((lines[i] ?? "").trim())) body.push(lines[i++] ?? "");
      i++;
      blocks.push({ type: "code", lang: fence[1] ?? "", text: body.join("\n") });
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1]!.length, text: heading[2] ?? "" });
      i++;
      continue;
    }
    if (/^(-{3,}|\*{3,})\s*$/.test(line.trim())) {
      blocks.push({ type: "rule" });
      i++;
      continue;
    }
    if (line.trim().startsWith("|") && TABLE_SEPARATOR.test((lines[i + 1] ?? "").trim())) {
      const header = splitRow(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && (lines[i] ?? "").trim().startsWith("|")) rows.push(splitRow(lines[i++] ?? ""));
      blocks.push({ type: "table", header, rows });
      continue;
    }
    const bullet = /^\s*([-*•]|\d+[.)])\s+/;
    if (bullet.test(line)) {
      const ordered = /^\s*\d/.test(line);
      const items: string[] = [];
      while (i < lines.length && bullet.test(lines[i] ?? "")) {
        let item = (lines[i] ?? "").replace(bullet, "");
        i++;
        while (i < lines.length && /^\s{2,}\S/.test(lines[i] ?? "") && !bullet.test(lines[i] ?? "")) {
          item += " " + (lines[i] ?? "").trim();
          i++;
        }
        items.push(item);
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }
    if (line.startsWith(">")) {
      const quote: string[] = [];
      while (i < lines.length && (lines[i] ?? "").startsWith(">")) quote.push((lines[i++] ?? "").replace(/^>\s?/, ""));
      blocks.push({ type: "quote", text: quote.join(" ") });
      continue;
    }
    const paragraph: string[] = [];
    while (
      i < lines.length &&
      (lines[i] ?? "").trim() &&
      !/^```/.test((lines[i] ?? "").trim()) &&
      !/^#{1,4}\s/.test(lines[i] ?? "") &&
      !(lines[i] ?? "").trim().startsWith("|") &&
      !bullet.test(lines[i] ?? "")
    ) {
      paragraph.push((lines[i] ?? "").trim());
      i++;
    }
    blocks.push({ type: "paragraph", text: paragraph.join(" ") });
  }
  return blocks;
}

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;

export function renderInline(text: string): ReactNode[] {
  const parts = text.split(INLINE);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    if (
      ((part.startsWith("*") && part.endsWith("*")) || (part.startsWith("_") && part.endsWith("_"))) &&
      part.length > 2
    ) {
      return <em key={index}>{part.slice(1, -1)}</em>;
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

export function Markdown({ source, className }: { source: string; className?: string }) {
  const blocks = parseBlocks(source);
  return (
    <div className={className ?? "md"}>
      {blocks.map((block, index) => {
        switch (block.type) {
          case "heading": {
            const Tag = (["h3", "h3", "h4", "h5"] as const)[block.level - 1] ?? "h5";
            return <Tag key={index}>{renderInline(block.text)}</Tag>;
          }
          case "paragraph":
            return <p key={index}>{renderInline(block.text)}</p>;
          case "code":
            return (
              <pre key={index} className="code-block">
                <code>{block.text}</code>
              </pre>
            );
          case "list": {
            const Tag = block.ordered ? "ol" : "ul";
            return (
              <Tag key={index}>
                {block.items.map((item, j) => (
                  <li key={j}>{renderInline(item)}</li>
                ))}
              </Tag>
            );
          }
          case "table":
            return (
              <div key={index} className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      {block.header.map((cell, j) => (
                        <th key={j}>{renderInline(cell)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, r) => (
                      <tr key={r}>
                        {row.map((cell, j) => (
                          <td key={j}>{renderInline(cell)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          case "quote":
            return <blockquote key={index}>{renderInline(block.text)}</blockquote>;
          case "rule":
            return <hr key={index} />;
        }
        return null;
      })}
    </div>
  );
}
