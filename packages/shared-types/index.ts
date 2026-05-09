/**
 * PRISM shared TypeScript types.
 *
 * This file is auto-generated from the OpenAPI schema.
 * Run `pnpm --filter @prism/shared-types generate` to regenerate.
 *
 * Phase 0: placeholder types only. Real types generated after Phase 1 API is built.
 */

export interface HealthResponse {
  status: string;
  timestamp: string;
  version: string;
}

export interface ApiError {
  error: string;
}
