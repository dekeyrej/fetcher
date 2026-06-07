"""
Repeater Service
"""
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import orjson

from redis_lib import RedisClient

class Repeater(RedisClient):
    """ Class to handle repeating raw updates from prod to dev/test. """
    def __init__(self) -> None:
        super().__init__(redis_url=None, prod=True)

    def message_handler(self, message):
        if message['type'] == 'message':
            data = orjson.loads(message['data'])
            logging.info(f"Repeating {self.in_channel} message type: {data.get('type', 'unknown')}")
            # Repeat the message to the local Redis instance
            self.publish(message['data'])

    def run(self) -> None:
        # read raw:types from prod redis, then loop through each type and pull the latest raw data for that type creating a data structure suitable for publishing, and publish to local redis
        types = orjson.loads(self.rget('raw:types', prod=True) or '[]')
        logging.info(f"Found raw types in prod Redis: {types}")
        for t in types:
            last_raw = self.rget(f'raw:{t}', prod=True)
            if last_raw is not None:
                logging.info(f"Found existing raw data for {t} in prod Redis. Processing with update() before listening for new messages.")
                try:
                    last_raw_data = orjson.loads(last_raw)
                    data = {
                            'type': t,
                            'updated': last_raw_data.get('updated', ''),
                            'values': last_raw_data.get('values', None)
                    }
                    logging.debug(f"Transformed data: {orjson.dumps(data, option=orjson.OPT_INDENT_2)}")
                    self.publish(orjson.dumps(data))
                except Exception as e:
                    logging.error(f"Error processing existing raw data for {t}: {e}")
            else:
                logging.info(f"No existing raw data found for {t} in prod Redis.")

        self.listen(prod=True)

if __name__ == "__main__":
    Repeater().run()