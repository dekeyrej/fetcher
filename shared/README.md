# Shared packages

## Where Used

| Package      | fetcher | kv-updater | transformer | MicroService | apiserver | repeater | recorder |
|           ---|      ---|         ---|          ---|           ---|        ---|       ---|       ---|
| Scheduler    |    X    |            |             |              |           |          |          |
| MicroService |         |            |      X3     |              |           |          |          |
| RedisClient  |    X1   |     X1     |             |       X2     |     X4    |     X1   |    X1    |
| liveness     |    X1   |     X1     |             |       X2     |     X4    |     X1   |          |

X1 - fetcher, kv-updater, repeater, and recorder are subclasses of RedisClient and import liveness

X2 - Microservice is a subclass of RedisClient _and_ imports liveness

X3 - Transformer is a subclass of MicroService.  

X4 - apiserver implements both Redis client functions and a liveness probe differently to be compatible with FastAPI