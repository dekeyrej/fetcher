import asyncio
import logging
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import arrow
import httpx
import orjson

async def fetch(url: str, message: str, now: str, headers: dict=None, raw: bool=False) -> dict:
    async with httpx.AsyncClient(http2=True,) as client:
        # Prefer provided headers and request compressed response
        req_headers = headers or {}
        req_headers["Accept-Encoding"] = "br, gzip, deflate"
        # Perform a simple GET and read the full body
        try:
            response = await client.get(url, headers=req_headers)
            logging.debug(f"{message}")
            logging.debug(f"{message} - response encoding: {response.headers.get('Content-Encoding', '')}, content-type: {response.headers.get('Content-Type', '')}, status code: {response.status_code}, time: {now}")
            body = response.content
            if raw:
                return body
            return orjson.loads(body)
        except httpx.RequestError as e:
            logging.error(f"An error occurred while requesting {url}: {e}")
            return {}
    
async def aqi(url: str, timezone: str) -> dict:  # working
    tnow = arrow.now().to(timezone)
    return await fetch(url,'Fetching AQI data',tnow.format('MM/DD/YYYY hh:mm A ZZZ'))
    
async def events() -> list[dict]:   # working
    return None # events are read by the events microservice directly from the file, so we can skip fetching them here
    
async def garmin(url: str, timezone: str) -> str:  # defered
    tnow = arrow.now().to(timezone)
    return await fetch(url,'Fetching Garmin Track data',tnow.format('MM/DD/YYYY hh:mm A ZZZ'),raw=True)
    
async def github(url: str, timezone: str, headers: dict, workflowid: str) -> dict:   # defered
    tnow = arrow.now().to(timezone)
    response = {}
    response['commits'] = await fetch(f'{url}/commits','Fetching GitHub commits',tnow.format('MM/DD/YYYY hh:mm A ZZZ'),headers=headers)
    response['workflow_runs'] = await fetch(f'{url}/actions/workflows/{workflowid}/runs','Fetching GitHub workflow runs',tnow.format('MM/DD/YYYY hh:mm A ZZZ'),headers=headers)
    return response
    
async def mlb(url: str, timezone: str) -> list[dict]:  # working
    tnow = arrow.now().to(timezone)
    response = await fetch(url,'Fetching MLB games',tnow.format('MM/DD/YYYY hh:mm A ZZZ'))
    return response['events']
    
async def moon(url: str, timezone: str, headers: dict, lat_long: str) -> list[dict]:  # working
    tnow = arrow.now().to(timezone)
    today = tnow.format('[&date=]YYYY-MM-DD[&offset=]ZZ')
    tomorrow = tnow.shift(days=+1).format('[&date=]YYYY-MM-DD[&offset=]ZZ')
    responses = await asyncio.gather(
        fetch(f'{url}/sun?{lat_long}&{today}','Fetching Sun data for today',tnow.format('MM/DD/YYYY hh:mm A ZZZ'),headers=headers),
        fetch(f'{url}/sun?{lat_long}&{tomorrow}','Fetching Sun data for tomorrow',tnow.format('MM/DD/YYYY hh:mm A ZZZ'),headers=headers),
        fetch(f'{url}/moon?{lat_long}&{today}','Fetching Moon data for today',tnow.format('MM/DD/YYYY hh:mm A ZZZ'),headers=headers),
        fetch(f'{url}/moon?{lat_long}&{tomorrow}','Fetching Moon data for tomorrow',tnow.format('MM/DD/YYYY hh:mm A ZZZ'),headers=headers)
    )
    return responses
    
async def gcal(url: str, timezone: str) -> dict:  # working
    # tnow = arrow.now().to(timezone)
    tnow = arrow.now().to('America/New_York')  # Google Calendar API requires timeMin and timeMax to be in the timezone of the calendar, which is typically set to the local timezone of the user who created the calendar. For simplicity, we'll assume it's America/New_York for now, but ideally this should be configurable.
    time_min = tnow.replace(hour=6, minute=0, second=0).format("YYYY-MM-DDTHH:mm:ssZZ")
    time_max = tnow.replace(hour=20, minute=0, second=0).format("YYYY-MM-DDTHH:mm:ssZZ")
    gurl = url + f"&timeMin={time_min}&timeMax={time_max}"
    response = await fetch(gurl,'Fetching Google Calendar events',tnow.format('MM/DD/YYYY hh:mm A ZZZ'))
    return response['items']
    
async def nfl(url: str, timezone: str) -> dict:  # working (marginally)
    tnow = arrow.now().to(timezone)
    return await fetch(url,'Fetching NFL games',tnow.format('MM/DD/YYYY hh:mm A ZZZ'))
    
async def weather(url: str, timezone: str) -> dict:  # working
    tnow = arrow.now().to(timezone)
    return await fetch(url,'Fetching Weather data',tnow.format('MM/DD/YYYY hh:mm A ZZZ'))
    
async def wc(url: str, timezone: str) -> dict:
    tnow = arrow.now().to(timezone)
    response = await fetch(url,'Fetching World Cup games',tnow.format('MM/DD/YYYY hh:mm A ZZZ'))
    return response['events']

# async def dispatcher(self, type: str):
#     logging.debug(f"Dispatching fetch for type: {type}")
#     rawmessage = {
#         'type': type,
#         'updated': arrow.now().to(self.timezone).format('MM/DD/YYYY h:mm:ss A Z')
#     }
#     # update the period for MLB based on the value set by the mlb.py microservice, defaulting to 20 seconds if not set
#     self.scheduler.update_period('MLB', int(self.rget('period:MLB') or 20))
#     # update the period for NFL based on the value set by the nfl.py microservice, defaulting to 60 seconds if not set
#     self.scheduler.update_period('NFL', int(self.rget('period:NFL') or 60))
#     # update the period for World Cup based on the value set by the wc.py microservice, defaulting to 60 seconds if not set
#     self.scheduler.update_period('WorldCup', int(self.rget('period:WorldCup') or 60))
#     if type == 'AQI':
#         rawmessage['values'] = await     aqi(self.urls[type], self.timezone)
#     elif type == 'Events':
#         rawmessage['values'] = await  events()
#     elif type == 'Track':
#         rawmessage['values'] = await  garmin(self.urls[type], self.timezone)
#     elif type == 'GitHub':
#         rawmessage['values'] = await  github(self.urls[type], self.timezone, headers=self.headers['GitHub'], workflowid=self.workflowid)
#     elif type == 'MLB':
#         rawmessage['values'] = await     mlb(self.urls[type], self.timezone) 
#     elif type == 'Moon':
#         rawmessage['values'] = await    moon(self.urls[type], self.timezone, headers=self.headers['Moon'], lat_long=self.lat_long)
#     elif type == 'Calendar':
#         rawmessage['values'] = await    gcal(self.urls[type], self.timezone)
#     elif type == 'NFL':
#         rawmessage['values'] = await     nfl(self.urls[type], self.timezone)  
#     elif type == 'Weather':
#         rawmessage['values'] = await weather(self.urls[type], self.timezone)
#     elif type == 'WorldCup':
#         rawmessage['values'] = await      wc(self.urls[type], self.timezone)
#     else:
#         logging.error(f"Unknown type: {type}")

#     if self.client is not None:
#         logging.debug(orjson.dumps(rawmessage))
#         if rawmessage['values'] is None and type != 'Events':  # events are read by the events microservice directly from the file, so we can skip fetching them here
#             logging.warning(f"No data fetched for type: {type}")
#         else:
#             self.publish(orjson.dumps(rawmessage))  # publish the data to the redis 'raw' channel
#     else:
#         logging.info(orjson.dumps(rawmessage))