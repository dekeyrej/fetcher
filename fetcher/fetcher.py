import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
import os

import arrow
import orjson

from redis_lib import RedisClient
from scheduler     import Scheduler
from secretmanager import SecretManager

from fetchers import aqi, events, garmin, github, mlb, moon, gcal, nfl, weather #, wc

class Fetcher(RedisClient):
    
    secrets: dict
    timezone: str
    urls: dict
    headers: dict
    workflowid: str
    scheduler: Scheduler

    def __init__(self, log_level: str = 'INFO'):
        super().__init__(redis_url=None)
        logging.getLogger().setLevel(getattr(logging, log_level.upper(), logging.INFO))
        self.secrets = self.read_secrets()
        self.workflowid = self.secrets.get('github_workflow_id', '')
        self.lat_long   = f"lat={self.secrets.get('latitude', '40.7128')}&lon={self.secrets.get('longitude', '-74.0060')}"
        self.urls       = self.build_urls()
        self.headers    = self.build_headers()
        self.secrets = None  # clear secrets from memory after use
        self.timezone    = os.getenv('TIMEZONE', 'America/New_York')
        # initialize the scheduler with the configuration file, dispatcher function as the notifier and local timezone
        self.scheduler = Scheduler(config_file='scheduler.yaml', notifier=self.dispatcher, timezone=self.timezone)
        if self.client is not None:
            # store the configured types in Redis for access by repeaters
            self.rset(f'{self.out_channel}:types', orjson.dumps(self.scheduler.configured_types()))
        for type in ['MLB', 'NFL']: #, 'WorldCup']:
            self.rset(f'period:{type}', self.scheduler.config[type]['period'])  # initialize the period for each task type in Redis for access by the microservices
            # self.scheduler.schedule_next_run(type)  # schedule the first run for each task type based on the configuration

    def read_secrets(self) -> dict:
        """ Read secrets from a file, Vault, Kubernetes, or environment variables. """
        with open("secretcfg.json") as f:
            secretcfg = orjson.loads(f.read())

        with open("secretdef.json") as f:
            secretdef = orjson.loads(f.read())
        sm = SecretManager(secretcfg, log_level='INFO')
        try:
            read_result = sm.execute(secretcfg.get("SOURCE"), "READ", sm, secretdef)
            if read_result.get("status") == "success":
                logging.debug("Secrets retrieved successfully.")
            else:
                logging.error(f"Failed to retrieve secrets: {read_result.get('error', 'Unknown error')}")
        except Exception as e:
            logging.error(f"An error occurred: {e}")
        sm.execute(secretcfg.get("SOURCE"), "LOGOUT", sm)
        del sm  # Clean up the SecretManager instance
        return read_result.get('data', {})
    
    def build_urls(self):
        urls = {
            'AQI': f'https://api.openweathermap.org/data/2.5/air_pollution?appid=' \
                   f'{self.secrets["owmkey"]}&{self.lat_long}',
            'Calendar': f'https://www.googleapis.com/calendar/v3/calendars/' \
                        f'{self.secrets["google_calendar_id"]}/events?key={self.secrets["google_api_key"]}' \
                        f'&orderBy=starttime&singleEvents=true',
            'GitHub': f"https://api.github.com/repos/{self.secrets.get('github_owner', 'octocat')}/{self.secrets.get('github_repo', 'Hello-World')}",
            'MLB': 'https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard',
            'Moon': 'https://api.met.no/weatherapi/sunrise/3.0',
            'NFL': 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard',
            'Track': self.secrets.get('garmin_url', 'https://api.garmin.com/wellness-api/rest/activities'),
            'Weather': f'https://api.openweathermap.org/data/3.0/onecall?appid=' \
                       f'{self.secrets["owmkey"]}&{self.lat_long}' \
                       f'&exclude=minutely,alerts&units=imperial&lang=en',
            'WorldCup': 'https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard',
        }
        return urls
    
    def build_headers(self):
        headers = {
            'GitHub': {
                'Authorization': f"token {self.secrets.get('github_api_key', '')}",
                'Accept': 'application/vnd.github+json'
            },
            'Moon': { 'User-Agent': 'moon.py joedekeyrel@gmail.com' }
        }
        return headers

    def message_handler(self, message) -> None:
        """ 
        Required override of the abstract method for handling incoming Redis pubsub messages. 
        No incoming messages to handle for this microservice, so we can just pass here.
        """
        pass

    ## ToDo: 
    def update_period(self, type: str, period: int):
        ''' Update the period for a given task type in the configuration. (currently used for MLB, NFL, and WorldCup) '''
        if self.scheduler.config[type]['period'] != period:
            logging.debug(f"Updating period for {type} from {self.scheduler.config[type]['period']} to {period} seconds")
            if period < 60:
                if type == 'MLB' and period < 20:
                    logging.warning(f"Period for {type} is less than 20 seconds. This may cause issues with scheduling and task execution.")
                    period = 20  # set a minimum period of 20 seconds for MLB to avoid scheduling issues and task execution overlaps
                elif type in ['NFL', 'WorldCup'] and period < 60:
                    logging.warning(f"Period for {type} is less than 60 seconds. This may cause issues with scheduling and task execution.")
                    period = 60  # set a minimum period of 60 seconds to avoid scheduling issues and task execution overlaps
            self.scheduler.set_period(type, period)  # update the period for this task type in the scheduler configuration
            self.rset(f'period:{type}', period)  # update the period for this task type in Redis for access by the microservices
            self.scheduler.schedule_next_run(type, Reschedule=True)  # reschedule the next run for this task type with the new period
            logging.info(f"Updated period for {type} to {period} seconds and rescheduled next run for "
                         f"{arrow.get(self.scheduler.config[type]['next_run_time']).to(self.timezone).format('YYYY-MM-DD HH:mm:ss')}")
    
    async def dispatcher(self, type: str):
        logging.debug(f"Dispatching fetch for type: {type}")
        rawmessage = {
            'type': type,
            'updated': arrow.now().to(self.timezone).format('MM/DD/YYYY h:mm:ss A Z')
        }
        
        if type == 'AQI':
            rawmessage['values'] = await     aqi(self.urls[type], self.timezone)
        elif type == 'Events':
            rawmessage['values'] = await  events()
        elif type == 'Track':
            rawmessage['values'] = await  garmin(self.urls[type], self.timezone)
        elif type == 'GitHub':
            rawmessage['values'] = await  github(self.urls[type], self.timezone, headers=self.headers['GitHub'], workflowid=self.workflowid)
        elif type == 'MLB':
            rawmessage['values'] = await     mlb(self.urls[type], self.timezone) 
        elif type == 'Moon':
            rawmessage['values'] = await    moon(self.urls[type], self.timezone, headers=self.headers['Moon'], lat_long=self.lat_long)
        elif type == 'Calendar':
            rawmessage['values'] = await    gcal(self.urls[type], self.timezone)
        elif type == 'NFL':
            rawmessage['values'] = await     nfl(self.urls[type], self.timezone)  
        elif type == 'Weather':
            rawmessage['values'] = await weather(self.urls[type], self.timezone)
        # elif type == 'WorldCup':
        #     rawmessage['values'] = await      wc(self.urls[type], self.timezone)
        else:
            logging.error(f"Unknown type: {type}")

        # update the period for MLB based on the value set by the mlb.py microservice, defaulting to 20 seconds if not set
        self.update_period('MLB', int(self.rget('period:MLB') or 20))
        # update the period for NFL based on the value set by the nfl.py microservice, defaulting to 60 seconds if not set
        self.update_period('NFL', int(self.rget('period:NFL') or 60))
        # # update the period for World Cup based on the value set by the wc.py microservice, defaulting to 60 seconds if not set
        # self.update_period('WorldCup', int(self.rget('period:WorldCup') or 60))
        
        if self.client is not None:
            logging.debug(orjson.dumps(rawmessage))
            if rawmessage['values'] is None and type != 'Events':  # events are read by the events microservice directly from the file, so we can skip fetching them here
                logging.warning(f"No data fetched for type: {type}")
            else:
                self.publish(orjson.dumps(rawmessage))  # publish the data to the redis 'raw' channel
        else:
            logging.info(orjson.dumps(rawmessage))

    async def run(self):
        try:
            await self.scheduler.run()  # run the scheduler to manage task execution based on the configured schedule
        except Exception as e:
            logging.error(f"Error in fetcher run loop: {e}")
            raise e

if __name__ == "__main__":
    import asyncio
    asyncio.run(Fetcher().run())
