"""
step 2 in the Redis-first chain. This process listens to a Redis pub/sub channel,
extracts the key and payload from the received data, and persists it to the Redis KV store.

incoming data format:
{
    "type": "key",
    "updated": "2023-10-01T12:00:00Z",
    "values": {
        "field1": "value1",
        "field2": "value2"
    }
}

stored data format for Redis KV store:
key = {
        "updated": "2023-10-01T12:00:00Z",
        "values": {
            "field1": "value1",
            "field2": "value2"
        }
      }
"""
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import orjson

from redis_lib import RedisClient

class KVUpdater(RedisClient):
    """
    Class to handle Redis KV store updates.
    """
    def __init__(self) -> None:
        super().__init__(redis_url=None)

    def message_handler(self, message) -> None:
        """
        Handle incoming messages from Redis pub/sub.
        """
        if message.get('type') == 'message':
            try:
                data = orjson.loads(message.get('data'))
                key = data.get('type')
                payload = {
                    "updated": data.get('updated'),
                    "values": data.get('values')
                }
                if key:
                    if payload['values']:
                        self.rset(f"{self.in_channel}:{key}", orjson.dumps(payload))
                        logging.info(f"Data persisted with key: {key}")
                    else:
                        logging.warning(f"No values to persist for key: {key}. Skipping.")
                else:
                    logging.warning("Invalid message format. 'key' and 'payload' are required.")
            except orjson.JSONDecodeError:
                logging.error("Failed to decode JSON message.")
            except Exception as e:
                logging.error(f"An error occurred while persisting data: {e}")

    def run(self) -> None:
        """
        Main function to listen to Redis pub/sub channel and persist data.
        """
        # use RedisClient.listen which sets up pubsub and thread
        try:
            self.listen()
        except KeyboardInterrupt:
            logging.info("Stopped listening for messages.")


if __name__ == "__main__":
    KVUpdater().run()