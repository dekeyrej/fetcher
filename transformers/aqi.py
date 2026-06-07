""" ... """
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import arrow

from microservice import MicroService

"""
From https://www.airnow.gov/sites/default/files/2020-05/aqi-technical-assistance-document-sept2018.pdf
(note: this is imported _outside_ the AQIServer class context)
"""
AQIData = {
    "aqi": {"adjectives": ["Good",      "Moderate",    "Unhealthy for Sensitive Groups", "Unhealthy", "Very Unhealthy", "Hazardous"],
            "colors" :    ["(0,228,0)", "(255,255,0)", "(255,126,0)",                    "(255,0,0)", "(143,63,151)",   "(126,0,35)"],
            "values":     [ (0,50),      (51,100),      (101,150),                        (151,200),   (201,300),        (301,500)]},
    "pollutants": {
        "o3":    {"name": "Ozone", "weight": 47.998, "units": "ppb", "decimals": 0,
                    "values": [(0,54), (55,70), (71,85), (86,105), (106,200), (201,500)]}, 
        "pm2_5": {"name": "Particulate Matter (2.5 microns)", "weight": 1, "units": "ug/m3", "decimals": 1,
                    "values": [(0,12), (12.1,35.4), (35.5,55.4), (55.5,150.4), (150.5,250.4), (250.5,500.4)]}, 
        "pm10":  {"name": "Particulate Matter (10 microns)", "weight": 1, "units": "ug/m3", "decimals": 0,
                    "values": [(0,54), (55,154), (155,254), (255,354), (355,424), (425,604)]}, 
        "co":    {"name": "Carbon Monoxide", "weight": 28.01, "units": "ppm",   "decimals": 1,
                    "values": [(0,4.4), (4.5,9.4), (9.5,12.4), (12.5,15.4), (15.5,30.4), (30.5,50.4)]}, 
        "so2":   {"name": "Sulfur Dioxide", "weight": 64.065, "units": "ppb",   "decimals": 0,
                    "values": [(0,35), (36,75), (76,185), (186,304), (305,604), (605,1004)]}, 
        "no2":   {"name": "Nitrogen Dioxide", "weight": 46.006, "units": "ppb",   "decimals": 0,
                    "values": [(0,53), (54,100), (101,360), (361,649), (650,1249), (1250,2049)]}
    }
}

class AQIServer(MicroService):
    """ ... """
    def __init__(self):
        super().__init__()
        self.type = 'AQI'

    def update(self, updatedata=None) -> dict:
        """ ... """
        values = {}
        if updatedata is not None:
            utc_measurement_time = arrow.get(str(updatedata['list'][0]['dt']), 'X')
            max_score = 0
            max_row = 0
            max_pollutant = ""
            # loop through the pollutants and find the max score
            for pollutant in AQIData['pollutants'].keys():
                raw_value = updatedata["list"][0]["components"][pollutant]
                logging.debug(f"Raw value for {pollutant}: {raw_value}")
                converted_value = self.convert_reading(raw_value, pollutant)
                logging.debug(f"Converted value for {pollutant}: {converted_value}")
                scaled_value, row = self.scaled_reading(converted_value, pollutant)
                logging.debug(f"Scaled value for {pollutant}: {scaled_value}, row: {row}")
                if scaled_value > max_score:
                    max_score = scaled_value
                    max_row = row
                    max_pollutant = pollutant

            values = {
                'date_time': utc_measurement_time.to(self.timezone).format('MM/DD/YYYY h:mm A ZZZ'),
                'aqi_score': max_score,
                'aqi_adjective': AQIData["aqi"]["adjectives"][max_row],
                'color': AQIData["aqi"]["colors"][max_row],
                'main_pollutant': AQIData["pollutants"][max_pollutant]["name"]
            }
            logging.debug(f"{type(self).__name__} updated: AQI {max_score} ({values['aqi_adjective']}) due to {values['main_pollutant']} at {values['date_time']}")
        return values

    def convert_reading(self, val: float|int, pol: str) -> float|int:
        """
        Values delivered by OWM are all in micrograms per cubic meter.
        function (1) converts to ppm or ppb, and
                 (2) returns the correct significant digits
        """
        units    = AQIData['pollutants'][pol]["units"]
        decimals = AQIData['pollutants'][pol]["decimals"]
        weight   = AQIData['pollutants'][pol]["weight"]

        match units:
            case "ppm":    conversion = 24.45 / (weight * 1000)
            case "ppb":    conversion = 24.45 / weight
            case "ug/m3":  conversion = 1
            case _:        raise ValueError(f"Unknown units: {units}")

        if decimals == 0:
            return int(round(val * conversion * 10**decimals, 0)/10**decimals)
        else:
            return round(val * conversion * 10**decimals, 0)/10**decimals

    def scaled_reading(self, cval: float|int, pol: str) -> int:
        """
        function scales the converted value based on the pollutants 'Break Points'
        and returns the (AQI) scaled value and the row in the table (AQI Level).
        https://www.airnow.gov/sites/default/files/
                 2020-05/aqi-technical-assistance-document-sept2018.pdf
        """
        aq = AQIData['aqi']['values']
        pm = AQIData['pollutants'][pol]['values']
        scaled = 0
        row = 0
        for i in range(6):
            if pm[i][0] <= cval <= pm[i][1]:
                row = i
                scaled = int(round((cval - pm[i][0]) * (aq[i][1] - aq[i][0])/
                                                       (pm[i][1] - pm[i][0]) + aq[i][0],0))
                return scaled, row
        return scaled, row

if __name__ == '__main__':
    AQIServer().run()
