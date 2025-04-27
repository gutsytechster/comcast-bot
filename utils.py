import asyncio
import logging
from typing import Callable, TypeVar, Any, Union, Optional
from functools import wraps
import aiohttp

# Configure logging
logger = logging.getLogger(__name__)

T = TypeVar('T')
ResponseType = Union[T, aiohttp.ClientResponse]

def with_retry(max_retries: int = 3, delay: float = 1.0):
    """Decorator to retry async functions on failure.

    Args:
        max_retries (int): Maximum number of retry attempts. Defaults to 3.
        delay (float): Delay between retries in seconds. Defaults to 1.0.

    Returns:
        Callable: Decorated function with retry capability.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Optional[ResponseType]:
            for attempt in range(max_retries):
                try:
                    result = await func(*args, **kwargs)

                    # Check if result is an aiohttp.ClientResponse
                    if isinstance(result, aiohttp.ClientResponse):
                        if result.status != 200:
                            raise Exception(f"HTTP {result.status}: {await result.text()}")
                        return result

                    return result
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"All {max_retries} attempts failed: {str(e)}")
                        return None
            return None
        return wrapper
    return decorator