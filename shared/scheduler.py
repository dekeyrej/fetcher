"""
A simple scheduler that runs tasks at specified intervals based on a configuration file.
The configuration file should be in YAML format and specify the following for each task type:
- slot: the second of the minute when the task should run (0-59)
- period: the interval in seconds between runs of the task
The scheduler will run indefinitely, executing the specified tasks at the appropriate times.
"""
import json
import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
# from datetime import datetime, timezone
# from zoneinfo import ZoneInfo

# # Timezone-aware logging formatter (prints times in America/New_York)
# class TZFormatter(logging.Formatter):
#     def __init__(self, fmt=None, datefmt=None, tz_name: str = 'America/New_York'):
#         super().__init__(fmt=fmt, datefmt=datefmt)
#         self.tz = ZoneInfo(tz_name)

#     def formatTime(self, record, datefmt=None):
#         dt = datetime.fromtimestamp(record.created, timezone.utc).astimezone(self.tz)
#         if datefmt:
#             return dt.strftime(datefmt)
#         return dt.strftime('%Y-%m-%d %H:%M:%S')

# # Configure root logger to use the TZFormatter
# handler = logging.StreamHandler()
# handler.setFormatter(TZFormatter(fmt='%(asctime)s - %(levelname)s - %(message)s'))
# logger = logging.getLogger()
# logger.setLevel(logging.INFO)
# logger.handlers = [handler]

from time import sleep

import arrow
import yaml

class Scheduler:    
    def __init__(self, config_file: str = "scheduler.yaml", notifier=lambda type: print(f"Running {type}"), timezone: str = 'America/New_York'):
        self.notifier = notifier
        self.timezone = timezone
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)
        logging.debug(yaml.dump(self.config, default_flow_style=False, sort_keys=False))
        logging.debug(f"{json.dumps(list(self.config.keys()))}")
        self.queue = []

    def configured_types(self):
        return list(self.config.keys())
    
    def dump_queue(self):
        print("Current schedule:")
        for type, time in self.queue:
            print(f"{type.ljust(8)}: {time.to(self.timezone).format('YYYY-MM-DD HH:mm:ss')}")
    
    def set_period(self, type: str, period: int):
        ''' Update the period for a given task type in the configuration. (currently used for MLB, NFL, and WorldCup) '''
        self.config[type]['period'] = period

    def schedule_next_run(self, type: str, now: arrow.Arrow = None, Reschedule: bool = False):
        now = now or arrow.now().to('UTC')
        slot = self.config[type]['slot']
        period = self.config[type]['period']

        if Reschedule:
            # remove any existing scheduled run for this task type from the queue and reschedule it with the new period
            self.queue = [item for item in self.queue if item[0] != type]  # remove any existing scheduled run for this task type from the queue
        
        if self.config[type].get('next_run_time', None) is None:  ## start-up and when rescheduling after a period update
            ## schedule for next available slot from _now_
            if now.second < slot:
                now = now.replace(second=slot, microsecond=0)
            elif now.second < slot + period and period < 60:
                now = now.replace(second=slot + period, microsecond=0)
            elif now.second < slot + 2 * period and period <= 20:  ## _should only be for MLB, but might pop-up for other dynamically scheduled feeds
                logging.debug("Scheduling for next available slot from now + period, but now is already past the next available slot, so scheduling for the next available slot after that")
                logging.debug(f"Next available slot: {slot + 2 * period}")
                now = now.replace(second=slot + 2 * period, microsecond=0)
            elif now.second > slot:
                now = now.shift(minutes=+1)
                now = now.replace(second=slot, microsecond=0)
        else:
            now = now.shift(seconds=+period)
            if type == 'MLB' and period == 20:
                seconds = now.second
                if seconds == 0:
                    now = now.replace(microsecond=0)
                elif seconds <= 20:
                    now = now.replace(second=20, microsecond=0)
                elif seconds <= 40:
                    now = now.replace(second=40, microsecond=0)
            else:## schedule for next available slot from _now_ + period
                if now.second < slot:
                    now = now.replace(second=slot, microsecond=0)
                elif now.second <= slot + period and period < 60:
                    now = now.replace(second=slot + period, microsecond=0)
                elif now.second > slot:
                    now = now.shift(minutes=+1)
                    now = now.replace(second=slot, microsecond=0)
        logging.info(f"Scheduling next run for {type} at {self.now_str(now, local=True)} (in {period} seconds)")
        self.queue.append((type, now))
        self.queue.sort(key=lambda x: x[1].timestamp())  # sort the queue by next run time
        self.config[type]['next_run_time'] = self.now_str(now)
    
    def now_str(self, t: arrow.Arrow, local: bool = False) -> str:
        if local:
            return t.to(self.timezone).format('YYYY-MM-DD HH:mm:ss')
        return t.to('UTC').format('YYYY-MM-DD HH:mm:ss')

    async def run(self):
        logging.debug(f"Current time: {self.now_str(arrow.now(), local=True)}")
        for type in self.config.keys():
            self.schedule_next_run(type)
        self.dump_queue()
        while True:
            try:
                if len(self.queue) > 0:
                    type, time = self.queue[0]
                    now = arrow.now().to('UTC')
                    logging.debug(f"Current time: {self.now_str(now, local=True)}")
                    if now >= time:
                        logging.debug(f"Running scheduled task for {type} at {self.now_str(now, local=True)}")
                        await self.notifier(type)           # fire the scheduled task
                        self.queue.pop(0)                   # remove the task from the queue (doing this after scheduling the next run, when the next run is MLB can result in no MLB events scheduled)
                        self.schedule_next_run(type, now)   # schedule the next run for this task type
                    for type in self.config.keys():
                        if self.config[type].get('next_run_time', None) is None:
                            logging.error(f"Task type '{type}' is missing 'next_run_time' in the config. This shouldn't happen -- scheduling next run for {type}.")
                            self.schedule_next_run(type)
                    sleep_length = self.queue[0][1].timestamp() - arrow.now().to('UTC').timestamp()
                    logging.debug(f"Sleeping for {sleep_length:.2f} seconds")
                    if sleep_length < 0.01:
                        logging.debug("Sleep length less than 0.01 second, sleeping for 0.01 second to avoid busy loop")
                        sleep(0.01)
                    else:
                        sleep(sleep_length)
            except Exception as e:
                logging.error(f"Error in scheduler run loop: {e}")
                raise e
            
if __name__ == "__main__":
    import asyncio

    timezone = 'America/New_York'

    def output(type):
        logging.info(f"Running {type.ljust(8)} at {arrow.now().to(timezone).format('YYYY-MM-DD HH:mm:ss')}")
        
    scheduler = Scheduler(config_file='scheduler.yaml', notifier=output, timezone=timezone)
    asyncio.run(scheduler.run())
