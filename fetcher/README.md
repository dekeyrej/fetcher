# Fetcher

A deterministically scheduled fetcher of contents from URLs

## Purpose

To responsibly support a complete micorservice development lifecycle - Dev, Test, and Prod from a bandwidth perspective.

## Concept

To gather content from various URLs - several of which require API keys, some of which are rate limited, and all of which should be dealt with responsibly (from a bandwidth perspective).  The contents are published to Redis (Prod).  Each of the Lifecycle environments (Dev, Test, Prod) can then retrieve the contents from Redis (Prod), and process them independently - without overburdening the sources. 

### Queue

Central to Fetcher is a time-ordered queue and an async function 'Dispatcher' that handles the next event from the queue for processing. At start-up, the scheduler (see below) is called to schedule the first retrieval for each URL based on the configuration (read from a Kubernetes ConfigMap).

### Dispatcher

When called for an event from the queue, Dispatcher calls Retriever, Publisher, and finally Scheduler - then sleeps until the time next scheduled event is due to fire

### Retriever

In this implementation, only Fetcher requires access to the user's API keys (secrets), so Fetcher reads those secrets (precise mechanism to be determined) from the local HashiCorp vault, uses thos values to construct the URLs/headers necessary and uses Requests to retrieve the contents

### Publisher

The raw content fanout is implemented by the 'Fetcher' microservice PUBLISHing the retreived contents on a Redis PubSub channel to the local Redis instance (intended to be Prod). A 'Repeater' microservice in the other environments (Dev and Test) SUBSCRIBE to the updates, and then rePUBLISH them to their own local Redis instances.

### Scheduler

To even out load on the inbound connection, the various URLs to be fetched are intentionally scheduled to occur a various second-resolution offsets from the 'top of the minute', and periods (expressed in seconds).  These scheduled events are added to the ordered queue.

## Completing the 'Cache'

As described, Dev and Test are 100% dependent on the source Fetcher - potentially leaving them beggared for up to 60 minutes before seeing a raw message of a particular type.  To overcome this, Redis is also used as a KV store.  A separate process 'KV-Updater' also SUBSCRIBEs to the raw messages on it's local Redis instance, and writes the contents back to Redis' KV store - this provides access to all of the latest raw contents _at startup_ to the Repeaters in the other environments.

| component | Redis user/role | Secret(s) |
|---|---|---|
| Fetcher | redis-`<env>`-publish | URL API keys |
| Repeater | redis-all-subscribe-read, redis-`<env>`-publish | none |
| KV-updater (both flavors) | redis-`<env>`-subscribe-write | none |
| Transformers | redis-`<env>`-subscribe-publish | none |
| API server | redis-all-subscribe-read | none |

## Secrets
Fetcher requires access to API keys, tokens etc. necessary to construct URLs and/or request headers.  Access to these scerets is via secretmanager [github](https://github.com/dekeyrej/secretmanager) or [pypi](https://pypi.org/project/dekeyrej-secretmanager/). As a result a `secretcfg.yaml` and a `secretdef.yaml` are required to be present, and constructed to point to your actual secrets.  In my environment, the two configuration files are loaded to the cluster as configMaps [1](../yaml/secretcfg.yaml), [2](../yaml/secretdef.yaml), and mounted from the configMpas in the fetcher container via it's [deployment yaml](../fetcher/yaml/fetcher-deployment.yaml).
