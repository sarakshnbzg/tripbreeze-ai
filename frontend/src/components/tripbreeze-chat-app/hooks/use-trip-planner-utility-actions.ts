import type { Dispatch, SetStateAction } from "react";

import {
  downloadItineraryPdf,
  emailItinerary,
  transcribeAudio,
} from "@/lib/api";

import {
  buildItineraryFileName,
  safeErrorMessage,
} from "../helpers";
import type { UseTripPlannerActionParams } from "./use-trip-planner-action-types";

export function useTripPlannerUtilityActions({
  authenticatedUser,
  state,
  itinerary,
  emailAddress,
  mediaRecorderRef,
  recordedChunksRef,
  setForm,
  setPlanningUpdates,
  setLoading,
  setError,
}: UseTripPlannerActionParams) {
  async function handleVoiceInput(recording: boolean, setRecording: Dispatch<SetStateAction<boolean>>) {
    if (recording) {
      mediaRecorderRef.current?.stop();
      setRecording(false);
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Voice recording is not supported in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      recordedChunksRef.current = [];
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          recordedChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        setLoading("voice");
        try {
          const blob = new Blob(recordedChunksRef.current, { type: "audio/webm" });
          const text = await transcribeAudio(blob);
          setForm((current) => ({
            ...current,
            freeText: [current.freeText, text].filter(Boolean).join(" ").trim(),
          }));
        } catch (voiceError) {
          setError(safeErrorMessage(voiceError));
        } finally {
          stream.getTracks().forEach((track) => track.stop());
          setLoading(null);
        }
      };

      recorder.start();
      setRecording(true);
      setError("");
    } catch {
      setError("Unable to start microphone recording.");
    }
  }

  async function handleDownloadPdf() {
    const finalItinerary = itinerary || String(state?.final_itinerary ?? "");
    if (!finalItinerary) {
      return;
    }
    setError("");
    setLoading("pdf");
    try {
      const fileName = buildItineraryFileName(state);
      const blob = await downloadItineraryPdf(
        finalItinerary,
        (state ?? {}) as Record<string, unknown>,
        fileName,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      link.click();
      URL.revokeObjectURL(url);
    } catch (pdfError) {
      setError(safeErrorMessage(pdfError));
    } finally {
      setLoading(null);
    }
  }

  async function handleEmailItinerary() {
    const finalItinerary = itinerary || String(state?.final_itinerary ?? "");
    if (!finalItinerary || !emailAddress.trim()) {
      setError("Enter an email address before sending the itinerary.");
      return;
    }
    setError("");
    setLoading("email");
    try {
      const result = await emailItinerary(
        emailAddress.trim(),
        authenticatedUser,
        finalItinerary,
        (state ?? {}) as Record<string, unknown>,
      );
      setPlanningUpdates((current) => [...current, result.message]);
    } catch (emailError) {
      setError(safeErrorMessage(emailError));
    } finally {
      setLoading(null);
    }
  }

  return {
    handleVoiceInput,
    handleDownloadPdf,
    handleEmailItinerary,
  };
}
