import asyncio
import logging
from typing import Callable, TypeVar, Any, Union, Optional, Dict
from functools import wraps
import aiohttp
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

T = TypeVar('T')
ResponseType = Union[T, aiohttp.ClientResponse]

def get_proxy_config() -> Optional[Dict[str, str]]:
    """Get proxy configuration from environment variables.

    Returns:
        Optional[Dict[str, str]]: Proxy configuration for Playwright and aiohttp.
        Format: {
            'server': 'http://proxy:port',
            'username': 'proxy_username',  # Optional
            'password': 'proxy_password'   # Optional
        }
    """
    proxy_server = os.getenv('PROXY_SERVER')
    if not proxy_server:
        return None

    config = {'server': proxy_server}

    # Add authentication if provided
    proxy_username = os.getenv('PROXY_USERNAME')
    proxy_password = os.getenv('PROXY_PASSWORD')
    if proxy_username and proxy_password:
        config.update({
            'username': proxy_username,
            'password': proxy_password
        })

    return config

def get_aiohttp_proxy_url() -> Optional[str]:
    """Get proxy URL for aiohttp client.

    Returns:
        Optional[str]: Proxy URL in format http://username:password@host:port
    """
    config = get_proxy_config()
    if not config:
        return None

    if 'username' in config and 'password' in config:
        return f"http://{config['username']}:{config['password']}@{config['server'].replace('http://', '')}"
    return config['server']

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