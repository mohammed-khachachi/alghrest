/**
 * ALGHREST Client SDK — Error Classes
 */

export class AlghrestError extends Error {
  public readonly statusCode?: number;
  public readonly responseBody?: unknown;

  constructor(message: string, statusCode?: number, responseBody?: unknown) {
    super(message);
    this.name = "AlghrestError";
    this.statusCode = statusCode;
    this.responseBody = responseBody;

    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class AlghrestAuthError extends AlghrestError {
  constructor(message = "Unauthorized: Invalid or missing API access token", responseBody?: unknown) {
    super(message, 401, responseBody);
    this.name = "AlghrestAuthError";
  }
}

export class AlghrestNotFoundError extends AlghrestError {
  constructor(message = "Resource not found", responseBody?: unknown) {
    super(message, 404, responseBody);
    this.name = "AlghrestNotFoundError";
  }
}

export class AlghrestValidationError extends AlghrestError {
  constructor(message = "Validation failed", responseBody?: unknown) {
    super(message, 422, responseBody);
    this.name = "AlghrestValidationError";
  }
}

export class AlghrestTimeoutError extends AlghrestError {
  constructor(message = "Request timed out") {
    super(message, 408);
    this.name = "AlghrestTimeoutError";
  }
}

export class AlghrestNetworkError extends AlghrestError {
  constructor(message = "Network connection error") {
    super(message);
    this.name = "AlghrestNetworkError";
  }
}
