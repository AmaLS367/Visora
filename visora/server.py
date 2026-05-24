import os
import logging
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Setup basic logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("visora.server")

# Initialize FastMCP Server
mcp = FastMCP("Visora")

# Import all tools to trigger registration decorators on startup
# This resolves any module imports beautifully as mcp is fully initialized.
from visora.tools import vision, animation, scene, mesh, queue  # noqa: E402, F401

if __name__ == "__main__":
    # Start the FastMCP server
    logger.info("Running Visora server via FastMCP...")
    mcp.run()
