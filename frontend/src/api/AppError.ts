/**
 * The one error type every API client caller deals with -- HTTP failures,
 * ApiResponse.error envelopes, and network/parse failures all normalize
 * into this, so feature code never inspects a raw Response or a raw fetch
 * exception.
 */
export class AppError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly httpStatus: number,
    readonly requestId: string,
    readonly cause?: unknown,
  ) {
    super(message);
    this.name = "AppError";
  }

  get isUnauthorized(): boolean {
    return this.httpStatus === 401;
  }

  get isForbidden(): boolean {
    return this.httpStatus === 403;
  }

  get isNotFound(): boolean {
    return this.httpStatus === 404;
  }
}
