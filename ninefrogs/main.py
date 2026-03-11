from log import setup_logging  # must be first
setup_logging()

import uvicorn  # noqa: E402
from loguru import logger  # noqa: E402

from config import settings  # noqa: E402
from web.app import create_app  # noqa: E402

# Pre-load the embedding model synchronously before the event loop starts.
# sentence-transformers/torch hold the GIL during import and model init,
# which would freeze the asyncio event loop if loaded inside a task.
logger.info("Loading embedding model (pre-event-loop)…")
from embeddings import _get_model  # noqa: E402
_get_model()
logger.info("Embedding model ready.")

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.web_host,
        port=settings.web_port,
        reload=False,
        log_level="info",
    )
