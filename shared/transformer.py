from abc import abstractmethod
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
import os

import arrow
import orjson

from redis_lib import RedisClient

class Transformer(RedisClient):
    def __init__(self, log_level: str = 'INFO'):
        super().__init__(redis_url=None)
        logging.getLogger().setLevel(getattr(logging, log_level.upper(), logging.INFO))
        self.type = None
        self.timezone       = os.getenv('TIMEZONE', 'America/New_York')

    @abstractmethod
    def update(self, data):
        """ Process incoming data and return a serializable `values` object.
        Must be implemented by subclasses. """
        pass
    
    def message_handler(self, message):
        if message['type'] == 'message':
            updatedata = orjson.loads(message['data'])
            if updatedata.get('type') == self.type:
                logging.info(f"{type(self).__name__} received message: {updatedata.get('type')} at {updatedata.get('updated')}")
                data = {
                    'type': updatedata.get('type', self.type),
                    'updated': updatedata.get('updated', arrow.now().to(self.timezone).format('MM/DD/YYYY h:mm:ss A Z')),
                    'values': self.update(updatedata.get('values', None))
                }
                logging.debug(f"Transformed data: {orjson.dumps(data, option=orjson.OPT_INDENT_2)}")
                self.publish(orjson.dumps(data))

    def run(self):
        # Create/publish server startup message to output_channel
        data = {
            'type': f'{self.type}-Server',
            'updated': arrow.now().to(self.timezone).format('MM/DD/YYYY h:mm:ss A Z'),
            'values': {'message': f'{type(self).__name__} started.'}
        }
        self.publish(orjson.dumps(data))
        logging.info(f"{type(self).__name__} started.")

        # Look for latest raw:{self.type} in K-V, and process with self.update()
        last_raw = self.rget(f'raw:{self.type}')
        if last_raw is not None:
            logging.info(f"Found existing raw data for {self.type} in Redis. Processing with update() before listening for new messages.")
            try:
                last_raw_data = orjson.loads(last_raw)
                data = {
                        'type': self.type,
                        'updated': last_raw_data.get('updated', arrow.now().to(self.timezone).format('MM/DD/YYYY h:mm:ss A Z')),
                        'values': self.update(last_raw_data.get('values', None))
                }
                logging.debug(f"Transformed data: {orjson.dumps(data, option=orjson.OPT_INDENT_2)}")
                self.publish(orjson.dumps(data))
            except Exception as e:
                logging.error(f"Error processing existing raw data for {self.type}: {e}")

        # Start listening for new messages on the input channel
        self.listen()
