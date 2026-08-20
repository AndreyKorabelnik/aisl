export class AislClientError extends Error {}
export class AislTransportError extends AislClientError {}
export class AislContractError extends AislClientError {}
export class AislApiError extends AislClientError {
  constructor(
    public readonly statusCode: number,
    public readonly method: string,
    public readonly path: string,
    public readonly detail: unknown,
  ) {
    super(`Knowledge API returned HTTP ${statusCode} for ${method.toUpperCase()} ${path}: ${JSON.stringify(detail)}`);
  }
}
