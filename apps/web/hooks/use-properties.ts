"use client";

import { useQuery } from "@tanstack/react-query";
import { propertiesApi, propertiesApiExt, type PropertyResponse } from "@/lib/api-client";

const FIVE_MINUTES = 1000 * 60 * 5;

export function useProperties() {
  return useQuery<PropertyResponse[]>({
    queryKey: ["properties"],
    queryFn: () => propertiesApi.list(),
    staleTime: FIVE_MINUTES,
  });
}

export function useProperty(propertyId: number | null | undefined) {
  return useQuery<PropertyResponse>({
    queryKey: ["property", propertyId],
    queryFn: () => propertiesApiExt.get(propertyId as number),
    enabled: typeof propertyId === "number" && Number.isFinite(propertyId),
    staleTime: FIVE_MINUTES,
  });
}
