# Fetcher
A newer architecture implementing my signboard services.

## The Problem(s)
Several of my internet data sources are metered (and I'm cheap). In the previous architecture, the _per data source_ microservices each fetched their individual source of data.  If I wanted to add new features, or investigate bugs (and not over-subscribe to the source), I had to 'test in prod'. Clearly this is a 'less than ideal' method. Another issue this architecture addressed was the spread of secrets - with each microservice needing a secret or two (API key, token, etc.) for the metered services.

## the Solution
Consolidate the fetching of the raw data sources.  This consolidates all of the secrets to just one container, and allows deterministic scheduling of the various sources - guaranteeing one source is fetched at a time.  The new transformers (stripped down microservices) listen to the 'raw' channel, transform the raw data, and publish on the update channel. KV-Updater is run in two configurations (from a single image) - one to persist the 'raw' messages from fetcher, and one to persist 'update' messages from the transformers. The apiserver still subscribes to the update channel, and streams to the clients via SSE. And finally, by publishing the raw data fetched from each source, a `repeater` was possible - taking the place of the fetcher in dev and test - subscibing to the raw channel from the prod Redis, and publishing it to the raw channel of its local (dev or test) Redis - with all of the other services running as usual in dev or test - oblivious to the fact that they're not running in prod!  If I want to try out something new (bug fix or new feature) in a kv-updater, transformer, apiserver, or client I can do that in dev without upsetting prod in the slightest.

### Event trace

```mermaid
sequenceDiagram
    participant Int as Internet
    participant F as Fetcher (Prod)
    participant RP as Redis (Prod)
    participant KV_R as KV-Update (Raw)
    participant T as Transform
    participant KV_U as KV-Update (Update)
    participant API as APIServer
    participant C as Clients

    Note over Int, C: Prod Cluster Flow
    Int->>F: GET
    F->>RP: pub (raw)
    RP-->>KV_R: sub(1)
    RP-->>T: sub(1)
    T->>RP: pub (update)
    RP-->>KV_U: sub(1)
    RP-->>API: sub(1)
    API->>C: SSE

    Note over RP, API: Persistence Loops
    KV_R->>RP: set
    KV_U->>RP: set

    Note over RP, C: Dev/Test Cluster Flow
    participant Rep as Repeater (Dev/Test)
    participant RD as Redis (Dev/Test)
    
    RP-->>Rep: sub(1) (Mirror Prod Raw)
    Rep->>RD: pub (raw)
    RD-->>T: sub(1) (Dev Transform)
    T->>RD: pub (update)
    RD-->>API: sub(1) (Dev API)
    API->>C: SSE
```


### 🔐 Secret Hardening & Zero Trust
While consolidating fetching into a single container reduces "secret sprawl", it creates a high-value target. To mitigate this, this project is designed to be paired with the secretmanager blueprint to move from simple consolidation to a Zero Trust security model.

By integrating the secretmanager framework, the fetcher achieves the following:

- Eliminating "Secret Zero": Instead of relying on static environment variables or mounted volumes which can be leaked, the system leverages HashiCorp Vault to bootstrap secrets without ever exposing a standing credential.
- Encryption-as-a-Service: Secrets are not stored in plain text within Kubernetes. They are stored as Vault-encrypted ciphertext (AES-256) and are only decrypted in memory during the container's init routine.
- Ephemeral Lifecycles: To minimize the window of exposure, decrypted secrets exist only as ephemeral Python objects and are never written to disk.
- Eternal Security via Rotation: The security posture is maintained automatically using recryptonator.py, which can be run as a Kubernetes CronJob to rotate Vault Transit keys and re-encrypt the secret store periodically (monthly in my usage).

## Other significant changes
- All of the components are now housed in this single repository
- All of the components share a single [Dockerfile](Dockerfile), and are all built into docker images from a single [build](builder/README.md) process that only builds the conatiners necessary based on source file change dates.
- I've added a simple [recorder](recorder) to logs messages of a given type, from either `raw` or `update` to support development/troubleshooting (a WorldCup transformer most recently)
- A Helm [chart](helm/microservices/) has been created allowing a single call to deploy Redis, fetcher (or repeater), kv-updaters, trasnformers, and the apiserver
- (deprecated) All of the YAML files (deployment, service, ingress, etc.) are all linked from the components subdirectory to a central [yaml](yaml) folder

## Python Classes

```mermaid
classDiagram
    class RedisClient <<abstract>> {
        -client Redis.client
        -in_channel str
        -out_channel str
        -redis_thread thread
        -redis_liveness_server HTTPServer
        -redis_liveness_thread thread
        _get_redis_url() str
        _get_prod_redis_url() str
        connect_redis(redis_url: str = None)
        +rget(key, prod: bool = False)
        +rset(key, value, prod: bool = False)
        +publish(message, prod: bool = False)
        +listen(channel, prod: bool = False)
        message_handler(message)*
        _shutdown_service(signum)
    }
    class HealthHandler {
        do_GET()
    }
    RedisClient *-- HealthHandler
    class Redis {
        client
    }
    RedisClient *-- Redis
    class Fetcher {
        secrets dict
        timezone str
        urls dict
        headers dict
        scheduler Scheduler
        client RedisClient
        lat_long str
        read_secrets() dict
        build_urls() dict
        build_headers() dict
        message_handler(message) %% Actually unused, but must be overridden
        update_period(type, period)
        dispatcher(type)
        fetch(url: str, message: str, now: str, headers: dict = None, raw: bool = False)
        aqi(url: str, timezone: str) dict
        events() list[dict]
        gcal(url: str, timezone: str) dict
        mlb(url: str, timezone: str) list[dict]
        moon(url: str, timezone: str, headers: dict, lat_long: str) list[dict]
        nfl(url: str, timezone: str) dict
        weather(url: str, timezone: str) dict
        run()
    }
    Fetcher ..|> RedisClient
    class SecretManager {
        SOURCES set
        k8s_client
        hvac_client
        config dict
        registry VerbRegistry
        ~__init__(config: dict = None)
        +configure_secret_type(config)
        +execute(backend, verb)
    }
    Fetcher *-- SecretManager
    class _kubevault_ops {
        init_kubevault(manager: SecretManager)
        reauthenticate_vault_via_kubernetes(manager: SecretManager) bool
        read_encrypted_secrets(manager: SecretManager, secret_def: dict) dict
        create_encrypted_secret(manager: SecretManager, secret_def: dict, data: str) dict
        rotate_vault_key(manager: SecretManager, transit_key: str) dict
        logout_kubevault(manager: SecretManager) dict
    }
    SecretManager *-- _kubevault_ops
    class _k8s_ops {
        connect_to_k8s(manager: SecretManager) client.CoreV1Api
        _get_k8s_service_account_token(k8s_client, service_account, namespace) jwt
        create_k8s_secret(manager: SecretManager, secret_def: dict, data) dict
        read_k8s_secret(manager: SecretManager, secret_def: dict)
        logout_k8s(manager: SecretManager) dict
    }
    _kubevault_ops *-- _k8s_ops
    class _vault_ops {
        connect_to_vault(url, verify: bool = True) hvac_client
        _authenticate_vault_via_kubernetes(hvac_client, role, jwt)
        encrypt_data_with_vault(hvac_client, transit_key, data)
        decrypt_data_with_vault(hvac_client, transit_key, data)
        _rotate_vault_key(hvac_client, transit_key)
        logout_vault(hvac_client)
    }
    _kubevault_ops *-- _vault_ops
    class VerbRegistry {
        VERBS set
        ~__init__(SECRET_VERB_REGISTRY)
        get_handler(source, verb) callable
        list_sources() list
        list_verbs(source) list
        validate()
        perform(backend, verb)
        safe_get_handler(backend, verb)
    }
    SecretManager *-- VerbRegistry
    class Scheduler {
        notifier callable
        timezone str
        config dict
        queue list
        configured_types() list
        dump_queue()
        set_period(type: str, period: int)
        schedule_next_run(type, now, Reschedule)
        now_str(t: arrow, local: bool = False)
        run()
    }
    Fetcher *-- Scheduler
    %% class Repeater {
    %%     client RedisClient
    %%     prod_client RedisClient
    %% }
    %% Repeater ..|> RedisClient
    class KV-Updater {
        client RedisClient
        message_handler(message)
    }
    KV-Updater ..|> RedisClient
    %% class Recorder {
    %%     client RedisClient
    %%     message_handler(message)
    %% }
    %% Recorder ..|> RedisClient
    class Transformer {
        client RedisClient
        type str
        timezone str
        message_handler(message)
        update(data)*
        run()
    }
    Transformer ..|> RedisClient
    class Events {
        type str = 'Events'
        update(data)
    }
    Events <|-- Transformer
    class CalendarServer {
        type str = 'Calendar'
        update(data)
    }
    CalendarServer <|-- Transformer
    class AQI {
        type str = 'AQI'
        AQIData dict
        update(data)
        _convert_reading(value, pollutant)
        _scaled_reading(value, pollutant)
    }
    AQI <|-- Transformer
    class Moon {
        type str = 'Moon'
        update(data)
        _moon_condition(moonphase float)
        _sun_event(mnd list, tstmp) str
        _moon_event(mnd list) str
        _age_to_illum(age int) float
        _parse_time(timestr str) arrow
        _ts2hhmm(tstmp) str
    }
    Moon <|-- Transformer
    class Weather {
        type str = 'Weather'
        dirs list
        update(data)
        _to_nwid(icon,wid)
        _deg_to_dir(degrees)
    }
    Weather <|-- Transformer
    class MLB {
        type str = 'MLB'
        update(data)
        _load_game(game)
        _team_values_and_scores(competition)
    }
    MLB <|-- Transformer
    class NFL {
        type str = 'NFL'
        update(data)
        _read_event(event)
    }
    NFL <|-- Transformer
```