import type { PlannerForm } from "@/lib/planner";

export function ModelSettingsPanel({
  form,
  setForm,
  availableModels,
}: {
  form: PlannerForm;
  setForm: React.Dispatch<React.SetStateAction<PlannerForm>>;
  availableModels: readonly string[];
}) {
  return (
    <div className="rounded-[1.6rem] border border-ink/10 bg-mist/55 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
        Settings
      </div>
      <div className="grid gap-3">
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-slate">Model</span>
          <select
            className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
            value={form.model}
            onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
          >
            {availableModels.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="mt-3 block">
        <div className="mb-2 flex items-center justify-between text-sm font-medium text-slate">
          <span>Temperature</span>
          <span className="font-semibold text-ink">{form.temperature.toFixed(1)}</span>
        </div>
        <input
          type="range"
          min="0"
          max="1"
          step="0.1"
          value={form.temperature}
          onChange={(event) =>
            setForm((current) => ({
              ...current,
              temperature: Number(event.target.value),
            }))
          }
          className="w-full accent-coral"
        />
        <p className="mt-2 text-xs text-slate">
          Lower values keep planning stricter and more deterministic. Higher values allow more variation.
        </p>
      </label>
    </div>
  );
}
