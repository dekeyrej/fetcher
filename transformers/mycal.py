""" Reads (google) calendar events for today """
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from microservice import MicroService

class CalendarServer(MicroService):
    """ Subclass of MicroService for reading calendar events """
    def __init__(self):
        super().__init__()
        self.type = 'Calendar'
#       calendar has to be public :-/

    def update(self, updatedata: list[dict]) -> list:
        """ called by MicroService.update() """
        values = []
        if updatedata is not None:
            if len(updatedata) == 0:
                values.append(('No events'))
            else:
                values = [(item["summary"], item["start"]["dateTime"], item["end"]["dateTime"]) for item in updatedata]
        logging.info(f'{type(self).__name__} updated.')
        return values

if __name__ == '__main__':
    CalendarServer().run()
