export declare class AislClientError extends Error {
}
export declare class AislTransportError extends AislClientError {
}
export declare class AislContractError extends AislClientError {
}
export declare class AislApiError extends AislClientError {
    readonly statusCode: number;
    readonly method: string;
    readonly path: string;
    readonly detail: unknown;
    constructor(statusCode: number, method: string, path: string, detail: unknown);
}
