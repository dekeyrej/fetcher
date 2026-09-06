# Agents Guide: Fetcher

## Architecture
Monorepo of Python microservices communicating via Redis channels (`raw` and `update`).
- **fetcher**: Fetches raw data from sources $\rightarrow$ `raw` channel.
- **transformers**: `raw` channel $\rightarrow$ transform $\rightarrow$ `update` channel.
- **kv-updater**: Persists `raw` and `update` messages.
- **apiserver**: `update` channel $\rightarrow$ SSE to clients.
- **repeater**: Dev tool; `raw` (prod Redis) $\rightarrow$ `raw` (local Redis).
- **recorder**: Logs messages of specific types.
- **shared/**: Common logic (Redis client, liveness, scheduler) used across services.

## Build & Deployment
- **Build Process**: Uses a custom "smart builder" in `builder/`.
  - Command: `python builder/builder.py` (inferred from `builder.py`).
  - Logic: Determines which images to rebuild based on modified files and reverse dependencies.
  - Dockerfile: Single shared `Dockerfile` at root.
- **Deployment**: Managed via Helm chart in `helm/microservices/`.

## Development Tips
- **Local Testing**: Use `repeater` to mirror production raw data to a local Redis instance for deterministic testing of transformers or the apiserver without hitting metered APIs.
- **Service Structure**: Most services are subclasses of `shared.redis_lib.RedisClient` or `shared.transformer.Transformer`.
- **Environment**: Check `fetcher/secretcfg.json` and `fetcher/secretdef.json` for secret definitions.
