export class AislClientError extends Error {
}
export class AislTransportError extends AislClientError {
}
export class AislContractError extends AislClientError {
}
export class AislApiError extends AislClientError {
    statusCode;
    method;
    path;
    detail;
    constructor(statusCode, method, path, detail) {
        super(`Knowledge API returned HTTP ${statusCode} for ${method.toUpperCase()} ${path}: ${JSON.stringify(detail)}`);
        this.statusCode = statusCode;
        this.method = method;
        this.path = path;
        this.detail = detail;
    }
}
