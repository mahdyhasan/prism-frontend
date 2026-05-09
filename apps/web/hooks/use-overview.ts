"use client";

import { useQuery } from "@tanstack/react-query";
import { overviewApi } from "@/lib/api-client";
import type { DatePreset, CompareTo } from "@/components/dashboard/date-range-picker";

export function useOverview(
  propertyId: number,
  preset: DatePreset,
  compareTo: CompareTo,
) {
  return useQuery({
    queryKey: ["overview", propertyId, preset, compareTo],
    queryFn: () =>
      overviewApi.get(propertyId, {
        preset,
        compare_to: compareTo === "none" ? undefined : compareTo,
      }),
    enabled: !!propertyId,
    staleTime: 1000 * 60 * 5,
  });
}
