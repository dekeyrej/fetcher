""" reads events.json and loads it into the database """
import json
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from transformer import Transformer

class NextEvent(Transformer):
    """ ... """
    def __init__(self):
        super().__init__()
        self.type = 'Events'

    def update(self, updatedata: list[dict]) -> list[dict]:
        with open('events.json', 'r') as f:
            values = json.load(f)
        logging.info(f'{type(self).__name__} updated.')
        return values

if __name__ == '__main__':
    NextEvent().run()
