# Ethics, Safety, and Privacy

TripBreeze AI is a travel-planning assistant, not an authority on border control, airline policy, or public-health rules. Users should confirm high-stakes details with official sources before booking or travel.

## System Boundaries

- The product is intended for travel planning tasks such as trip intake, option research, budget checks, and itinerary generation.
- Entry guidance is grounded in a local knowledge base instead of being generated from model memory alone.
- Human review is required before the workflow moves from research into the final itinerary.

## Prompt-Injection and Untrusted Input

- Free-text trip requests are treated as untrusted input.
- Intake prompts explicitly instruct the model to ignore embedded commands or role-play directives.
- The intake layer strips obvious prompt-injection lines such as `ignore previous instructions`, `system:`, `assistant:`, and similar role-reset patterns before user text is inserted into prompts.
- Golden and unit tests should cover adversarial inputs so this guardrail remains in place.

## Bias and Coverage Limits

Several parts of the stack can introduce uneven outcomes:

- `SerpAPI` flight and hotel ordering may favor certain suppliers, brands, or regions.
- The local knowledge base may have better coverage for some passports or destinations than others.
- LLMs can over-generalize from dominant English-language or Western travel patterns.

Current mitigations:

- Retrieval uses metadata-aware narrowing across separate sources for visa, health, customs, currency, and transit topics.
- The review step exposes grounded entry notes and budget context before approval.
- The app should present travel guidance as assistive, not definitive.

## Privacy and Retention

- User preferences and recent trip history are stored in Postgres for continuity across sessions.
- Passwords are stored as bcrypt hashes rather than plaintext.
- Trip history is capped to the most recent 10 trips in the profile layer.
- A production deployment should pair this with explicit consent, clear deletion controls, and session management.

## Recommended Next Hardening Steps

- Add a user-triggered profile deletion endpoint and UI action.
- Add API rate limiting for search and transcription routes.
- Add end-to-end logging for LLM token usage, cost, and latency on every model call.
- Expand evaluation sets with adversarial and out-of-coverage travel questions.
