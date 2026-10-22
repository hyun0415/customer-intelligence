import { Fragment, ReactNode } from "react";
import { Source } from "../lib/api";


function showCitation(citationKey: string) {
  const target = document.getElementById(`citation-${citationKey}`);

  if (!target) return;
  const details = target.closest("details");

  if (details instanceof HTMLDetailsElement) details.open = true;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.classList.add("citation-highlight");
  window.setTimeout(() => target.classList.remove("citation-highlight"), 1600);
}


function inline(text: string, sources: Source[]): ReactNode[] {
  return text.split(/(\*\*.*?\*\*|`.*?`|\[\[cite:\d+\]\])/g).filter(Boolean).map((part, index) => {
    const citation = part.match(/^\[\[cite:(\d+)\]\]$/);

    if (citation) {
      const sourceIndex = sources.findIndex(
        (source) => source.parent_chunk_id === Number(citation[1]),
      );

      if (sourceIndex < 0) return null;
      const source = sources[sourceIndex];

      return (
        <button
          aria-label={`근거 ${sourceIndex + 1}: ${source.title} ${source.section_title || ""}`.trim()}
          className="citation-badge"
          key={index}
          onClick={() => showCitation(source.citation_key)}
          title={`${source.title} · ${source.section_title || "섹션 미상"}`}
          type="button"
        >
          {sourceIndex + 1}
        </button>
      );
    }

    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }

    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }

    return <Fragment key={index}>{part}</Fragment>;
  });
}


function tableCells(line: string) {
  const normalized = line.trim();
  const cells: string[] = [];
  let cell = "";

  for (let index = 0; index < normalized.length; index += 1) {
    const char = normalized[index];

    if (char === "\\" && (normalized[index + 1] === "|" || normalized[index + 1] === "\\")) {
      cell += normalized[++index];
    } else if (char === "|") {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += char;
    }
  }

  if (cells.length === 0) return null;
  cells.push(cell.trim());

  if (normalized.startsWith("|")) cells.shift();

  if (normalized.endsWith("|") && cells.length > 1 && cells.at(-1) === "") cells.pop();

  return cells;
}


function tableAlignments(line: string) {
  const cells = tableCells(line);

  if (!cells || !cells.every((cell) => /^:?-{3,}:?$/.test(cell))) return null;

  return cells.map((cell) => {
    if (cell.startsWith(":") && cell.endsWith(":")) return "center";

    if (cell.endsWith(":")) return "right";

    return "left";
  });
}


function renderLine(line: string, key: number, sources: Source[]) {
  if (!line.trim()) return <div className="markdown-space" key={key} />;

  if (line.startsWith("### ")) return <h3 key={key}>{inline(line.slice(4), sources)}</h3>;

  if (line.startsWith("## ")) return <h2 key={key}>{inline(line.slice(3), sources)}</h2>;
  const unordered = line.match(/^\s*-\s+(.+)$/);

  if (unordered) return <div className="markdown-list" key={key}><span>•</span><span>{inline(unordered[1], sources)}</span></div>;
  const ordered = line.match(/^\s*(\d+)\.\s+(.+)$/);

  if (ordered) return <div className="markdown-list" key={key}><span>{ordered[1]}.</span><span>{inline(ordered[2], sources)}</span></div>;

  return <p key={key}>{inline(line, sources)}</p>;
}


export function MessageContent({ content, sources = [] }: { content: string; sources?: Source[] }) {
  const lines = content.split("\n");
  const blocks: ReactNode[] = [];

  for (let index = 0; index < lines.length;) {
    const headers = tableCells(lines[index]);

    const alignments = index + 1 < lines.length
      ? tableAlignments(lines[index + 1])
      : null;

    if (headers && alignments && headers.length === alignments.length) {
      const rows: string[][] = [];
      let nextIndex = index + 2;

      while (nextIndex < lines.length) {
        const cells = tableCells(lines[nextIndex]);

        if (!cells || cells.length !== headers.length) break;
        rows.push(cells);
        nextIndex += 1;
      }

      blocks.push(
        <div className="markdown-table-wrap" key={`table-${index}`}>
          <table className="markdown-table">
            <thead>
              <tr>
                {headers.map((header, cellIndex) => (
                  <th className={`align-${alignments[cellIndex]}`} key={cellIndex}>
                    {inline(header, sources)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td className={`align-${alignments[cellIndex]}`} key={cellIndex}>
                      {inline(cell, sources)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      index = nextIndex;
      continue;
    }

    blocks.push(renderLine(lines[index], index, sources));
    index += 1;
  }

  return <div className="markdown">{blocks}</div>;
}
