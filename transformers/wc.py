""" FIFA World Cup server - reads data from ESPN scoreboard API """
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import arrow
import orjson

from microservice import MicroService

class WCServer(MicroService):
    """ ... """
    def __init__(self):
        super().__init__()
        self.type = 'WorldCup'
        self.update_period = 60
        self.rset('period:WorldCup', self.update_period) # initialize the period in Redis for the fetcher to read
        with open('wcgroups.json') as f:
            self.wcgroups = orjson.loads(f.read())
        logging.debug(orjson.dumps(self.wcgroups, option=orjson.OPT_INDENT_2).decode('utf-8'))

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
                game, start_time = self.load_game(event)
                if game is None:
                    continue
                self.print_game(game)
                values.append(game)
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
                if tnow.hour <= 12:
                    next_valid = tnow.replace(hour=12,minute=0,second=0) # 12:00 PM today
                else:
                    next_valid = tnow.shift(days=+1).replace(hour=12,minute=0,second=0) # 12:00 PM tomorrow
                self.update_period = (next_valid - tnow).seconds
            elif in_games > 0:  # at least one game in progress, update every 60 seconds
                # next_valid = \
                #     tnow.shift(seconds=+self.update_period).format('MM/DD/YYYY h:mm:ss A Z')
                self.update_period = 60
            else: # no games in progress but at least one game still scheduled, sleep until the next game starts or 15 minutes, whichever is sooner
                next_valid = next_start_time
                self.update_period = min((next_valid - tnow).seconds, 15*60)
            
            self.rset('period:WorldCup', self.update_period) # update the period in Redis for the fetcher to read

            logging.info(f'{type(self).__name__} updated. Next update period: {self.update_period} seconds.')
            logging.debug(orjson.dumps(values, option=orjson.OPT_INDENT_2).decode('utf-8'))
            return values

    def load_game(self, game: dict) -> tuple[dict, str]:
        """ ... """
        values = {}
        values['id']         = game.get('id', '')
        if values['id'] == '':
            logging.warning(f"Game ID is missing for game: {orjson.dumps(game, option=orjson.OPT_INDENT_2).decode('utf-8')}")
            return None, None
        start_time           = arrow.get(game['date'],'YYYY-MM-DD[T]HH:mmZ').to(self.timezone)
        values['startTime']  = start_time.format('MM/DD/YYYY h:mm A Z')
        values['seasonType'] = game['season']['slug']
        self.teams = {
            competitor['team'].get('id', ''): competitor['team'].get('abbreviation', '')
            for competitor in game['competitions'][0].get('competitors', [])
        }
        logging.debug(f"Teams: {self.teams}")
        if values['seasonType'] == 'group-stage':
            values['group'] = self.wcgroups.get(game['competitions'][0]['competitors'][0]['team'].get('abbreviation', ''), '')
        values.update(self.team_values_and_scores(game['competitions'][0]))
        return values, start_time
    
    def team_values_and_scores(self, competition: dict) -> dict:
        values = {}
        values['status'] = status           = competition['status']['type']['state'] # pre, in, post
        detail_count = len(competition['details'])
        if detail_count > 0:
            details = competition['details']
        
        for i in range(2):
            prefix = 'home' if i == 0 else 'away'
            values[f'{prefix}id']           = competition['competitors'][i]['team'].get('id', '')
            values[f'{prefix}Abbreviation'] = competition['competitors'][i]['team'].get('abbreviation', '')
            values[f'{prefix}Name']         = competition['competitors'][i]['team'].get('displayName', '')
            values[f'{prefix}Color']        = competition['competitors'][i]['team'].get('color', '000000')
            values[f'{prefix}Record']       = competition['competitors'][i]['records'][0].get('summary', '')
            values[f'{prefix}Logo']         = competition['competitors'][i]['team'].get('logo', '')
            if status in ['in', 'post']:
                values[f'{prefix}Score']    = competition['competitors'][i]['score']
        
        if status in ['in', 'post']:
            values['period']                = competition['status']['period']
            values['perioddes']             = f"{competition['status']['type'].get('description', '').replace('First', '1st').replace('Second', '2nd')} -  {competition['status'].get('displayClock', '')}" # pre, top, mid, bot, end
            if detail_count > 0:
                values['summary']               = self.format_detail(details, values['homeAbbreviation'])
                values['lastPlay']              = values['summary'][-1] if detail_count > 0 else ''

        return values
    
    def format_detail(self, details: list, hometeam: str) -> list[str]:
        lines = []
        for detail in details:
            line = {}
            line['time'] = detail['clock'].get('displayValue', '')
            type = detail['type'].get('text', '').replace('Goal', '⚽').replace('Scored', '⚽').replace('Yellow Card', '🟨').replace('Red Card', '🟥') # yellow and red square emojis .replace('Goal - Header', '⚽').replace('Own Goal', '⚽')
            name = detail['athletesInvolved'][0].get('shortName', '')
            jersey = detail['athletesInvolved'][0].get('jersey', '')
            team = self.teams.get(detail.get('team', {}).get('id', ''), '')
            if team == hometeam:
                # time = detail['clock'].get('displayValue', '').ljust(6, ' ')
                line['home'] = f"{name} #{jersey.ljust(2)} {type}"
                line['away'] = ''
            else:
                # time = detail['clock'].get('displayValue', '').ljust(6, ' ')
                line['home'] = ''
                line['away'] = f"{type} {name} #{jersey}"
            lines.append(line)
        return lines
    
    def print_game(self, game: dict) -> None:
                
        """ ... """
        lines = []
        if game['status'] == 'pre':
            start_time = arrow.get(game['startTime'],'MM/DD/YYYY h:mm A Z').to(self.timezone)
            lines.append(f"Sched  {start_time.to('America/New_York').format('hh:mm A')} - Group {game['group']}")
            lines.append(f"{game['homeAbbreviation']}               ({game['homeRecord']})")
            lines.append(f"{game['awayAbbreviation']}               ({game['awayRecord']})")
        elif game['status'] == 'in':
            lines.append(f"{game['perioddes']}")
            lines.append(f"{game['homeAbbreviation']}   {game['homeScore'].rjust(7)}")  # \N{REGIONAL INDICATOR SYMBOL LETTER U}\N{REGIONAL INDICATOR SYMBOL LETTER S}
            lines.append(f"{game['awayAbbreviation']}   {game['awayScore'].rjust(7)}")  # \N{REGIONAL INDICATOR SYMBOL LETTER P}\N{REGIONAL INDICATOR SYMBOL LETTER A}
            if 'summary' in game:
                if len(game['summary']) > 3:
                    lines.append(f"Summary (showing last 3 of {len(game['summary'])}):")
                    for line in game['summary'][-3:]: # only print the last 3 details to avoid flooding the console
                        lines.append(line)
                else:
                    lines.append("Summary:")
                    for line in game['summary']:
                        lines.append(line)
        else: # game['status'] == 'post'
            lines.append(f"{game['perioddes'].replace('Full Time - ', 'Final - ').ljust(6)} - Group {game['group']}")
            lines.append(f"{game['homeAbbreviation']}   {game['homeScore'].rjust(7)}     ({game['homeRecord']})")
            lines.append(f"{game['awayAbbreviation']}   {game['awayScore'].rjust(7)}     ({game['awayRecord']})")
            if 'summary' in game:
                lines.append("Summary:")
                for line in game['summary']:
                    lines.append(line)
                    # if 'Goal' in line:
                    #     lines.append(line)

        for line in lines:
            print(line)
        print("\n")

if __name__ == '__main__':
    WCServer().run()
