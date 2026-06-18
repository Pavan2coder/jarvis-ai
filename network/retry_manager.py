import random
import time
import functools
from typing import Callable, Any, Type, Union, Tuple, Optional
import requests
from backend.utils.logger import logger

# ==========================================
# Error Categorization (Exceptions)
# ==========================================

class APIException(Exception):
    """Base exception for all external API calls."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        super().__init__(message)
        self.original_exception = original_exception


class FatalAPIError(APIException):
    """Exception for non-retriable, fatal errors (e.g., bad request formats, 404)."""
    pass


class AuthAPIError(FatalAPIError):
    """Exception for authentication or API key failures (401, 403)."""
    pass


class TransientAPIError(APIException):
    """Exception for retriable, transient errors (e.g., timeouts, 5xx server errors)."""
    pass


class TimeoutAPIError(TransientAPIError):
    """Exception for connection or read timeout errors."""
    pass


class ConnectionAPIError(TransientAPIError):
    """Exception for network connection drops or resets."""
    pass


class QuotaAPIError(TransientAPIError):
    """Exception for quota limits and rate-limiting (429).
    
    Can represent a transient rate limit (retriable) or a hard quota exhaustion (can be marked fatal).
    """
    def __init__(self, message: str, original_exception: Optional[Exception] = None, is_hard_limit: bool = False):
        super().__init__(message, original_exception)
        self.is_hard_limit = is_hard_limit


# ==========================================
# Retry Configuration
# ==========================================

class RetryConfig:
    """Configuration class for controlling retry behavior."""
    def __init__(
        self,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        max_backoff: float = 10.0,
        backoff_factor: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_factor = backoff_factor
        self.jitter = jitter

    def __repr__(self) -> str:
        return (f"RetryConfig(max_retries={self.max_retries}, "
                f"initial_backoff={self.initial_backoff}s, "
                f"max_backoff={self.max_backoff}s, "
                f"backoff_factor={self.backoff_factor}, "
                f"jitter={self.jitter})")


# ==========================================
# Helper Exception Categorizer
# ==========================================

def categorize_exception(exc: Exception) -> APIException:
    """Categorizes generic network and HTTP exceptions into specific APIException classes.
    
    Handles requests exceptions and translates HTTP status codes appropriately.
    """
    if isinstance(exc, APIException):
        return exc

    # Handle Requests HTTP status errors
    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        if response is not None:
            status = response.status_code
            body_text = response.text or ""
            
            if status in (401, 403):
                return AuthAPIError(f"Authentication failed (HTTP {status}): {body_text[:200]}", exc)
            
            if status == 429:
                # Check if it's a hard limit vs a rate limit
                # e.g., "quota exhausted", "limit exceeded", "RESOURCE_EXHAUSTED"
                is_hard = any(word in body_text.upper() for word in ["QUOTA", "EXHAUSTED", "LIMIT_EXCEEDED"])
                msg = f"Rate limit / Quota exceeded (HTTP 429): {body_text[:200]}"
                return QuotaAPIError(msg, exc, is_hard_limit=is_hard)
            
            if status in (500, 502, 503, 504):
                return TransientAPIError(f"Transient server error (HTTP {status}): {body_text[:200]}", exc)
            
            if 400 <= status < 500:
                return FatalAPIError(f"Client error (HTTP {status}): {body_text[:200]}", exc)
                
        return FatalAPIError(f"HTTP error occurred: {str(exc)}", exc)

    # Handle connection & timeouts
    if isinstance(exc, requests.exceptions.Timeout):
        return TimeoutAPIError(f"Request timed out: {str(exc)}", exc)
    
    if isinstance(exc, requests.exceptions.ConnectionError):
        return ConnectionAPIError(f"Connection failed: {str(exc)}", exc)

    if isinstance(exc, requests.exceptions.RequestException):
        return TransientAPIError(f"Network request failed: {str(exc)}", exc)

    # Fallback for general exceptions
    return FatalAPIError(f"An unexpected error occurred: {str(exc)}", exc)


# ==========================================
# Retry Manager Implementation
# ==========================================

class RetryManager:
    """Manages the execution of retriable blocks with exponential backoff and jitter."""
    
    @staticmethod
    def calculate_backoff(attempt: int, config: RetryConfig) -> float:
        """Calculates backoff duration using exponential backoff.
        
        If jitter is enabled, applies Full Jitter:
        sleep = random(0, min(max_backoff, initial_backoff * (backoff_factor ** attempt)))
        """
        if attempt < 0:
            return 0.0
            
        temp = config.initial_backoff * (config.backoff_factor ** attempt)
        upper_limit = min(config.max_backoff, temp)
        
        if config.jitter:
            return random.uniform(0, upper_limit)
        return upper_limit

    @classmethod
    def execute(
        cls,
        func: Callable[..., Any],
        *args: Any,
        retry_config: Optional[RetryConfig] = None,
        **kwargs: Any
    ) -> Any:
        """Executes a callable with retries based on the provided configuration.
        
        Categorizes exceptions and retries only on TransientAPIError (or non-hard QuotaAPIError).
        Fails fast on AuthAPIError or hard QuotaAPIError.
        """
        config = retry_config or RetryConfig()
        attempt = 0

        while True:
            try:
                return func(*args, **kwargs)
            except Exception as raw_exc:
                categorized = categorize_exception(raw_exc)
                
                # Check retriability
                is_retriable = False
                if isinstance(categorized, TransientAPIError):
                    # For QuotaAPIError, check if it's a hard limit
                    if isinstance(categorized, QuotaAPIError) and categorized.is_hard_limit:
                        is_retriable = False
                        logger.error(f"Hard quota limit hit. Skipping retries. Details: {categorized}")
                    else:
                        is_retriable = True
                
                if not is_retriable or attempt >= config.max_retries:
                    if not is_retriable:
                        logger.warning(f"Non-retriable error encountered: {categorized}")
                    else:
                        logger.error(f"Max retries ({config.max_retries}) reached. Raising error: {categorized}")
                    raise categorized

                # Calculate and execute backoff sleep
                sleep_time = cls.calculate_backoff(attempt, config)
                logger.warning(
                    f"Transient API failure: {categorized}. "
                    f"Retrying (attempt {attempt + 1}/{config.max_retries}) in {sleep_time:.2f}s..."
                )
                time.sleep(sleep_time)
                attempt += 1


def with_retry(retry_config: Optional[RetryConfig] = None) -> Callable:
    """Decorator to apply retry logic to standard Python functions."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return RetryManager.execute(func, *args, retry_config=retry_config, **kwargs)
        return wrapper
    return decorator
