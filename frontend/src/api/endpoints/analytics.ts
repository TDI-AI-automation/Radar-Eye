import { apiClient } from "../instance";
import type { components } from "../generated/schema";

type ThreatAnalyticsDto = components["schemas"]["ThreatAnalyticsSchema"];
type IncidentAnalyticsDto = components["schemas"]["IncidentAnalyticsSchema"];
type CameraAnalyticsDto = components["schemas"]["CameraAnalyticsSchema"];
type SystemAnalyticsDto = components["schemas"]["SystemAnalyticsSchema"];

/**
 * shared/schemas/analytics.py: "straightforward repository-query
 * aggregations over existing tables, not a new analytics computation
 * engine (explicitly out of scope for RM-12)." These four endpoints are
 * genuinely this coarse -- counts and totals, no time-windowed trends, no
 * precision/recall/response-time metrics, no heatmaps. See
 * docs/FRONTEND_ARCHITECTURE.md's Phase 2 checkpoint for what the
 * prototype's Analytics screen assumed that isn't backed by any endpoint.
 */
export function getThreatAnalytics(): Promise<ThreatAnalyticsDto | null> {
  return apiClient.request<ThreatAnalyticsDto>("/analytics/threats");
}

export function getIncidentAnalytics(): Promise<IncidentAnalyticsDto | null> {
  return apiClient.request<IncidentAnalyticsDto>("/analytics/incidents");
}

export function getCameraAnalytics(): Promise<CameraAnalyticsDto | null> {
  return apiClient.request<CameraAnalyticsDto>("/analytics/cameras");
}

export function getSystemAnalytics(): Promise<SystemAnalyticsDto | null> {
  return apiClient.request<SystemAnalyticsDto>("/analytics/system");
}
