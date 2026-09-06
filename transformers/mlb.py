""" ... """
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import arrow

from transformer import Transformer

class MLBServer(Transformer):
    """ ... """
    def __init__(self):
        super().__init__()
        self.type = 'MLB'
        self.update_period = 20
        self.rset('period:MLB', self.update_period) # initialize the period in Redis for the fetcher to read

    def update(self, updatedata: list[dict]) -> list[dict]:
        """ ... """
        tnow = arrow.now().to(self.timezone)
        events = updatedata
        if events is not None:
            values = []
            # start_times = []
            next_start_time = tnow.replace(hour=23,minute=59,second=59)
            game_count = len(events)
            pre_games = in_games = post_games = 0
            for event in events:
                game, start_time = self._load_game(event)
                values.append(game)
                # start_times.append(start_time)
                status = game['status']
                if status == 'post':
                    post_games += 1
                elif status == 'in':
                    in_games += 1
                else:
                    pre_games += 1
                    if tnow <= start_time < next_start_time:
                        next_start_time = start_time

            if game_count == 0 or (in_games == 0 and post_games == game_count): # no games scheduled or all games finished
                if tnow.hour <= 11:
                    next_valid = tnow.replace(hour=11,minute=30,second=0) # 11:30 AM today
                else:
                    next_valid = tnow.shift(days=+1).replace(hour=11,minute=30,second=0) # 11:30 AM tomorrow
                self.update_period = (next_valid - tnow).seconds
            elif in_games > 0:  # at least one game in progress, update every 20 seconds
                # next_valid = \
                #     tnow.shift(seconds=+self.update_period).format('MM/DD/YYYY h:mm:ss A Z')
                self.update_period = 20
            else: # no games in progress but at least one game still scheduled, sleep until the next game starts or 15 minutes, whichever is sooner
                next_valid = next_start_time
                self.update_period = min((next_valid - tnow).seconds, 15*60)
            
            self.rset('period:MLB', self.update_period) # update the period in Redis for the fetcher to read

            logging.info(f'{type(self).__name__} updated. Next update period: {self.update_period} seconds.')
            return values

    def _load_game(self, game: dict) -> tuple[dict, str]:
        """ ... """
        values = {}
        values['id']         = game['id']
        start_time           = arrow.get(game['date'],'YYYY-MM-DD[T]HH:mmZ').to(self.timezone)
        values['startTime']  = start_time.format('MM/DD/YYYY h:mm A Z')
        values['seasonType'] = game['season']['slug']
        values.update(self._team_values_and_scores(game['competitions'][0]))
        return values, start_time
    
    def _team_values_and_scores(self, competition: dict) -> dict:
        values = {}
        
        values['status'] = status           = competition['status']['type']['state'] # pre, in, post
        values['hasPlayByPlay']             = competition.get('playByPlayAvailable', False)
        
        for i in range(2):
            prefix = 'home' if i == 0 else 'away'
            values[f'{prefix}Abbreviation'] = competition['competitors'][i]['team']['abbreviation']
            values[f'{prefix}Color']        = competition['competitors'][i]['team'].get('color', '000000')
            values[f'{prefix}Record']       = competition['competitors'][i].get('record', '')
            values[f'{prefix}Logo']         = competition['competitors'][i]['team']['logo']
            if status in ['in', 'post']:
                values[f'{prefix}Score']    = competition['competitors'][i]['score']
                values[f'{prefix}Hits']     = competition['competitors'][i]['hits']
                values[f'{prefix}Errors']   = competition['competitors'][i]['errors']
        
        if status == 'in':
            values['inning']                = competition['status']['period']
            values['inningState']           = competition['status']['type']['shortDetail'][0:3]
            if values['inningState'] in ['Top', 'Bot']:
                # Top, Mid, Bot, End
                values['balls']             = competition['situation'].get('balls',0)
                values['strikes']           = competition['situation'].get('strikes',0)
                values['outs']              = competition['situation'].get('outs',0)
                values['onFirst']           = competition['situation'].get('onFirst',False)
                values['onSecond']          = competition['situation'].get('onSecond',False)
                values['onThird']           = competition['situation'].get('onThird',False)
            
            if values['hasPlayByPlay']:
                values['lastPlay']     = competition['situation']['lastPlay'].get('text','')

        return values

if __name__ == '__main__':
    MLBServer().run()
