import logging

from visora.app import mcp
from visora.config import get_settings

settings = get_settings()

# Setup basic logging
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("visora.server")

# Import all tools to trigger registration decorators on startup
from visora.tools import animation, mesh, queue, scene, vision

if __name__ == "__main__":
    # Start the FastMCP server
    logger.info("Running Visora server via FastMCP...")
    mcp.run()
