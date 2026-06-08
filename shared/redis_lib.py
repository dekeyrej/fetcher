from abc import ABC, abstractmethod
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
import os
import signal
import sys
import time

from redis import Redis

from liveness import start_liveness_probe

class RedisClient(ABC):
    def __init__(self, redis_url: str = None, prod: bool = False) -> None:
        self.client = self.connect_redis(redis_url)
        self.prod_client = None
        if prod:  # for 'repeater' which listens to prod Redis and publishes to in-cluster Redis
            prod_redis_url = self.get_prod_redis_url()
            self.prod_client = self.connect_redis(prod_redis_url)
        self.in_channel = os.getenv('IN_CHANNEL', '') # for listening, if needed (repeater, kv-updater, transformers)
        self.out_channel = os.getenv('OUT_CHANNEL', '') # for publishing, if needed (fetcher, repeater, transformers)
        self.redis_thread = None
        # Register the OS signals to trigger our shutdown method
        signal.signal(signal.SIGTERM, self.shutdown_service)
        signal.signal(signal.SIGINT,  self.shutdown_service)  # Catches Ctrl+C
        # start liveness probe if LIVENESS_PORT is set in environment variables
        start_liveness_probe()

    def get_redis_url(self) -> str:
        """
        Construct the Redis URL from environment variables.
        """
        import os
        redis_host_port_db  = os.getenv('HOST_PORT_DB', 'redis.redis:6379/0') # default to in-cluster Redis
        redis_user_pass     = os.getenv('USER_PASS', 'none:none') # default to no auth
        redis_url = f"redis://{redis_user_pass}@{redis_host_port_db}"
        logging.debug(f"Constructed Redis URL: {redis_url}")    
        return redis_url

    def get_prod_redis_url(self) -> str:
        """
        Construct the production Redis URL from environment variables.
        """
        import os
        redis_host_port_db  = os.getenv('PROD_HOST_PORT_DB', 'localhost:6379/0') # invalid default to force setting this in prod
        redis_user_pass     = os.getenv('PROD_USER_PASS', 'none:none') # default to no auth
        redis_url = f"redis://{redis_user_pass}@{redis_host_port_db}"
        logging.debug(f"Constructed Production Redis URL: {redis_url}")    
        return redis_url

    def connect_redis(self, redis_url: str = None):
        """
        Connect to Redis using the provided URL or environment variables.
        """
        if redis_url is None:
            redis_url = self.get_redis_url()

        try:
            r = Redis.from_url(redis_url, decode_responses=True)
            if not r.ping():
                raise ConnectionError(f"Could not connect to Redis at {redis_url}")
            logging.debug(f"Connected to Redis at {redis_url}")
        except Exception as e:
            logging.error(f"Error connecting to Redis: {e}")
            sys.exit(1)
        return r

    def rget(self, key: str, prod: bool = False):
        """ Get a value from Redis by key. If prod is True, use the production Redis client. """
        try:
            client = self.prod_client if prod and self.prod_client else self.client
            value = client.get(key)
            logging.debug(f"Retrieved key '{key}' with value: {value}")
            return value
        except Exception as e:
            logging.error(f"Error getting key '{key}': {e}")
            return None
        
    def rset(self, key: str, value: str, prod: bool = False):
        """ Set a value in Redis by key. If prod is True, use the production Redis client. """
        try:
            client = self.prod_client if prod and self.prod_client else self.client
            client.set(key, value)
            logging.debug(f"Set key '{key}' with value: {value}")
        except Exception as e:
            logging.error(f"Error setting key '{key}': {e}")

    def publish(self, message: str, prod: bool = False):
        """ Publish a message to the output channel. If prod is True, use the production Redis client. """
        try:
            client = self.prod_client if prod and self.prod_client else self.client
            client.publish(self.out_channel, message)
            logging.debug(f"Published message to channel '{self.out_channel}': {message}")
        except Exception as e:
            logging.error(f"Error publishing to channel '{self.out_channel}': {e}")
    
    @abstractmethod
    def message_handler(self, message) -> None:
        """
        Abstract method to handle incoming messages from Redis pub/sub.
        Must be implemented by subclasses.
        """
        pass

    def listen(self, prod: bool = False) -> None:
        """
        Main function to listen to Redis pub/sub input channel and handle messages.
        client = self.client, except for 'repeater' which listens to self.prod_client
        """
        logging.debug(f"Setting up Redis pub/sub listener on channel '{self.in_channel}'...")
        client = self.prod_client if prod and self.prod_client else self.client
        if self.in_channel:
            pubsub = client.pubsub()
            pubsub.subscribe(**{self.in_channel: self.message_handler})
            self.redis_thread = pubsub.run_in_thread(sleep_time=0.01, daemon=True)
            logging.info(f"Listening for messages on '{self.in_channel}'...")

            try:
                while True:
                    time.sleep(1)  # Keep the main thread alive while the pubsub thread is running
            except KeyboardInterrupt:
                logging.info("Stopped listening for messages.")
                if self.redis_thread:
                    self.redis_thread.stop()
            finally:
                pubsub.unsubscribe()
                pubsub.close()
                client.close()
        else:
            logging.warning("No channel specified for listening. Exiting.")
            sys.exit(1)

    def shutdown_service(self, signum, frame):
        """
        Handle shutdown signals (SIGTERM, SIGINT) to gracefully stop the service.
        """
        logging.info(f"Received signal {signum}. Shutting down {type(self).__name__}...")
        if self.redis_thread and self.redis_thread.is_alive():
            self.redis_thread.stop()
            logging.info("Stopped Redis pubsub thread.")
        self.client.close()
        if self.prod_client:
            self.prod_client.close()
        logging.info("Closed Redis connection(s).")
        sys.exit(0)