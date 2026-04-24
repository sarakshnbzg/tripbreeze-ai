"use client";

import type { Dispatch, SetStateAction } from "react";

import { LoaderCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { renderMarkdownContent, type ChatMessage } from "@/components/tripbreeze-chat-app/helpers";
import type { PlannerLoadingState } from "@/components/tripbreeze-chat-app/ui-types";

export function MessageFeed({ messages }: { messages: ChatMessage[] }) {
  if (!messages.length) {
    return null;
  }

  return (
    <div className="space-y-3">
      {messages.map((message, index) => (
        <div
          key={`${message.role}-${index}`}
          className={`max-w-4xl rounded-[1.75rem] px-5 py-4 text-sm leading-7 shadow-sm ${
            message.role === "user"
              ? "ml-auto bg-pine text-white shadow-[0_16px_36px_rgba(24,77,71,0.20)]"
              : "border border-line/70 bg-paper/90 text-ink"
          }`}
        >
          <div
            className={`mb-2 text-[11px] font-semibold uppercase tracking-[0.22em] ${
              message.role === "user" ? "text-white/60" : "text-slate"
            }`}
          >
            {message.role === "user" ? "You" : "TripBreeze"}
          </div>
          {message.role === "assistant" ? renderMarkdownContent(message.content) : message.content}
        </div>
      ))}
    </div>
  );
}

export function TranscriptPanel({ title, messages }: { title: string; messages: ChatMessage[] }) {
  if (!messages.length) {
    return null;
  }

  return (
    <div className="rounded-[1.75rem] border border-line/70 bg-paper/88 px-5 py-4 text-sm leading-7 text-ink shadow-sm">
      <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate">{title}</div>
      <div className="space-y-3">
        {messages.map((message, index) => (
          <div
            key={`${message.role}-transcript-${index}`}
            className={`max-w-4xl rounded-[1.4rem] px-4 py-3 text-sm leading-7 ${
              message.role === "user" ? "ml-auto bg-pine text-white" : "border border-line/60 bg-white text-ink"
            }`}
          >
            <div
              className={`mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${
                message.role === "user" ? "text-white/60" : "text-slate"
              }`}
            >
              {message.role === "user" ? "You" : "TripBreeze"}
            </div>
            {message.role === "assistant" ? renderMarkdownContent(message.content) : message.content}
          </div>
        ))}
      </div>
    </div>
  );
}

export function PlanningProgressPanel({
  recentPlanningUpdates,
  showPlanningProgress,
  setShowPlanningProgress,
  loading,
  compact = false,
}: {
  recentPlanningUpdates: string[];
  showPlanningProgress: boolean;
  setShowPlanningProgress: Dispatch<SetStateAction<boolean>>;
  loading: PlannerLoadingState;
  compact?: boolean;
}) {
  if (!recentPlanningUpdates.length) {
    return null;
  }

  if (compact) {
    return (
      <div className="rounded-[1.6rem] border border-line/70 bg-paper/82 p-4 lg:hidden">
        <button
          type="button"
          onClick={() => setShowPlanningProgress((current) => !current)}
          className="flex w-full items-center justify-between gap-3 text-left"
        >
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-ink">
              <LoaderCircle className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              Planning progress
            </div>
            <div className="mt-1 text-xs text-slate">Latest workflow milestones from the planner.</div>
          </div>
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate">
            {showPlanningProgress ? "Hide" : "Show"}
          </span>
        </button>
        {showPlanningProgress ? (
          <div className="mt-4 space-y-2">
            {recentPlanningUpdates.map((update, index) => (
              <div
                key={`mobile-${update}-${index}`}
                className="rounded-[1.1rem] border border-line/60 bg-white/85 px-3 py-2 text-sm text-slate"
              >
                {update}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="rounded-[1.75rem] border border-line/70 bg-gradient-to-r from-paper/95 via-mist/90 to-white/88 p-5">
      <button
        type="button"
        onClick={() => setShowPlanningProgress((current) => !current)}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <div className="flex items-center gap-2 text-sm font-semibold text-ink">
          <LoaderCircle className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Planning progress
        </div>
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">
          {showPlanningProgress ? "Hide" : "Show"}
        </span>
      </button>
      {showPlanningProgress ? (
        <div className="mt-3 space-y-2 text-sm text-slate">
          {recentPlanningUpdates.map((update, index) => (
            <div key={`${update}-${index}`} className="rounded-[1.1rem] border border-line/60 bg-white/85 px-3 py-2">
              {update}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ClarificationPanel({
  clarificationQuestion,
  clarificationAnswer,
  setClarificationAnswer,
  handleClarification,
  loading,
}: {
  clarificationQuestion: string;
  clarificationAnswer: string;
  setClarificationAnswer: Dispatch<SetStateAction<string>>;
  handleClarification: () => Promise<void>;
  loading: PlannerLoadingState;
}) {
  if (!clarificationQuestion) {
    return null;
  }

  return (
    <div className="mt-6 rounded-[1.75rem] border border-pine/12 bg-[linear-gradient(180deg,rgba(243,248,245,0.96),rgba(255,250,244,0.96))] p-5 shadow-sm">
      <div className="text-sm font-semibold text-ink">One quick detail</div>
      <div className="mt-2 text-sm text-slate">This helps me keep the trip accurate before I continue.</div>
      <textarea
        className="mt-3 h-24 w-full rounded-3xl border border-line/70 bg-white/92 px-4 py-3 text-sm outline-none transition focus:border-pine"
        value={clarificationAnswer}
        onChange={(event) => setClarificationAnswer(event.target.value)}
        placeholder="Type your answer here..."
      />
      <div className="mt-4">
        <Button onClick={() => void handleClarification()} disabled={loading !== null || !clarificationAnswer.trim()}>
          {loading === "clarifying" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
          Continue Planning
        </Button>
      </div>
    </div>
  );
}
