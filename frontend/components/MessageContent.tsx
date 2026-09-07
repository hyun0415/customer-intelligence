import { Fragment, ReactNode } from "react";


function inline(text: string): ReactNode[] {
  return text.split(/(\*\*.*?\*\*|`.*?`)/g).filter(Boolean).map((part, index) => {
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
  let normalized = line.trim().replaceAll("\\|", "|");
  if (!normalized.includes("|")) return null;
  if (normalized.startsWith("|")) normalized = normalized.slice(1);
  if (normalized.endsWith("|")) normalized = normalized.slice(0, -1);
  return normalized.split("|").map((cell) => cell.trim());
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


function renderLine(line: string, key: number) {
  if (!line.trim()) return <div className="markdown-space" key={key} />;
  if (line.startsWith("### ")) return <h3 key={key}>{inline(line.slice(4))}</h3>;
  if (line.startsWith("## ")) return <h2 key={key}>{inline(line.slice(3))}</h2>;
  const unordered = line.match(/^\s*-\s+(.+)$/);
  if (unordered) return <div className="markdown-list" key={key}><span>•</span><span>{inline(unordered[1])}</span></div>;
  const ordered = line.match(/^\s*(\d+)\.\s+(.+)$/);
  if (ordered) return <div className="markdown-list" key={key}><span>{ordered[1]}.</span><span>{inline(ordered[2])}</span></div>;
  return <p key={key}>{inline(line)}</p>;
}


export function MessageContent({ content }: { content: string }) {
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
                    {inline(header)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td className={`align-${alignments[cellIndex]}`} key={cellIndex}>
                      {inline(cell)}
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

    blocks.push(renderLine(lines[index], index));
    index += 1;
  }

  return <div className="markdown">{blocks}</div>;
}
