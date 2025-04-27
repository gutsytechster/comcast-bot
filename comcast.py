import asyncio
import json
import logging
import os
from typing import Dict, List, Optional
import aiohttp
from playwright.async_api import async_playwright, Page, Browser, Response
from dotenv import load_dotenv
from utils import with_retry, get_proxy_config, get_aiohttp_proxy_url

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ComcastScraper:
    def __init__(self):
        self.intercepted_requests: List[Dict] = []
        self.navigation_headers: Optional[Dict] = None
        self.cookies: Optional[Dict] = None
        self.initial_navigation_response: Optional[str] = None
        self.navigation_response_future: Optional[asyncio.Future] = None
        self.page: Optional[Page] = None
        self.browser: Optional[Browser] = None
        self.proxy_config = get_proxy_config()

    @staticmethod
    def get_credentials() -> tuple[str, str]:
        """Get credentials from environment variables."""
        username = os.getenv('COMCAST_USERNAME')
        password = os.getenv('COMCAST_PASSWORD')

        if not username or not password:
            raise ValueError(
                "Missing credentials. Please set COMCAST_USERNAME and COMCAST_PASSWORD "
                "environment variables or create a .env file with these variables."
            )

        return username, password

    async def setup(self):
        """Initialize browser and page with proper configuration."""
        playwright = await async_playwright().start()

        # Configure browser with proxy if available
        browser_args = []
        if self.proxy_config:
            browser_args.append(f'--proxy-server={self.proxy_config["server"]}')
            if 'username' in self.proxy_config and 'password' in self.proxy_config:
                browser_args.append(f'--proxy-auth={self.proxy_config["username"]}:{self.proxy_config["password"]}')

        self.browser = await playwright.chromium.launch(
            headless=False,
            slow_mo=500,
            args=browser_args
        )
        self.page = await self.browser.new_page()

        # Set up request and response listeners
        self.page.on("request", self.log_request)
        self.page.on("response", self.log_response)

        # Create future for navigation response
        self.navigation_response_future = asyncio.Future()

    async def log_request(self, request):
        """Log and store navigation request details."""
        if request.url.endswith('/Navigation'):
            if not self.page:
                logger.error("Page not initialized")
                return

            request_data = {
                "url": request.url,
                "method": request.method,
                "headers": request.headers,
                "cookies": await self.page.context.cookies(),
                "post_data": await request.post_data() if request.method == "POST" else None,
            }
            self.intercepted_requests.append(request_data)
            logger.debug(f"Intercepted Navigation Request headers: {request_data.get('headers')}")
            self.navigation_headers = request.headers
            self.cookies = {cookie['name']: cookie['value'] for cookie in request_data['cookies']}

    async def log_response(self, response: Response):
        """Log and store navigation response details."""
        if response.url.endswith('/Navigation'):
            try:
                response_text = await response.text()
                if self.navigation_response_future and not self.navigation_response_future.done():
                    self.navigation_response_future.set_result(response_text)
                    self.initial_navigation_response = response_text
            except Exception as e:
                logger.error(f"Error reading navigation response: {str(e)}")
                if self.navigation_response_future and not self.navigation_response_future.done():
                    self.navigation_response_future.set_exception(e)

    async def login(self, username: str, password: str):
        """Handle login process with proper error handling and retries."""
        if not self.page:
            logger.error("Page not initialized")
            return

        try:
            await self.page.goto("https://business.comcast.com/account")
            try:
                reject_button = await self.page.wait_for_selector("#onetrust-reject-all-handler", timeout=2000)
                if reject_button:
                    await reject_button.click()
            except Exception:
                # Cookie consent banner not present, continue
                pass

            # Fill username and click sign in
            await self.page.fill("input[name='user']", username)
            await self.page.wait_for_timeout(2000)
            await self.page.click("#sign_in")
            await self.page.wait_for_timeout(10000)

            # Fill password and click sign in
            await self.page.fill("input[name='passwd']", password)
            await self.page.click("#sign_in")

            # Wait for navigation to complete
            await self.page.wait_for_timeout(10000)
            logger.info("Login successful")
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            raise

    async def process_account(self, account: Dict, customer_id: str):
        """Process a single account's billing information."""
        account_number = account.get('accountNumber')
        auth_guid = account.get('authGuid')

        if not account_number or not auth_guid:
            logger.warning(f"Skipping account with missing account_number or auth_guid")
            return

        if not self.page:
            logger.error("Page not initialized")
            return

        try:
            # Navigate to account dashboard
            await self.page.goto(f"https://business.comcast.com/account/dashboard/accounts/{auth_guid}")
            await self.page.wait_for_timeout(10000)
            logger.info(f"Successfully navigated to account {account_number}")

            if not self.navigation_headers:
                logger.error("No navigation headers available while processing account")
                return

            # Configure aiohttp session with proxy
            proxy_url = get_aiohttp_proxy_url()
            async with aiohttp.ClientSession() as session:
                # Get user token
                user_token = await self.get_user_token(session, customer_id, account_number)
                if not user_token:
                    return

                # Get billing details
                billing_response = await self.get_billing_details(session, account_number, user_token)
                if not billing_response:
                    return

                # Download bill
                await self.download_bill(session, account_number, billing_response, user_token)

        except Exception as e:
            logger.error(f"Error processing account {account_number}: {str(e)}")

    @with_retry(max_retries=3)
    async def get_user_token(self, session: aiohttp.ClientSession, customer_id: str, account_number: str) -> Optional[str]:
        """Get user token for API requests."""
        if not self.navigation_headers:
            logger.error("No navigation headers available while getting user token")
            return None

        headers = {
            'Content-Type': 'application/json',
            'Origin': 'https://business.comcast.com',
            'Referer': 'https://business.comcast.com/account/bill',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'Cb-Authorization': '',
        }
        headers.update(self.navigation_headers)

        proxy_url = get_aiohttp_proxy_url()
        async with session.post(
            'https://business-self-service-prod.codebig2.net/business-bootstrap-api/v1/api/state/application/orionInitialState',
            headers=headers,
            json={
                "customerId": customer_id,
                "userContextId": self.navigation_headers.get('tracking-id'),
            },
            proxy=proxy_url
        ) as response:
            if response.status != 200:
                raise Exception(f"Failed to get user token. Status: {response.status}")

            authorization_response = await response.json()
            user_token = authorization_response.get('initialStateModel', {}).get('userToken')
            if not user_token:
                raise Exception("No user token found in response")

            logger.info(f"User token for account {account_number}: {user_token}")
            return user_token

    @with_retry(max_retries=3)
    async def get_billing_details(self, session: aiohttp.ClientSession, account_number: str, user_token: str) -> Optional[Dict]:
        """Get billing details with retries."""
        if not self.navigation_headers:
            logger.error("No navigation headers available while getting billing details")
            return None

        headers = {
            'Content-Type': 'application/json',
            'Origin': 'https://business.comcast.com',
            'Referer': 'https://business.comcast.com/account/bill',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'Cb-Authorization': user_token,
        }
        headers.update(self.navigation_headers)

        proxy_url = get_aiohttp_proxy_url()
        async with session.post(
            'https://business-self-service-prod.codebig2.net/billing-api/v1/bill/getDetails',
            headers=headers,
            json={
                "billingArrangementId": account_number,
                "isEnterprise": False,
                "isOrionCustomer": False
            },
            proxy=proxy_url
        ) as response:
            if response.status != 200:
                raise Exception(f"Failed to get billing details. Status: {response.status}")

            billing_response = await response.json()
            logger.debug(f"Billing API Response for account {account_number}: {billing_response}")
            return billing_response

    @with_retry(max_retries=3)
    async def download_bill(self, session: aiohttp.ClientSession, account_number: str, billing_response: Dict, user_token: str):
        """Download bill PDF."""
        if not self.navigation_headers:
            logger.error("No navigation headers available while downloading bill")
            return

        bill_id = billing_response.get('summary', {}).get('billId')
        if not bill_id:
            raise Exception(f"No billId found in response for account {account_number}")

        headers = {
            'Content-Type': 'application/json',
            'Origin': 'https://business.comcast.com',
            'Referer': 'https://business.comcast.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'Cb-Authorization': user_token,
        }
        headers.update(self.navigation_headers)

        proxy_url = get_aiohttp_proxy_url()
        async with session.post(
            'https://business-self-service-prod.codebig2.net/billing-api/v1/bill/download',
            headers=headers,
            json={
                "billingArrangementId": account_number,
                "billId": bill_id,
                "isEnterprise": False,
                "isOrionCustomer": False
            },
            proxy=proxy_url
        ) as download_response:
            if download_response.status != 200:
                raise Exception(f"Failed to download bill. Status: {download_response.status}")

            pdf_content = await download_response.read()
            pdf_filename = f"bill_{account_number}_{bill_id}.pdf"
            with open(f"bills/{pdf_filename}", "wb") as f:
                f.write(pdf_content)
            logger.info(f"Saved bill PDF to {pdf_filename}")

    async def run(self):
        """Main execution flow."""
        try:
            # Get credentials
            try:
                username, password = self.get_credentials()
            except ValueError as e:
                logger.error(str(e))
                return

            await self.setup()
            await self.login(username, password)

            # Wait for navigation response
            try:
                if not self.navigation_response_future:
                    logger.error("Navigation response future not initialized")
                    return

                navigation_response = await asyncio.wait_for(self.navigation_response_future, timeout=30)
                accounts_data = json.loads(navigation_response)
                customer_id = accounts_data.get('custGuid')
                accounts = accounts_data.get('accounts', [])

                if not accounts:
                    logger.error("No accounts found in the navigation response")
                    return

                for account in accounts:
                    await self.process_account(account, customer_id)

            except asyncio.TimeoutError:
                logger.error("Timeout waiting for navigation response")
            except Exception as e:
                logger.error(f"Error processing navigation response: {str(e)}")

        finally:
            if self.browser:
                await self.browser.close()

async def main():
    scraper = ComcastScraper()
    await scraper.run()

if __name__ == "__main__":
    asyncio.run(main())
