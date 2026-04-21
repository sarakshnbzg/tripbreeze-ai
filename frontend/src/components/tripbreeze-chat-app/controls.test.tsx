import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReviewOptionCard } from "./controls";

describe("ReviewOptionCard", () => {
  it("shows hotel stars prominently on hotel cards", () => {
    render(
      <ReviewOptionCard
        option={{
          name: "Grand Vienna",
          hotel_class: 4,
          rating: 8.9,
          address: "Innere Stadt",
          price_per_night: 220,
          total_price: 440,
        }}
        title="Hotel 1"
        variant="hotel"
        allOptions={[]}
        selected={false}
        onSelect={vi.fn()}
        currencyCode="EUR"
      />,
    );

    expect(screen.getByText("★★★★ 4-star hotel")).toBeInTheDocument();
  });
});
