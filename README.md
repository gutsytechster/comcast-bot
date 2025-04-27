# Comcast Business Bill Scraper

An automated tool to download bills from Comcast Business accounts using browser automation and API calls.

## Features

- Automated login to Comcast Business portal
- Multi-account support
- Automatic bill download in PDF format
- Proxy support for both browser and API requests
- Retry mechanism for failed requests
- Detailed logging
- Environment-based configuration

## Prerequisites

- Python 3.8 or higher
- Comcast Business account credentials
- (Optional) Proxy server for routing requests

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/comcast-bot.git
cd comcast-bot
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Playwright browsers:
```bash
playwright install
```

5. Create a `.env` file:
```bash
cp .env.example .env
```

6. Edit `.env` with your credentials:
```
# Comcast Business credentials
COMCAST_USERNAME=your_username_here
COMCAST_PASSWORD=your_password_here

# Proxy configuration (optional)
PROXY_SERVER=http://proxy.example.com:8080
PROXY_USERNAME=proxy_username
PROXY_PASSWORD=proxy_password
```

## Usage

Run the scraper:
```bash
python comcast.py
```

The script will:
1. Log in to your Comcast Business account
2. Navigate through your accounts
3. Download bills for each account
4. Save PDFs in the `bills` directory

## Project Structure

- `comcast.py`: Main scraper implementation
- `utils.py`: Utility functions and decorators
- `requirements.txt`: Project dependencies
- `.env`: Configuration file (not in version control)
- `.env.example`: Example configuration file
- `bills/`: Directory for downloaded bills

## Technical Details
The Comcast Business website is generally accessible for automated interactions and does not require proxy usage by default. However, the site implements rate limiting - multiple login attempts within a short time period will trigger a temporary block, preventing the password entry page from loading.

The website relies heavily on browser session state for API functionality. Direct API calls cannot be easily replicated without first establishing a valid browser session through the normal login flow.

The script implements robust error handling with:
- Automatic retries for failed requests
- Comprehensive error logging for debugging
- Status code validation and recovery
- Session management and renewal

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is for educational purposes only. Use responsibly and in accordance with Comcast's terms of service.
