import type { ReactNode } from "react";

import { formatCurrency } from "@/lib/planner";
import type { TripOption } from "@/lib/types";

import { HOTEL_STARS } from "./constants";
import {
  flightBadges,
  flightPricePills,
  formatHourLabel,
  hotelBadges,
  hotelBreakfast,
  hotelMetaPills,
  hotelRating,
  hotelStarSummary,
  stopLabel,
  transportBadges,
  transportLabel,
} from "./helpers";

export function HotelStarTierPicker({
  label,
  helper,
  thresholds,
  onChange,
}: {
  label: string;
  helper?: string;
  thresholds: number[];
  onChange: (thresholds: number[]) => void;
}) {
  const selected = [...new Set(thresholds)].sort((a, b) => a - b);
  const selectedTier = selected[0] ?? null;

  return (
    <div>
      <div className="mb-2 block text-sm font-medium text-slate">{label}</div>
      {helper ? <div className="mb-3 text-sm text-slate">{helper}</div> : null}
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        <button
          type="button"
          onClick={() => onChange([])}
          className={`rounded-2xl px-4 py-3 text-left text-sm transition ${
            selectedTier === null ? "bg-ink text-white" : "border border-ink/10 bg-white text-slate"
          }`}
        >
          <div className="font-semibold">Any</div>
          <div className={`mt-1 text-xs ${selectedTier === null ? "text-white/75" : "text-slate"}`}>
            No hotel star preference
          </div>
        </button>
        {HOTEL_STARS.slice().sort((a, b) => a - b).map((star) => {
          const active = selectedTier === star;
          return (
            <button
              key={star}
              type="button"
              onClick={() => onChange(active ? [] : [star])}
              className={`rounded-2xl px-4 py-3 text-left text-sm transition ${
                active ? "bg-ink text-white" : "border border-ink/10 bg-white text-slate"
              }`}
            >
              <div className="font-semibold">{star}-star and up</div>
              <div className={`mt-1 text-xs ${active ? "text-white/75" : "text-slate"}`}>
                Minimum {star}-star hotels
              </div>
            </button>
          );
        })}
      </div>
      {selectedTier !== null ? (
        <div className="mt-3 text-sm text-slate">
          Selected: {selectedTier}-star and up
        </div>
      ) : (
        <div className="mt-3 text-sm text-slate">Selected: Any hotel tier</div>
      )}
    </div>
  );
}

export function ReviewOptionCard({
  option,
  title,
  variant,
  allOptions,
  selected,
  onSelect,
  currencyCode,
}: {
  option: TripOption;
  title: string;
  variant: "flight" | "hotel" | "transport";
  allOptions: TripOption[];
  selected: boolean;
  onSelect: () => void;
  currencyCode: string;
}) {
  const badges =
    variant === "flight"
      ? flightBadges(allOptions, option)
      : variant === "hotel"
        ? hotelBadges(allOptions, option)
        : transportBadges(allOptions, option);
  const flightSummary =
    variant === "flight"
      ? String(option.outbound_summary ?? option.return_summary ?? option.description ?? option.duration ?? "Details available")
      : "";
  const ratingLabel = variant === "hotel" ? hotelRating(option) : "";
  const breakfastStatus = variant === "hotel" ? hotelBreakfast(option) : "";
  const mode = variant === "transport" ? transportLabel(option.mode) : "";
  const bookingLabel =
    variant === "flight"
      ? "View on Google Flights"
      : variant === "hotel"
        ? "View on Google Hotels"
        : "View on Google Maps Transit";
  const flightPriceMeta = variant === "flight" ? flightPricePills(option, currencyCode) : null;
  const metaPills =
    variant === "flight"
      ? [
          option.duration ? String(option.duration) : "",
          typeof option.stops === "number" ? stopLabel(option.stops) : "",
          ...(flightPriceMeta?.standard ?? []),
        ].filter(Boolean)
      : [];
  const hotelPills =
    variant === "hotel" ? hotelMetaPills(option, currencyCode, ratingLabel) : [];
  const hotelAddress = variant === "hotel" ? String(option.address ?? "").trim() : "";
  const hotelTotalPrice = variant === "hotel" ? Number(option.total_price ?? option.price ?? 0) : 0;
  const hotelSummary =
    variant === "hotel"
      ? hotelAddress || String(option.description ?? "Details available").trim()
      : "";
  const hotelDescription =
    variant === "hotel" ? String(option.description ?? "").trim() : "";
  const hotelStars = variant === "hotel" ? hotelStarSummary(option) : "";

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-[1.6rem] border p-4 text-left transition ${
        selected
          ? "border-coral bg-gradient-to-br from-[#fff3ee] to-[#fff8f2] shadow-[0_18px_45px_rgba(215,108,78,0.14)]"
          : "border-ink/10 bg-white hover:-translate-y-0.5 hover:border-coral/40 hover:shadow-[0_14px_34px_rgba(16,33,43,0.08)]"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="font-semibold text-ink">{String(option.name ?? option.airline ?? title)}</div>
          {variant === "hotel" && hotelStars ? (
            <div className="mt-1 text-sm font-medium text-coral">{hotelStars}</div>
          ) : null}
          <div className="mt-1 text-sm text-slate">
            {variant === "flight"
              ? flightSummary
              : variant === "hotel"
                ? hotelSummary
                : String(option.description ?? option.duration ?? "Details available")}
          </div>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${
            selected ? "bg-coral text-white" : "bg-mist text-slate"
          }`}
        >
          {selected ? "Selected" : "Option"}
        </span>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate">
        {badges.map((badge) => (
          <span
            key={badge}
            className={`rounded-full px-3 py-1 font-semibold ${
              variant === "flight" || variant === "hotel"
                ? "bg-coral text-white shadow-[0_8px_18px_rgba(215,108,78,0.22)]"
                : "bg-white/80 text-ink"
            }`}
          >
            {badge}
          </span>
        ))}
        {variant === "transport" && mode ? <span>{mode}</span> : null}
        {variant === "flight"
          ? metaPills.map((pill) => (
              <span key={pill} className="rounded-full bg-white/80 px-3 py-1 font-semibold text-ink">
                {pill}
              </span>
            ))
          : variant === "hotel"
            ? (
              <>
                {hotelPills.map((pill) => (
                  <span key={pill} className="rounded-full bg-white/80 px-3 py-1 font-semibold text-ink">
                    {pill}
                  </span>
                ))}
                {breakfastStatus ? (
                  <span className="rounded-full bg-white/80 px-3 py-1 font-semibold text-ink">
                    {breakfastStatus}
                  </span>
                ) : null}
                {hotelTotalPrice > 0 ? (
                  <span className="rounded-full bg-ink px-3 py-1 font-semibold text-white">
                    {formatCurrency(hotelTotalPrice, currencyCode)} total
                  </span>
                ) : null}
              </>
            )
          : (
            <>
              {option.duration ? <span>{String(option.duration)}</span> : null}
              {typeof option.stops === "number" ? (
                <span>{stopLabel(option.stops)}</span>
              ) : null}
              <span className="rounded-full bg-white/80 px-3 py-1 font-semibold text-ink">
                {formatCurrency(option.total_price ?? option.price, currencyCode)}
              </span>
            </>
          )}
        {variant === "flight" && flightPriceMeta?.highlighted ? (
          <span className="rounded-full bg-ink px-3 py-1 font-semibold text-white">
            {flightPriceMeta.highlighted}
          </span>
        ) : null}
      </div>
      {variant === "hotel" ? (
        <div className="mt-3 space-y-1 text-sm text-slate">
          {hotelDescription && hotelDescription !== hotelSummary ? (
            <div className="leading-6">{hotelDescription}</div>
          ) : null}
        </div>
      ) : null}
      {variant === "transport" ? (
        <div className="mt-3 space-y-1 text-sm text-slate">
          {option.segments_summary ? <div>Route: {String(option.segments_summary)}</div> : null}
          {(option.departure_time || option.arrival_time) ? (
            <div>
              Depart: {String(option.departure_time ?? "?")} · Arrive: {String(option.arrival_time ?? "?")}
            </div>
          ) : null}
        </div>
      ) : null}
      {String(option.booking_url ?? "").trim() ? (
        <div className="mt-3 text-sm">
          <a
            href={String(option.booking_url)}
            target="_blank"
            rel="noreferrer"
            className="font-semibold text-coral underline-offset-2 hover:underline"
            onClick={(event) => event.stopPropagation()}
          >
            {bookingLabel}
          </a>
        </div>
      ) : null}
    </button>
  );
}

export function TimeWindowPicker({
  label,
  start,
  end,
  onChange,
}: {
  label: string;
  start: number;
  end: number;
  onChange: (nextStart: number, nextEnd: number) => void;
}) {
  const safeStart = Math.max(0, Math.min(23, start));
  const safeEnd = Math.max(safeStart, Math.min(23, end));

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-slate">{label}</span>
        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-ink">
          {formatHourLabel(safeStart)} to {formatHourLabel(safeEnd)}
        </span>
      </div>
      <div className="space-y-3 rounded-3xl border border-ink/10 bg-white px-4 py-4">
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-[0.2em] text-slate">From</div>
          <input
            type="range"
            min={0}
            max={23}
            value={safeStart}
            className="w-full accent-[#d76c4e]"
            onChange={(event) => {
              const nextStart = Number(event.target.value);
              onChange(nextStart, Math.max(nextStart, safeEnd));
            }}
          />
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-[0.2em] text-slate">To</div>
          <input
            type="range"
            min={0}
            max={23}
            value={safeEnd}
            className="w-full accent-[#10212b]"
            onChange={(event) => {
              const nextEnd = Number(event.target.value);
              onChange(Math.min(safeStart, nextEnd), nextEnd);
            }}
          />
        </div>
      </div>
    </div>
  );
}

export function FieldGroup({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-[1.75rem] border border-ink/10 bg-white/70 p-4">
      <div className="mb-4">
        <div className="text-sm font-semibold text-ink">{title}</div>
        {description ? <div className="mt-1 text-sm text-slate">{description}</div> : null}
      </div>
      {children}
    </div>
  );
}
