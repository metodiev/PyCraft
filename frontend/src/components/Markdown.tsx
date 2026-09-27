/**
 * Lightweight Markdown renderer for challenge briefings.
 *
 * Supports exactly the subset challenge authors use — headings, paragraphs,
 * lists, tables, fenced code, inline code, bold/italic and collapsible
 * ``<details>`` hints — rather than pulling in a full Markdown engine.
 */

import { Fragment, useMemo } from "react";
import type { ReactNode } from "react";
import "./markdown.css";

export function Markdown({ source }: { source: string }) {
  const blocks = useMemo(() => parseBlocks(source), [source]);
  return <div className="markdown">{blocks}</div>;
}

type Token =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "code"; language: string; lines: string[] }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "details"; summary: string; body: string[] };

function parseBlocks(source: string): ReactNode[] {
  const lines = source.split("\n");
  const blocks: Token[] = [];

  for (let i = 0; i < lines.length; ) {
    const line = lines[i] ?? "";

    if (line.trim() === "") {
      i += 1;
      continue;
    }

    // Fenced code block.
    if (line.trimStart().startsWith("```")) {
      const language = line.trim().slice(3).trim();
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !(lines[i] ?? "").trimStart().startsWith("```")) {
        body.push(lines[i] ?? "");
        i += 1;
      }
      i += 1; // consume the closing fence
      blocks.push({ kind: "code", language, lines: body });
      continue;
    }

    // <details><summary>…</summary> hint block.
    if (line.trim().startsWith("<details>")) {
      const summaryLine = lines[i + 1] ?? "";
      const summary = summaryLine.replace(/<\/?summary>/g, "").replace(/#+\s*/, "").trim();
      const body: string[] = [];
      i += 2;
      while (i < lines.length && !(lines[i] ?? "").trim().startsWith("</details>")) {
        body.push(lines[i] ?? "");
        i += 1;
      }
      i += 1; // consume </details>
      blocks.push({ kind: "details", summary, body });
      continue;
    }

    // ATX heading.
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading !== null) {
      blocks.push({
        kind: "heading",
        level: (heading[1] ?? "#").length,
        text: (heading[2] ?? "").trim(),
      });
      i += 1;
      continue;
    }

    // Table: header row followed by a separator row of dashes.
    if (line.includes("|") && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1] ?? "")) {
      const header = splitTableRow(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && (lines[i] ?? "").includes("|")) {
        rows.push(splitTableRow(lines[i] ?? ""));
        i += 1;
      }
      blocks.push({ kind: "table", header, rows });
      continue;
    }

    // List (unordered or ordered).
    const listMatch = /^\s*([-*+]|\d+\.)\s+/.exec(line);
    if (listMatch !== null) {
      const ordered = /\d+\./.test(listMatch[1] ?? "");
      const items: string[] = [];
      while (i < lines.length && /^\s*([-*+]|\d+\.)\s+/.test(lines[i] ?? "")) {
        items.push((lines[i] ?? "").replace(/^\s*([-*+]|\d+\.)\s+/, ""));
        i += 1;
      }
      blocks.push({ kind: "list", ordered, items });
      continue;
    }

    // Paragraph: consume until a blank line or another block starter.
    const paragraph: string[] = [];
    while (
      i < lines.length &&
      (lines[i] ?? "").trim() !== "" &&
      !/^(#{1,6}\s|\s*```|\s*<details>)/.test(lines[i] ?? "") &&
      !/^\s*([-*+]|\d+\.)\s+/.test(lines[i] ?? "")
    ) {
      paragraph.push(lines[i] ?? "");
      i += 1;
    }
    if (paragraph.length > 0) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
    } else {
      i += 1; // defensive: never spin on an unhandled line
    }
  }

  return blocks.map((block, index) => <Block key={index} token={block} />);
}

function Block({ token }: { token: Token }) {
  switch (token.kind) {
    case "heading": {
      const Tag = `h${Math.min(6, token.level + 1)}` as "h2" | "h3" | "h4" | "h5" | "h6";
      return <Tag>{renderInline(token.text)}</Tag>;
    }
    case "paragraph":
      return <p>{renderInline(token.text)}</p>;
    case "code":
      return (
        <pre className="md-code" data-language={token.language}>
          <code>{token.lines.join("\n")}</code>
        </pre>
      );
    case "list": {
      const items = token.items.map((item, index) => <li key={index}>{renderInline(item)}</li>);
      return token.ordered ? <ol>{items}</ol> : <ul>{items}</ul>;
    }
    case "table":
      return (
        <div className="md-table-wrap">
          <table className="md-table">
            <thead>
              <tr>
                {token.header.map((cell, index) => (
                  <th key={index}>{renderInline(cell)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {token.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex}>{renderInline(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "details":
      return (
        <details className="md-details">
          <summary>{token.summary || "Hint"}</summary>
          <div className="md-details-body">{parseBlocks(token.body.join("\n"))}</div>
        </details>
      );
  }
}

/** Handles `code`, **bold**, *italic* and [links](url). */
function renderInline(text: string): ReactNode {
  const pattern = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(\[[^\]]+\]\([^)]+\))/g;
  const parts: ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) parts.push(text.slice(cursor, match.index));
    const token = match[0];

    if (token.startsWith("`")) {
      parts.push(<code key={key++} className="md-inline-code">{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**")) {
      parts.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("*")) {
      parts.push(<em key={key++}>{token.slice(1, -1)}</em>);
    } else {
      const link = /\[([^\]]+)\]\(([^)]+)\)/.exec(token);
      if (link !== null) {
        parts.push(
          <a key={key++} href={link[2]} target="_blank" rel="noreferrer noopener">
            {link[1]}
          </a>,
        );
      }
    }
    cursor = match.index + token.length;
  }

  if (cursor < text.length) parts.push(text.slice(cursor));
  return <Fragment>{parts}</Fragment>;
}

function splitTableRow(line: string): string[] {
  return line
    .replace(/^\s*\|/, "")
    .replace(/\|\s*$/, "")
    .split("|")
    .map((cell) => cell.trim());
}
