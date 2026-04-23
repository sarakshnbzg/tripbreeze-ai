import type { ReviewPanelProps } from "./workspace-types";

import {
  DestinationBriefingPanel,
  EmptyOptionsPanel,
  PersonalisationPanel,
  PartialResultsPanel,
  ReviewActionsPanel,
  ReviewWorkspaceHeader,
} from "./review-panel-sections";
import {
  MultiCitySelectionPanel,
  SingleTripSelectionPanel,
} from "./review-selection-panels";

export function ReviewPanel({
  model,
  actions,
  refs,
}: ReviewPanelProps) {
  const { hasReviewWorkspace, finalItinerary, state, hasOptionResults, currencyCode, selection } = model;

  if (!hasReviewWorkspace || finalItinerary || !state) {
    return null;
  }

  return (
    <>
      <DestinationBriefingPanel destinationInfo={state.destination_info} />

      <div className="rounded-[1.9rem] border border-ink/10 bg-gradient-to-b from-white to-[#fbf8f3] p-5 shadow-[0_20px_50px_rgba(16,33,43,0.08)]">
        <ReviewWorkspaceHeader model={model} />
        <PartialResultsPanel note={model.partialResultsNote} />

        {hasOptionResults ? (
          state.trip_legs?.length ? (
            <MultiCitySelectionPanel
              state={state}
              currencyCode={currencyCode}
              selection={selection}
              setSelection={actions.setSelection}
            />
          ) : (
            <SingleTripSelectionPanel model={model} actions={actions} refs={refs} />
          )
        ) : (
          <EmptyOptionsPanel />
        )}

        <PersonalisationPanel
          model={model}
          actions={actions}
          personaliseSectionRef={refs.personaliseSectionRef}
        />
        <ReviewActionsPanel model={model} actions={actions} />
      </div>
    </>
  );
}
