from fastapi import HTTPException


class SentinelPayException(HTTPException):
    """Base exception for all SentinelPay domain errors."""

    def __init__(self, status_code: int, code: str, message: str, details: dict = None):
        """Initialise with a structured error envelope."""
        super().__init__(
            status_code=status_code,
            detail={"error": {"code": code, "message": message, "details": details or {}}},
        )


class EmailAlreadyRegistered(SentinelPayException):
    """Raised when a registration attempt uses an already-registered email."""

    def __init__(self):
        super().__init__(400, "EMAIL_ALREADY_REGISTERED", "This email address is already registered.")


class MerchantIdAlreadyTaken(SentinelPayException):
    """Raised when the requested merchant_id is not available."""

    def __init__(self):
        super().__init__(400, "MERCHANT_ID_ALREADY_TAKEN", "This merchant ID is already taken.")


class InvalidCredentials(SentinelPayException):
    """Raised on failed login attempts."""

    def __init__(self):
        super().__init__(401, "INVALID_CREDENTIALS", "Incorrect email or password.")


class AccountInactive(SentinelPayException):
    """Raised when a disabled account attempts to log in."""

    def __init__(self):
        super().__init__(401, "ACCOUNT_INACTIVE", "This account has been deactivated.")


class InvalidToken(SentinelPayException):
    """Raised when a JWT cannot be decoded or is missing."""

    def __init__(self):
        super().__init__(401, "INVALID_TOKEN", "Authentication token is invalid or missing.")


class TokenExpired(SentinelPayException):
    """Raised when a JWT has passed its expiry time."""

    def __init__(self):
        super().__init__(401, "TOKEN_EXPIRED", "Authentication token has expired.")


class InvalidRefreshToken(SentinelPayException):
    """Raised when a refresh token is invalid."""

    def __init__(self):
        super().__init__(401, "INVALID_REFRESH_TOKEN", "Refresh token is invalid.")


class RefreshTokenExpired(SentinelPayException):
    """Raised when a refresh token has expired."""

    def __init__(self):
        super().__init__(401, "REFRESH_TOKEN_EXPIRED", "Refresh token has expired.")


class Forbidden(SentinelPayException):
    """Raised when a user lacks the required role or ownership."""

    def __init__(self, message: str = "You do not have permission to perform this action."):
        super().__init__(403, "FORBIDDEN", message)


class TransactionNotFound(SentinelPayException):
    """Raised when a transaction UUID does not exist."""

    def __init__(self):
        super().__init__(404, "TRANSACTION_NOT_FOUND", "Transaction not found.")


class DecisionNotFound(SentinelPayException):
    """Raised when a fraud decision record is missing for a transaction."""

    def __init__(self):
        super().__init__(404, "DECISION_NOT_FOUND", "Fraud decision not found for this transaction.")


class RuleNotFound(SentinelPayException):
    """Raised when a rule UUID does not exist."""

    def __init__(self):
        super().__init__(404, "RULE_NOT_FOUND", "Rule not found.")


class UserNotFound(SentinelPayException):
    """Raised when a user UUID does not exist."""

    def __init__(self):
        super().__init__(404, "USER_NOT_FOUND", "User not found.")


class DuplicateTransaction(SentinelPayException):
    """Raised when a transaction with the same external_transaction_id is submitted twice."""

    def __init__(self):
        super().__init__(409, "DUPLICATE_TRANSACTION", "A transaction with this ID has already been analyzed.")


class RuleNameAlreadyExists(SentinelPayException):
    """Raised when a rule name is not unique."""

    def __init__(self):
        super().__init__(400, "RULE_NAME_ALREADY_EXISTS", "A rule with this name already exists.")


class CannotDemoteSelf(SentinelPayException):
    """Raised when an admin tries to remove their own admin role."""

    def __init__(self):
        super().__init__(400, "CANNOT_DEMOTE_SELF", "You cannot remove your own admin role.")


class AIScorerUnavailable(SentinelPayException):
    """Raised (and caught) when the Anthropic API is unreachable."""

    def __init__(self):
        super().__init__(503, "AI_SCORER_UNAVAILABLE", "AI scoring service is temporarily unavailable. A fallback decision was applied.")
