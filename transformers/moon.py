""" Sun and Moon data server """
import logging
from  math import cos, pi
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import arrow

from microservice import MicroService

class MoonServer(MicroService):
    """ subclass of ServerPage to fetch sun and moon data """
    def __init__(self):
        super().__init__()
        self.type = 'Moon'
        self.twelve_hour = True

    def update(self, updatedata=None) -> dict:
        """ 
        fetch web data and update database 
        as of 9/1/2023, Norwegian Met updated its API to version 3.0
        """
        values = {}
        if updatedata is not None:
            sun_data = [
                updatedata[i]['properties'] for i in range(2)
            ]

            moon_data = [
                updatedata[i]['properties'] for i in range(2,4)
            ]
            phase, illumstr = self.moon_condition(moon_data[0]['moonphase'])

            values = {
                'phase': phase,
                'illumstr': illumstr,
                'sunevent': self.sun_event(sun_data, arrow.now().format('X')),
                'moonevent': self.moon_event(moon_data)
            }
            logging.info(f'{type(self).__name__} updated.')
        return values

    def moon_condition(self, moonphase: float) -> tuple[int, float]:
        """ convert moonphase to an integer phase (index of phase image) and an illumination %
            moonphase values seem to be in the range 0.0..359.99
        """
        phase     =              int(moonphase / 3.6 ) % 100  # => 0..99
        illum     = self.age_to_illum(moonphase / 360)        # => 0.0..1.0
        return phase, illum

    def sun_event(self, mnd: list, tstmp) -> str:
        """ determine the next sun event (sunrise or sunset) """
        # sunrise and sunset happen every day - easier
        sunrise   = self.parse_time(mnd[0]['sunrise']['time'])
        sunset    = self.parse_time(mnd[0]['sunset']['time'])
        tomorrow_sunrise = self.parse_time(mnd[1]['sunrise']['time'])
        # determine which sun event is next
        # print(type(tstmp))
        # print(type(sunrise))
        if tstmp <= sunrise:
            event = f"Sunrise:  {self.ts2hhmm(sunrise)}"
        elif tstmp <= sunset:
            event = f"Sunset:   {self.ts2hhmm(sunset)}"
        else:
            event = f"Sunrise:  {self.ts2hhmm(tomorrow_sunrise)}"
        return event

    def moon_event(self, mnd: list) -> str:
        """Determine the next moon event (moonrise or moonset)"""
        events = []

        for day in mnd[:2]:
            if 'moonrise' in day and day['moonrise']['time'] is not None:
                moon_rise = self.parse_time(day['moonrise']['time'])
                events.append(('Rise', moon_rise))
            if 'moonset' in day and day['moonset']['time'] is not None:
                moon_set = self.parse_time(day['moonset']['time'])
                events.append(('Set', moon_set))

        # Sort the events by time and find the next event
        events.sort(key=lambda e: e[1])
        current_time = arrow.now().format('X')

        for event_type, event_time in events:
            if event_time > current_time:
                next_event = (event_type, event_time)
                break

        event_str = f"Moonrise: {self.ts2hhmm(next_event[1])}" if next_event[0] == 'Rise' else f"Moonset:  {self.ts2hhmm(next_event[1])}"
        return event_str

    def age_to_illum(self, age: int) -> float:
        """ convert age (0..100) to a percent illumination """
        if age <= 0.5:
            illum = (1 - cos(age * 2 * pi)) * 50
        else:
            illum = (1 + cos((age - 0.5) * 2 * pi)) * 50
        return f'{illum:.1f}%'

    def parse_time(self, timestr: str) -> arrow:
        """ converts a timestamp string into an arrow (a string?) """
        return arrow.get(timestr).format('X')

    def ts2hhmm(self, tstmp: str) -> str:
        """ converts a timestamp into an arrow and returns either a
            12-hr time, or a 24-hr time
        """
        tnow = arrow.get(tstmp,'X').to(self.timezone)
        if self.twelve_hour:
            out = tnow.format('hh:mm A')
        else:
            out = tnow.format('HH:mm')
        return out

if __name__ == '__main__':
    MoonServer().run()
