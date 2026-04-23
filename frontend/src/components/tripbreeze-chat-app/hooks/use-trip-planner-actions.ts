import { useTripPlannerReviewActions } from "./use-trip-planner-review-actions";
import { useTripPlannerUtilityActions } from "./use-trip-planner-utility-actions";
import type { UseTripPlannerActionParams } from "./use-trip-planner-action-types";

export function useTripPlannerActions(params: UseTripPlannerActionParams) {
  const {
    handlePlanTrip,
    handleClarification,
    handleReview,
  } = useTripPlannerReviewActions(params);

  const {
    handleVoiceInput,
    handleDownloadPdf,
    handleEmailItinerary,
  } = useTripPlannerUtilityActions(params);

  return {
    handlePlanTrip,
    handleClarification,
    handleReview,
    handleVoiceInput,
    handleDownloadPdf,
    handleEmailItinerary,
  };
}
