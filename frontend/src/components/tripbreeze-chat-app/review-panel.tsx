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
      <div className="animate-fade-up">
        <DestinationBriefingPanel destinationInfo={state.destination_info} />
      </div>

      <div className="animate-fade-up stagger-1 rounded-[1.9rem] border border-pine/12 bg-gradient-to-b from-paper via-white to-[#f7f2ea] p-5 shadow-[0_24px_56px_rgba(16,33,43,0.10)]">
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
