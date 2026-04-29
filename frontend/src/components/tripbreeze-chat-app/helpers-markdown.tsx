import type { ReactNode } from "react";

const bareUrlPattern = /https?:\/\/[^\s)]+/g;

function normalizeBookingLinks(content: string) {
  const lines = content.split("\n");
  const normalizedLines: string[] = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const nextLine = lines[index + 1]?.trim() ?? "";
    const bookingOnlyMatch = /^(\s*[-*]\s+)?Booking:\s*$/i.exec(line.trim());
    const nextLineUrlMatch = /^(https?:\/\/\S+)$/.exec(nextLine);

    if (bookingOnlyMatch && nextLineUrlMatch) {
      const bullet = bookingOnlyMatch[1] ? "- " : "";
      normalizedLines.push(`${bullet}Booking: [Open booking link](${nextLineUrlMatch[1]})`);
      index += 1;
      continue;
    }

    normalizedLines.push(
      line.replace(/Booking:\s*(https?:\/\/\S+)/gi, "Booking: [Open booking link]($1)"),
    );
  }

  return normalizedLines.join("\n");
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\((https?:\/\/[^)\s]+)\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  function pushPlainText(value: string, keyPrefix: string) {
    let plainLastIndex = 0;
    let urlMatch: RegExpExecArray | null;

    bareUrlPattern.lastIndex = 0;
    urlMatch = bareUrlPattern.exec(value);
    while (urlMatch) {
      if (urlMatch.index > plainLastIndex) {
        parts.push(value.slice(plainLastIndex, urlMatch.index));
      }

      const href = urlMatch[0];
      parts.push(
        <a
          key={`${keyPrefix}-${urlMatch.index}-bare-link`}
          href={href}
          target="_blank"
          rel="noreferrer"
          className="font-semibold text-coral underline-offset-2 break-words hover:underline"
        >
          Open link
        </a>,
      );

      plainLastIndex = bareUrlPattern.lastIndex;
      urlMatch = bareUrlPattern.exec(value);
    }

    if (plainLastIndex < value.length) {
      parts.push(value.slice(plainLastIndex));
    }
  }

  match = pattern.exec(text);
  while (match) {
    if (match.index > lastIndex) {
      pushPlainText(text.slice(lastIndex, match.index), `${lastIndex}-${match.index}`);
    }

    const token = match[0];
    if (token.startsWith("**") && token.endsWith("**")) {
      parts.push(<strong key={`${match.index}-bold`}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`") && token.endsWith("`")) {
      parts.push(
        <code key={`${match.index}-code`} className="rounded bg-black/5 px-1 py-0.5 text-[0.95em]">
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("[") && token.includes("](") && token.endsWith(")")) {
      const closingBracket = token.indexOf("](");
      const label = token.slice(1, closingBracket);
      const href = token.slice(closingBracket + 2, -1);
      parts.push(
        <a
          key={`${match.index}-link`}
          href={href}
          target="_blank"
          rel="noreferrer"
          className="font-semibold text-coral underline-offset-2 break-words hover:underline"
        >
          {label}
        </a>,
      );
    }

    lastIndex = pattern.lastIndex;
    match = pattern.exec(text);
  }

  if (lastIndex < text.length) {
    pushPlainText(text.slice(lastIndex), `${lastIndex}-${text.length}`);
  }

  return parts;
}

export function renderMarkdownContent(content: string) {
  const normalized = normalizeBookingLinks(content)
    .replace(/\r\n/g, "\n")
    .replace(/([^\n])\s(#{2,6}\s)/g, "$1\n$2")
    .trim();

  if (!normalized) {
    return null;
  }

  const lines = normalized.split("\n");
  const nodes: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();

    if (!line) {
      index += 1;
      continue;
    }

    const headingMatch = /^(#{1,6})\s+(.*)$/.exec(line);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      const className =
        level === 1
          ? "text-xl font-semibold"
          : level === 2
            ? "text-lg font-semibold"
            : level === 3
              ? "text-base font-semibold"
              : "text-sm font-semibold";
      nodes.push(
        <div key={`heading-${index}`} className={`${className} mt-1`}>
          {renderInlineMarkdown(text)}
        </div>,
      );
      index += 1;
      continue;
    }

    if (/^\|.*\|$/.test(line)) {
      const tableLines: string[] = [];
      while (index < lines.length && /^\|.*\|$/.test(lines[index].trim())) {
        tableLines.push(lines[index].trim());
        index += 1;
      }

      const rows = tableLines
        .filter((row, rowIndex) => rowIndex !== 1 || !/^(\|\s*:?-+:?\s*)+\|?$/.test(row))
        .map((row) => row.split("|").slice(1, -1).map((cell) => cell.trim()));

      if (rows.length) {
        const [header, ...body] = rows;
        nodes.push(
          <div key={`table-${index}`} className="overflow-x-auto">
            <table className="mt-2 min-w-full border-collapse text-sm">
              <thead>
                <tr>
                  {header.map((cell, cellIndex) => (
                    <th key={`th-${cellIndex}`} className="border-b border-black/10 px-2 py-2 text-left font-semibold">
                      {renderInlineMarkdown(cell)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {body.map((row, rowIndex) => (
                  <tr key={`tr-${rowIndex}`} className="border-b border-black/5">
                    {row.map((cell, cellIndex) => (
                      <td key={`td-${rowIndex}-${cellIndex}`} className="px-2 py-2 align-top">
                        {renderInlineMarkdown(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>,
        );
      }
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      nodes.push(
        <ul key={`list-${index}`} className="ml-5 list-disc space-y-1">
          {items.map((item, itemIndex) => (
            <li key={`li-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    const paragraphLines: string[] = [];
    while (index < lines.length) {
      const current = lines[index].trim();
      if (!current || /^(#{1,6})\s+/.test(current) || /^\|.*\|$/.test(current) || /^[-*]\s+/.test(current)) {
        break;
      }
      paragraphLines.push(current);
      index += 1;
    }

    const paragraph = paragraphLines.join(" ");
    nodes.push(
      <p key={`p-${index}`} className="leading-7">
        {renderInlineMarkdown(paragraph)}
      </p>,
    );
  }

  return <div className="space-y-3 whitespace-pre-wrap">{nodes}</div>;
}
