import type { components } from "@gtm-state/contracts";

export type ApiLiveness = components["schemas"]["LivenessResponse"];
export type ApiReadiness = components["schemas"]["ReadinessResponse"];

export const API_SERVICE_NAME: ApiLiveness["service"] = "gtm-state-api";
