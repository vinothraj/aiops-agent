import logging
import sys

def setup_logging(log_level: str = "INFO"):
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Set logging level for some verbose libraries if needed
    logging.getLogger("uvicorn.access").setLevel(log_level)
