import logging

from backend.app import mcp
from backend.config import get_settings

settings = get_settings()

# Setup basic logging
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("backend.server")

# Import all tools to trigger registration decorators on startup
from backend.tools import animation, asset, bridge, mesh, queue, scene, vision


def main() -> None:
    logger.info("Running Visora server via MCPServer...")
    mcp.run()


if __name__ == "__main__":
    main()
