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


export function MessageContent({ content }: { content: string }) {
  return (
    <div className="markdown">
      {content.split("\n").map((line, index) => {
        if (!line.trim()) return <div className="markdown-space" key={index} />;
        if (line.startsWith("### ")) return <h3 key={index}>{inline(line.slice(4))}</h3>;
        if (line.startsWith("## ")) return <h2 key={index}>{inline(line.slice(3))}</h2>;
        const unordered = line.match(/^\s*-\s+(.+)$/);
        if (unordered) return <div className="markdown-list" key={index}><span>•</span><span>{inline(unordered[1])}</span></div>;
        const ordered = line.match(/^\s*(\d+)\.\s+(.+)$/);
        if (ordered) return <div className="markdown-list" key={index}><span>{ordered[1]}.</span><span>{inline(ordered[2])}</span></div>;
        return <p key={index}>{inline(line)}</p>;
      })}
    </div>
  );
}
