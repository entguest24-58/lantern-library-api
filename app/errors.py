class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def bad_request(message: str) -> ApiError:
    return ApiError(400, message)


def unauthorized(message: str = "authentication required") -> ApiError:
    return ApiError(401, message)


def forbidden(message: str = "staff only") -> ApiError:
    return ApiError(403, message)


def not_found(message: str) -> ApiError:
    return ApiError(404, message)


def conflict(message: str) -> ApiError:
    return ApiError(409, message)
