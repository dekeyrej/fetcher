""" NFL server - reads data from ESPN scoreboard API """
# docker build --build-arg=MICROSERVICE=nfl -t 192.168.86.49:32000/nfl:registry .
# docker push 192.168.86.49:32000/nfl:registry
# kubectl rollout restart -n default deployment nfl

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import arrow

from transformer import Transformer

class NFLServer(Transformer):

    active: int
    update_period: int

    """ ... """
    def __init__(self):
        super().__init__()
        self.type = 'NFL'
        self.update_period = 60
        self.rset('period:NFL', self.update_period) # initialize the period in Redis for the fetcher to read
        # self.active = 0
        # self.output = False

    def update(self, updatedata: dict) -> dict:
        """ ... """
        tnow = arrow.now().to(self.timezone)
        if updatedata:
            seasonid = int(updatedata['season']['type'] - 1)
            weekid = int(updatedata['week']['number'] - 1)
            self.active = 0
            values = {
                'seasontype': updatedata['leagues'][0]['calendar'][seasonid]['label'],
                'weekname':   updatedata['leagues'][0]['calendar'][seasonid]['entries'][weekid]['label'],
                'weekdates':  updatedata['leagues'][0]['calendar'][seasonid]['entries'][weekid]['detail'],
            }
            events = []
            next_start_time = tnow.replace(hour=23,minute=59,second=59)
            games = updatedata['events']
            game_count = len(games)
            pre_games = in_games = post_games = 0
            for game in games:
                events.append(self._read_event(game))
                start_time = arrow.get(game['date']).to(self.timezone)
                status = game['competitions'][0]['status']['type']['state']
                if status == 'post':
                    post_games += 1
                elif status == 'in':
                    in_games += 1
                else:
                    pre_games += 1
                    if tnow <= start_time < next_start_time:
                        next_start_time = start_time
                
            values['events'] = sorted(events, key=lambda x: arrow.get(x['fulldate']))

            # if there are any in-progress games, set the update period to 60 seconds
            if in_games > 0:
                self.update_period = 60
            else:
                self.update_period = 15 * 60

            # if self.update_period != 59: self.update_period = min((next_start_time - tnow).seconds, 15 * 60)
            self.rset('period:NFL', self.update_period)

            logging.info(f'{type(self).__name__} updated. Next update period: {self.update_period} seconds.')
            return values

    def _read_event(self, event):
        """ ... """
        game = {}
        date = arrow.get(event['date']).to(self.timezone)
        game['date']  = date.format('ddd h:mm A')
        game['fulldate']  = date.format('YYYY-MM-DD HH:mm:ss')
        game['week']  = event['week']['number']
        game['state'] = event['competitions'][0]['status']['type']['state']   # 'pre', 'in', 'post'
        home          = event['competitions'][0]['competitors'][0]
        game['homeabrv']   = home['team']['abbreviation']
        game['homeid']     = home['team']['id']
        game['homecolor']  = f"#{home['team'].get('color','FFFFFF')}"
        game['homelogo']   = home['team']['logo']
        if home.get('records',None):
            game['homerecord'] = home['records'][0].get('summary','')
        else:
            game['homerecord'] = ''
        game['homescore']  = home['score']
        away          = event['competitions'][0]['competitors'][1]
        game['awayabrv'] = away['team']['abbreviation']
        game['awayid']     = away['team']['id']
        game['awaycolor']= f"#{away['team'].get('color','FFFFFF')}"
        game['awaylogo']   = away['team']['logo']
        if away.get('records', None):
            game['awayrecord'] = away['records'][0].get('summary','')
        else:
            game['awayrecord'] = ''
        game['awayscore']  = away['score']
        if game['state'] == 'in':
            stat = event['competitions'][0]['status']
            self.active += 1
            game['period'] = stat.get('period',"")
            game['clock']  = stat.get('displayClock',"")
            try:
                if game['clock'] == '00:00' and game['period'] == 2:
                    game['period'] = 'Halftime'
                elif game['period'] == 1:
                    game['period'] = '1st Qtr'
                elif game['period'] == 2:
                    game['period'] = '2nd Qtr'
                elif game['period'] == 3:
                    game['period'] = '3rd Qtr'
                elif game['period'] == 4:
                    game['period'] = '4th Qtr'
                elif game['period'] > 4:
                    game['period'] = 'OT'
            except:
                print("exception in stat")
            situ = event['competitions'][0]['situation']
            game['position']       = situ.get('possessionText',"")
            game['downandyardage'] = situ.get('shortDownDistanceText',"")
            game['downyardsposition'] = situ.get('downDistanceText',"")
            possession = situ.get('possession', None)   
            if possession:
                game['possession'] = game['homeabrv'] if possession == game['homeid'] else game['awayabrv']
        return game

if __name__ == '__main__':
    NFLServer().run()
    