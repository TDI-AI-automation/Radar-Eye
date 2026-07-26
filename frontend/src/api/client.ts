import { AppError } from "./AppError";
import type { ApiEnvelope } from "./types";

/**
 * ApiClient -- the ONLY module permitted to call fetch(). Every feature
 * module goes through src/api/endpoints/*.ts, which goes through this.
 *
 * Owns: auth header injection, request correlation IDs, per-request
 * timeout, caller-supplied cancellation, retry (idempotent GET only),
 * error/response normalization, and inactive-but-present hooks for
 * metrics/tracing/telemetry (item 4 -- extension points, not implementations).
 *
 * Deliberately has zero import-time dependency on auth/ -- `getAuthToken`
 * and `onUnauthorized` are injected via ApiClientConfig so this file and
 * Phase 1's AuthProvider can be built/tested independently, and so this
 * file compiles and is unit-testable today even though AuthProvider
 * doesn't exist yet.
 */

export interface RequestMeta {
  requestId: string;
  method: string;
  path: string;
}

export interface ApiClientHooks {
  /** Fired before every attempt (including retries). No-op today -- the
   * seam for metrics/tracing/telemetry mentioned in the architecture
   * review; wire a real implementation here later without touching
   * request()'s call sites. */
  onRequestStart?: (meta: RequestMeta) => void;
  onRequestEnd?: (meta: RequestMeta, outcome: "success" | "error") => void;
}

export interface ApiClientConfig {
  baseUrl: string;
  getAuthToken: () => string | null;
  /** Invoked when a request that DID carry a token comes back 401 (i.e.
   * the token was rejected, not merely absent) -- Phase 1's AuthProvider
   * wires this to its refresh-then-retry / force-logout flow. */
  onUnauthorized: () => void;
  hooks?: ApiClientHooks;
  defaultTimeoutMs?: number;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  /** Caller-supplied cancellation -- pass TanStack Query's queryFn
   * `{ signal }` straight through. This file never invents its own
   * cancellation mechanism on top of the caller's. */
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Only meaningful for GET. Mutations (POST/PATCH/DELETE) never
   * auto-retry -- they are not safe to replay blindly. */
  retry?: boolean;
}

const DEFAULT_TIMEOUT_MS = 10_000;
const MAX_GET_ATTEMPTS = 3;

export class ApiClient {
  constructor(private readonly config: ApiClientConfig) {}

  async request<T>(path: string, options: RequestOptions = {}): Promise<T | null> {
    const method = options.method ?? "GET";
    const requestId = crypto.randomUUID();
    const meta: RequestMeta = { requestId, method, path };
    const timeoutMs = options.timeoutMs ?? this.config.defaultTimeoutMs ?? DEFAULT_TIMEOUT_MS;
    const maxAttempts = options.retry && method === "GET" ? MAX_GET_ATTEMPTS : 1;

    this.config.hooks?.onRequestStart?.(meta);

    let lastError: unknown;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const timeoutController = new AbortController();
      const timeoutId = setTimeout(() => timeoutController.abort(), timeoutMs);
      const signal = combineSignals(options.signal, timeoutController.signal);

      try {
        const response = await fetch(`${this.config.baseUrl}${path}`, {
          method,
          signal,
          headers: this.buildHeaders(requestId),
          body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
        });

        const data = await this.parseEnvelope<T>(response, requestId);
        this.config.hooks?.onRequestEnd?.(meta, "success");
        return data;
      } catch (err) {
        lastError = err;

        if (err instanceof AppError && err.isUnauthorized) {
          this.config.onUnauthorized();
          break; // never retry an auth failure
        }
        if (attempt < maxAttempts) continue;
      } finally {
        clearTimeout(timeoutId);
      }
    }

    this.config.hooks?.onRequestEnd?.(meta, "error");
    throw lastError;
  }

  /**
   * For the download endpoints (GET /recordings/{id}/download,
   * GET /snapshots/{id}/download) -- these return the raw file, not an
   * ApiResponse envelope, so they need a different unwrap path than
   * request(). Auth/correlation-id/timeout handling is identical.
   */
  async requestBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
    const requestId = crypto.randomUUID();
    const timeoutMs = options.timeoutMs ?? this.config.defaultTimeoutMs ?? DEFAULT_TIMEOUT_MS;
    const timeoutController = new AbortController();
    const timeoutId = setTimeout(() => timeoutController.abort(), timeoutMs);
    const signal = combineSignals(options.signal, timeoutController.signal);

    try {
      const response = await fetch(`${this.config.baseUrl}${path}`, {
        method: "GET",
        signal,
        headers: this.buildHeaders(requestId),
      });
      if (!response.ok) {
        if (response.status === 401) this.config.onUnauthorized();
        throw new AppError(
          "download_failed",
          `Download failed (${response.status})`,
          response.status,
          requestId,
        );
      }
      return await response.blob();
    } finally {
      clearTimeout(timeoutId);
    }
  }

  private buildHeaders(requestId: string): HeadersInit {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Request-Id": requestId,
    };
    const token = this.config.getAuthToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
  }

  private async parseEnvelope<T>(response: Response, requestId: string): Promise<T | null> {
    let envelope: ApiEnvelope<T>;
    try {
      envelope = (await response.json()) as ApiEnvelope<T>;
    } catch (cause) {
      throw new AppError(
        "network_error",
        `Request failed (${response.status})`,
        response.status,
        requestId,
        cause,
      );
    }

    if (!response.ok || !envelope.success) {
      throw new AppError(
        envelope.error?.code ?? "unknown_error",
        envelope.error?.message ?? `Request failed (${response.status})`,
        response.status,
        requestId,
      );
    }

    return envelope.data;
  }
}

function combineSignals(a: AbortSignal | undefined, b: AbortSignal): AbortSignal {
  if (!a) return b;
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (a.aborted || b.aborted) {
    controller.abort();
  } else {
    a.addEventListener("abort", abort, { once: true });
    b.addEventListener("abort", abort, { once: true });
  }
  return controller.signal;
}
