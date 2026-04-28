export type SourceTrust = {
  sourceName: string;
  authority: string;
  officialLink: string;
  lastVerified: string;
  isStale: boolean;
};

type ParsedSourceTrust = {
  content: string;
  trust: SourceTrust | null;
};

function parseTrustLines(lines: string[]): SourceTrust | null {
  const values: Record<string, string> = {};

  lines.forEach((line) => {
    const match = line.match(/^-+\s*([^:]+):\s*(.+)\s*$/);
    if (!match) {
      return;
    }

    const [, rawLabel, rawValue] = match;
    const label = rawLabel.trim().toLowerCase();
    const value = rawValue.trim();
    if (label && value) {
      values[label] = value;
    }
  });

  const sourceName = values.source ?? "";
  const authority = values.authority ?? "";
  const officialLink = values["official link"] ?? "";
  const lastVerified = values["last verified"] ?? "";

  if (!sourceName && !authority && !officialLink && !lastVerified) {
    return null;
  }

  return {
    sourceName,
    authority,
    officialLink,
    lastVerified,
    isStale: /stale/i.test(lastVerified),
  };
}

export function extractSourceTrust(markdown: string): ParsedSourceTrust {
  const normalized = markdown.trim();
  const trustHeading = /^####\s+Source Trust\s*$/m;
  const headingMatch = trustHeading.exec(normalized);

  if (!headingMatch || headingMatch.index === undefined) {
    return { content: normalized, trust: null };
  }

  const headingIndex = headingMatch.index;
  const before = normalized.slice(0, headingIndex).trimEnd();
  const afterHeading = normalized.slice(headingIndex + headingMatch[0].length);
  const afterLines = afterHeading.replace(/^\s*\n/, "").split("\n");
  const trustLines: string[] = [];
  let consumedLineCount = 0;

  for (const line of afterLines) {
    if (!line.trim()) {
      consumedLineCount += 1;
      break;
    }
    if (/^#{1,6}\s+/.test(line)) {
      break;
    }
    if (!/^-+\s*[^:]+:\s*.+$/.test(line.trim())) {
      break;
    }
    trustLines.push(line.trim());
    consumedLineCount += 1;
  }

  const trust = parseTrustLines(trustLines);
  if (!trust) {
    return { content: normalized, trust: null };
  }

  const remainingLines = afterLines.slice(consumedLineCount).join("\n").trimStart();
  const content = [before, remainingLines].filter(Boolean).join("\n\n").trim();

  return { content, trust };
}

function formatAuthority(authority: string) {
  const normalized = authority.trim();
  if (!normalized) {
    return "Source metadata available";
  }

  return normalized.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function badgeTone(isStale: boolean) {
  return isStale
    ? "border-amber-300 bg-amber-50 text-amber-900"
    : "border-pine/20 bg-pine/10 text-pine";
}

export function SourceTrustCard({
  trust,
  compact = false,
}: {
  trust: SourceTrust;
  compact?: boolean;
}) {
  return (
    <div
      className={`rounded-[1.4rem] border ${trust.isStale ? "border-amber-200 bg-amber-50/85" : "border-pine/15 bg-pine/8"} ${
        compact ? "p-4" : "p-5"
      }`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">Source trust</div>
          <div className="mt-2 text-sm font-semibold text-ink">{trust.sourceName || "Travel guidance source"}</div>
        </div>
        <div
          className={`rounded-full border px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] ${badgeTone(trust.isStale)}`}
        >
          {formatAuthority(trust.authority)}
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {trust.lastVerified ? (
          <div className="rounded-[1.15rem] border border-white/70 bg-white/80 px-4 py-3 text-sm text-slate">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate">Last verified</div>
            <div className="mt-1 font-semibold text-ink">{trust.lastVerified}</div>
          </div>
        ) : null}
        {trust.officialLink ? (
          <div className="rounded-[1.15rem] border border-white/70 bg-white/80 px-4 py-3 text-sm text-slate">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate">Official source</div>
            <a
              href={trust.officialLink}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-flex font-semibold text-coral underline-offset-2 hover:underline"
            >
              Check official source
            </a>
          </div>
        ) : null}
      </div>

      {trust.isStale ? (
        <div className="mt-4 rounded-[1.15rem] border border-amber-300 bg-white/75 px-4 py-3 text-sm text-amber-950">
          This entry guidance may be outdated. Verify the latest rules with the official immigration source before
          booking or travel.
        </div>
      ) : null}
    </div>
  );
}
