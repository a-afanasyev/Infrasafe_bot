"""
Start Redis Streams Consumer

Task 1.3: Redis Streams Setup
Background worker script to consume events from Redis Streams
"""

import asyncio
import logging
import signal
import sys

from core.stream_consumer import stream_consumer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


async def shutdown(sig, loop):
    """Cleanup tasks tied to the service's shutdown."""
    logger.info(f"Received exit signal {sig.name}...")

    # Stop consumer
    await stream_consumer.stop()

    # Cancel all running tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]

    logger.info(f"Cancelling {len(tasks)} outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)

    loop.stop()


async def main():
    """Main entry point for consumer"""
    try:
        logger.info("🚀 Starting Analytics Service Stream Consumer...")

        # Initialize consumer
        await stream_consumer.initialize()

        # Start consuming events
        await stream_consumer.consume_events()

    except KeyboardInterrupt:
        logger.info("Consumer interrupted by user")
    except Exception as e:
        logger.error(f"Consumer failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()

    # Handle signals
    signals = (signal.SIGTERM, signal.SIGINT)
    for s in signals:
        loop.add_signal_handler(
            s, lambda s=s: asyncio.create_task(shutdown(s, loop))
        )

    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
        logger.info("🛑 Consumer shutdown complete")
