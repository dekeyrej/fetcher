"""
This process listens to a Redis pub/sub channel ('raw' for transformers or 'updated' for clients),
based on the selected key, extracts the payload from the received data, and 
persists the selected key as a series of JSON files.

Used for development, debugging and testing purposes - specifically transformers and clients

incoming data format:
{
    "type": "key",
    "updated": "2023-10-01T12:00:00Z",
    "values": {
        "field1": "value1",
        "field2": "value2"
    }
}

saved data format:
filename: output/{channel}-{key}-{updated}.json where channel is 'raw' or 'update'
content: "values" field from the incoming data, pretty-printed as JSON.
"""
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import orjson

from redis_lib import RedisClient

class KVUpdater(RedisClient):
    """
    Class to handle Redis KV store updates.
    """
    def __init__(self, key) -> None:
        super().__init__(redis_url=None)
        self.key = key

    def message_handler(self, message) -> None:
        """
        Handle incoming messages from Redis pub/sub.
        """
        if message.get('type') == 'message':
            try:
                data = orjson.loads(message.get('data'))
                key = data.get('type')
                logging.info(f"Received message with key: {key}")
                if key == self.key:
                    date = data.get('updated').replace(":", "-").replace("/", "-").replace(" ", "_")  # Replace colons, slashes, and spaces for filename compatibility
                    filename = f"output/{self.in_channel}-{key}-{date}.json"
                    payload = data.get('values')
                    if payload:
                        with open(filename, 'wt') as f:
                            f.write(orjson.dumps(payload, option=orjson.OPT_INDENT_2).decode('utf-8'))
                        logging.info(f"Data persisted with key: {key}")
                    else:
                        logging.debug(f"No values to persist for key: {key}. Skipping.")
                else:
                    logging.debug(f"Non-matching key received: {key}. Expected: {self.key}. Skipping.")
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
    import os
    os.makedirs("output", exist_ok=True)
    key = os.getenv("KEY", "WorldCup")
    KVUpdater(key=key).run()