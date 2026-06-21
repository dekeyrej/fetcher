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
    def __init__(self, config_file: str = "scheduler.yaml", notifier=lambda type: print(f"Running {type}")):
        self.notifier = notifier
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
            print(f"{type.ljust(8)}: {time.format('YYYY-MM-DD HH:mm:ss')}")

    ## ToDo: 
    def update_period(self, type: str, period: int):
        ''' Update the period for a given task type in the configuration. (used for MLB, NFL, and WorldCup in the current implementation) '''
        if self.config[type]['period'] != period:
            logging.debug(f"Updating period for {type} from {self.config[type]['period']} to {period} seconds")
            if period < 20:
                logging.warning(f"Period for {type} is less than 20 seconds. This may cause issues with scheduling and task execution.")
                period = 20  # set a minimum period of 20 seconds to avoid scheduling issues and task execution overlaps
            self.config[type]['period'] = period
            self.schedule_next_run(type, Reschedule=True)  # reschedule the next run for this task type with the new period
            logging.info(f"Updated period for {type} to {period} seconds and rescheduled next run for {self.config[type]['next_run_time']}(UTC)")
    
    def schedule_next_run(self, type: str, now: arrow.Arrow = None, Reschedule: bool = False):
        now = now or arrow.now().to('UTC')
        slot = self.config[type]['slot']
        period = self.config[type]['period']

        if Reschedule:
            # remove any existing scheduled run for this task type from the queue and reschedule it with the new period
            self.queue = [item for item in self.queue if item[0] != type]  # remove any existing scheduled run for this task type from the queue
        
        if self.config[type].get('next_run_time', None) is None:
            if now.second < slot:
                now = now.replace(second=slot, microsecond=0)
            elif now.second < slot + period and period < 60:
                now = now.replace(second=slot + period, microsecond=0)
            elif now.second < slot + 2 * period and period < 30:
                now = now.replace(second=slot + 2 * period, microsecond=0)
            elif now.second > slot:
                now = now.shift(minutes=+1)
                now = now.replace(second=slot, microsecond=0)
        else:
            now = now.shift(seconds=+period)
        logging.info(f"Scheduling next run for {type} at {self.now_str(now, local=True)} (in {period} seconds)")
        self.queue.append((type, now))
        self.queue.sort(key=lambda x: x[1].timestamp())  # sort the queue by next run time
        self.config[type]['next_run_time'] = self.now_str(now)
    
    def now_str(self, t: arrow.Arrow, local: bool = False) -> str:
        if local:
            return t.to('America/New_York').format('YYYY-MM-DD HH:mm:ss')
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
                        logging.info(f"Running scheduled task for {type} at {self.now_str(now, local=True)}")
                        await self.notifier(type)           # fire the scheduled task
                        self.queue.pop(0)                   # remove the task from the queue (doing this after scheduling the next run, when the next run is MLB can result in no MLB events scheduled)
                        self.schedule_next_run(type, now)   # schedule the next run for this task type
                    sleep_length = self.queue[0][1].timestamp() - arrow.now().to('UTC').timestamp()
                    logging.debug(f"Sleeping for {sleep_length:.2f} seconds")
                    if sleep_length < 0.01:
                        logging.debug("Sleep length less than 0.01 second, sleeping for 0.01 second to avoid busy loop")
                        sleep(0.01)
                    else:
                        sleep(sleep_length)
                else:
                    logging.info("No scheduled runs. Sleeping for 30 seconds.")
                    sleep(30)
                # Check if any type doesn't have a next_run_time in the config (e.g. if it was just added to the config file) and schedule it if so
                for type in self.config.keys():
                    if self.config[type].get('next_run_time', None) is None:
                        logging.error(f"Task type '{type}' is missing 'next_run_time' in the config. This shouldn't happen because the scheduler should schedule the next run for any task type that doesn't have a next_run_time, but just in case, scheduling next run for {type}.")
                        # logging.info(f"Scheduling next run for {type} as it was just added to the config file")
                        # self.schedule_next_run(type)
            except Exception as e:
                logging.error(f"Error in scheduler run loop: {e}")
                raise e
            
if __name__ == "__main__":
    import asyncio

    def output(type):
        logging.info(f"Running {type.ljust(8)} at {arrow.now().to('UTC').format('YYYY-MM-DD HH:mm:ss')}")
        
    scheduler = Scheduler(config_file='scheduler.yaml', notifier=output)
    asyncio.run(scheduler.run())
