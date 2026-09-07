```mermaid
graph TD
    subgraph PROBLEM ["The Problem: Fragmented Architecture"]
        direction TB
        S1[Microservice A] -->|Secret A| API1((Data Source A))
        S2[Microservice B] -->|Secret B| API2((Data Source B))
        S3[Microservice C] -->|Secret C| API3((Data Source C))
        
        style PROBLEM fill:#fff1f0,stroke:#cf1322
        note1[Secret Sprawl & <br/>High Metered Costs] --- PROBLEM
    end

    subgraph SOLUTION ["The Solution: Consolidated Pipeline"]
        direction TB
        
        %% Security Layer
        subgraph SEC ["Zero Trust Hardening (via secretmanager)"]
            F[Fetcher]
        end

        %% Data Flow
        F -->|Single Point of Entry| APIs((External APIs))
        F -->|Consolidated Secrets| RC[Raw Channel - Redis]
        
        RC --> T[Transformers]
        T --> UC[Update Channel - Redis]
        
        UC --> API[APIServer]
        UC --> KV[KV-Updater]
        RC --> KV
        
        %% Dev/Test Loop
        R[Repeater] -.->|Mirrors Prod Raw| RC
        
        style SOLUTION fill:#f6ffed,stroke:#52c41a
        style SEC fill:#e6f7ff,stroke:#1890ff
        note2[Deterministic Scheduling & <br/>Safe Dev/Test Environment] --- SOLUTION
    end
```