import asyncio
import aiofiles
import csv
import os
import time
import logging

logger = logging.getLogger("ADS_Engine")

_SENTINEL = object()

class PerformanceLogger:
    def __init__(self, filename="trades.csv"):
        self.filename = filename
        self._queue = asyncio.Queue()
        self._fieldnames = [
            "timestamp", "epoch", "signal_type", "bias", "strike_price",
            "gap", "effective_threshold", "cvd", "velocity", "binance_ofi",
            "up_ask", "down_ask", "size", "target_ask", "order_id", 
            "fill_status", "pnl_at_settlement", "epoch_outcome", "latency"
        ]
        self._is_running = False

    async def log(self, record: dict):
        """Non-blocking: put the record into the queue."""
        if not isinstance(record, dict):
            return
            
        # Ensure all fieldnames exist in the record
        sanitized_record = {k: record.get(k, "") for k in self._fieldnames}
        if "timestamp" not in sanitized_record or not sanitized_record["timestamp"]:
            sanitized_record["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        await self._queue.put(sanitized_record)

    def _to_csv_line(self, record: dict) -> str:
        """Convert a record dict to a CSV formatted string line."""
        import io
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=self._fieldnames)
        writer.writerow(record)
        return output.getvalue()

    async def run(self):
        """Dedicated writer loop — the only coroutine that writes to disk."""
        self._is_running = True
        
        # Write header if file is new
        if not os.path.exists(self.filename):
            async with aiofiles.open(self.filename, mode="w", newline="") as f:
                header = ",".join(self._fieldnames) + "\n"
                await f.write(header)
                await f.flush()

        logger.info(f"PerformanceLogger: Started writing to {self.filename}")
        
        try:
            while True:
                record = await self._queue.get()
                if record is _SENTINEL:
                    self._queue.task_done()
                    break
                    
                async with aiofiles.open(self.filename, mode="a", newline="") as f:
                    await f.write(self._to_csv_line(record))
                    await f.flush()
                self._queue.task_done()
        except asyncio.CancelledError:
            logger.info("PerformanceLogger: Task cancelled.")
        except Exception as e:
            logger.error(f"PerformanceLogger Error: {e}")
        finally:
            self._is_running = False

    async def stop(self):
        """Signal the writer loop to stop and wait for queue to flush."""
        self._is_running = False
        await self._queue.put(_SENTINEL)
        await self._queue.join()
        logger.info("PerformanceLogger: Flushed and stopped.")
