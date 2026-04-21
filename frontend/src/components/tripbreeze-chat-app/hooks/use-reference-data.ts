import { useEffect, useState } from "react";

import { getReferenceValues } from "@/lib/api";

export function useReferenceData() {
  const [cities, setCities] = useState<string[]>([]);
  const [countries, setCountries] = useState<string[]>([]);
  const [airlines, setAirlines] = useState<string[]>([]);

  useEffect(() => {
    void Promise.all([
      getReferenceValues("cities"),
      getReferenceValues("countries"),
      getReferenceValues("airlines"),
    ])
      .then(([cityValues, countryValues, airlineValues]) => {
        setCities(cityValues);
        setCountries(countryValues);
        setAirlines(airlineValues);
      })
      .catch(() => {
        // Keep the UI usable even if reference data is unavailable.
      });
  }, []);

  return { cities, countries, airlines };
}
