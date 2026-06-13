# Fetcher
A newer architecture implementing my signboard services.

## The Problem(s)
Several of my internet data sources are metered (and I'm cheap). In the previous architecture, the _per data source_ microservices each fetched their individual source of data.  If I wanted to add new features, or investigate bugs (and not over-subscribe to the source), I had to 'test in prod'. Clearly this is a 'less than ideal' method. A smaller issue was the spread of secrets - with each microservice needing a secret or two (API key, token, etc.) for the metered services.

## the Solution
Consolidate the fetching of the raw data sources.  This consolidates all of the secrets to just one container, and allows deterministic scheduling of the various sources - guaranteeing one source is fetched at a time.  The new transformers (stripped down microservices) listen to the 'raw' channel, transform the raw data, and publish on the update channel. KV-Updater is run in two configurations (from a single image) - one to persist the 'raw' messages from fetcher, and one to persist 'update' messages from the trasnformers. The apiserver still subscribes to the update channel, and streams to the clients via SSE. And finally, by publishing the raw data fetched from each source, a `repeater` was possible - taking the place of the fetcher in dev and test - subscibing to the raw channel from the prod Redis, and publishing it to the raw channel of its local (dev or test) Redis - with all of the other dev or test services running as usual - oblivious to the fact that they're not running in prod!  If I want to try out something new (bug fix or new feature) in a kv-updater, transformer, apiserver, or client I can do that in dev without upsetting prod in the slightest.

## Other significant changes
- All of the components are now housed in this single repository
- All of the components share a single [Dockerfile](Dockerfile), and are all built into docker images from a single [build](builder/README.md) process that only builds the conatiners necessary based on source file change dates.
- A Helm [chart](helm/microservices/) has been created allowing a single call to deploy Redis, fetcher (or repeater), kv-updaters, trasnformers, and the apiserver
- (deprecated) All of the YAML files (deployment, service, ingress, etc.) are all linked from the components subdirectory to a central [yaml](yaml) folder