""" ... """
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import arrow

from transformer import Transformer

class OWMServer(Transformer):
    dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
            'S','SSW','SW','WSW','W','WNW','NW','NNW']

    """ ... """
    def __init__(self):
        super().__init__()
        self.type = 'Weather'

    def update(self, updatedata: dict) -> dict:
        tnow = arrow.now().to(self.timezone)
        values = {}
        if updatedata is not None:
            values = {
                'current': {
                    'temp': float(updatedata["current"]["temp"]),
                    'fl': float(updatedata["current"]["feels_like"]),
                    'humid': int(updatedata["current"]["humidity"]),
                    'windDir': self._deg_to_dir(int(updatedata["current"]["wind_deg"])),
                    'windSpeed': float(updatedata["current"]["wind_speed"]),
                    'windGust': float(updatedata["current"].get("wind_gust", 0.0)),
                    'desc': updatedata["current"]["weather"][0]["description"],
                    'dn': updatedata["current"]["weather"][0]["icon"][2],
                    'wid': int(updatedata["current"]["weather"][0]["id"]),
                    'nwid': self._to_nwid(updatedata["current"]["weather"][0]["icon"], 
                                         int(updatedata["current"]["weather"][0]["id"]))
                },
                'forecast': [
                    {
                        'dow': 'TOD' if i == 0 else 'TOM' if i == 1 else tnow.shift(days=i).format('ddd').upper(),
                        'dn': updatedata["daily"][i]["weather"][0]["icon"][2],
                        'wid': int(updatedata["daily"][i]["weather"][0]["id"]),
                        'nwid': self._to_nwid(updatedata["daily"][i]["weather"][0]["icon"], 
                                             int(updatedata["daily"][i]["weather"][0]["id"])),
                        'high': int(updatedata["daily"][i]["temp"]["max"]),
                        'low': int(updatedata["daily"][i]["temp"]["min"])
                    } for i in range(8)
                ],
                'hourly': [
                    {
                        'hour': arrow.Arrow.fromtimestamp(float(updatedata["hourly"][i]["dt"]), tzinfo='US/Eastern').format('HH:mm'),
                        'dn': updatedata["hourly"][i]["weather"][0]["icon"][2],
                        'wid': int(updatedata["hourly"][i]["weather"][0]["id"]),
                        'nwid': self._to_nwid(updatedata["hourly"][i]["weather"][0]["icon"], 
                                             int(updatedata["hourly"][i]["weather"][0]["id"])),
                        'temp': int(updatedata["hourly"][i]["temp"]),
                        'feel': int(updatedata["hourly"][i]["feels_like"])
                    } for i in range(48)
                ]
            }
        logging.info(f'{type(self).__name__} updated.')
        return values

    def _to_nwid(self, icon: str, wid: int) -> int:
        """ ... """
        # print(f'Icon: {icon}, WeatherID: {wid}')
        if ((icon[2] == "n") and          # icon[2] # returns "d" for day, or "n" for night
            wid in (800, 801, 802, 951)): # these four WeatherIDs have a unique night icon
            nwid = wid + 61000
        else:
            nwid = wid + 60000
        return nwid

    def _deg_to_dir(self, deg) -> str:
        """ ... """
        return self.dirs[round(deg/22.5) % 16]

if __name__ == '__main__':
    OWMServer().run()
