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


def main() -> None:
    logger.info("Running Visora server via FastMCP...")
    mcp.run()


if __name__ == "__main__":
    main()
