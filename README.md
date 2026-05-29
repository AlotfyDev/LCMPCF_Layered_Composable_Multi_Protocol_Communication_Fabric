# 🌐 Layered Composable Multi-Protocol Communication Fabric

> **A contract-driven, adapter-based transport & session orchestration stack spanning OSI L3 → L7.**  
> Built for zero-downtime protocol switching, resilient session management, and clean separation between business logic and communication infrastructure.

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![Architecture](https://img.shields.io/badge/OSI-L3%E2%86%92L7-4B8BBE.svg)
![Docker Ready](https://img.shields.io/badge/docker-ready-2496ED.svg)
![K8s Compatible](https://img.shields.io/badge/k8s-ready-326CE5.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## 📑 Table of Contents
- [🚀 Quick Start](#-quick-start)
- [🏗️ Architecture & Core Principles](#-architecture--core-principles)
- [📖 Usage Patterns](#-usage-patterns)
- [🧪 Testing Strategy](#-testing-strategy)
- [🐳 Deployment & Cloud-Native Ready](#-deployment--cloud-native-ready)
- [📁 Project Structure](#-project-structure)
- [⚙️ Configuration Reference](#-configuration-reference)
- [🤝 Contributing](#-contributing)
- [📜 License](#-license)

---

## 🚀 Quick Start

### 1️⃣ Prerequisites
- Python `3.11+`
- `pip` & `venv`
- Docker & Docker Compose (for deployment/integration tests)

### 2️⃣ Install Dependencies
```bash
git clone <repository-url>
cd communication-fabric
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3️⃣ Run Locally (Embedded Mode)
```bash
# Loads config, assembles L3-L7, and starts the runtime
python -m wiring.runner
# or directly:
python examples/embedded_mode/main.py
```

### 4️⃣ Run with Docker
```bash
docker compose up -d --build
# Verify health:
curl http://localhost:8000/api/v1/ready
```

---

## 🏗️ Architecture & Core Principles

This framework implements a **Layered Composable Multi-Protocol Communication Fabric**. Instead of monolithic clients or hardcoded network stacks, it uses strict layering, contract-driven dependency inversion, and dynamic configuration.

| Principle | Implementation |
|-----------|----------------|
| **Strict Layering (L3→L7)** | Unidirectional dependency flow via `Protocol` interfaces. No cross-layer imports. |
| **Contract-Driven (DIP)** | `BaseActor` & Adapters consume only `ICommunicationGateway`. Zero infrastructure coupling. |
| **Composable & Swappable** | Change LB algorithm, compression, or protocol via YAML. Zero code changes required. |
| **Resilient & Observable** | Circuit Breakers, Session Checkpoints, Graceful Shutdown, `/live` & `/ready` K8s probes. |
| **Protocol-Agnostic** | HTTP, WebSocket, gRPC, GraphQL, Webhooks, CLI, InProcess share the same orchestration core. |

📖 **Deep Dive**: See [`ARCHITECTURE.md`](ARCHITECTURE.md) for complete layer breakdown, Mermaid diagrams, data flow, and lifecycle management.

---

## 📖 Usage Patterns

The same `BaseActor` works identically across deployment patterns. Only the `Composition Root` changes.

### 🔹 Pattern 1: Embedded (In-Process)
```python
from wiring.runner import AppRunner
from actors.base_actor import BaseActor

runner = AppRunner("config/transport_example.yaml")
await runner.start()

actor = BaseActor(gateway=runner.fabric_client, actor_id="local-agent")
result = await actor.execute_task({"action": "analyze"}, protocol="http")
```

### 🔹 Pattern 2: Gateway / Sidecar (Networked)
```python
from examples.gateway_mode.remote_adapter import RemoteGatewayAdapter
from actors.base_actor import BaseActor

adapter = RemoteGatewayAdapter(base_url="http://fabric-service:8000/api/v1")
actor = BaseActor(gateway=adapter, actor_id="remote-agent")
result = await actor.execute_task({"action": "translate"}, protocol="graphql")
```
✅ **Guarantee**: `BaseActor` code **never changes**. Swapping transport patterns = swapping the injected gateway implementation.

---

## 🧪 Testing Strategy

| Test Type | Scope | Command |
|-----------|-------|---------|
| **Unit / Isolation** | `BaseActor` + `MockGateway` (Zero network, instant) | `pytest tests/test_actor_isolation.py -v` |
| **Integration / Live** | Docker container, protocol switching, `/ready` stability | `pytest tests/test_fabric_integration.py -m integration -v` |
| **Contract Compliance** | Verifies `ICommunicationGateway` structural typing | Included in `test_actor_isolation.py` |

```bash
# Run all tests
pytest -v

# Run with coverage
pytest --cov=actors --cov=wiring --cov=network tests/
```

---

## 🐳 Deployment & Cloud-Native Ready

### Docker & Healthchecks
The `docker-compose.yml` includes production-ready probes:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/ready"]
  interval: 15s
  timeout: 5s
  retries: 3
  start_period: 30s
```

### Kubernetes Probes Mapping
| Endpoint | Purpose | K8s Probe |
|----------|---------|-----------|
| `GET /api/v1/live` | Is the async loop alive? | `livenessProbe` |
| `GET /api/v1/ready` | Are pipelines/channels registered? | `readinessProbe` |
| `GET /api/v1/health` | Full system state & metrics | Manual / Prometheus |

### Graceful Shutdown
Handles `SIGINT`/`SIGTERM` automatically:
```
Signal → AppRunner → FabricClient.close() → PipelineRegistry → LayerRegistry → SessionRegistry → ChannelPool → Clean Exit
```

---

## 📁 Project Structure

```
communication-fabric/
├── config/
│   └── transport_example.yaml          # Central configuration (L3-L7, LB, CB, TTL, Health)
├── contracts/
│   └── communication_gateway.py        # Unified consumer contract (ICommunicationGateway)
├── actors/
│   └── base_actor.py                   # Pure business logic (L8)
├── wiring/
│   ├── assembler.py                    # Composition Root & FabricClient
│   ├── runner.py                       # AppRunner, Signal Handlers, Lifecycle Manager
│   ├── registry/                       # Layer & Pipeline registries
│   └── pipelines/                      # Directional L3-L7 orchestration chains
├── network/                            # L3: Pool, Router, LB, CircuitBreaker, Adapters
├── transporters/                       # L4: Channel, Retry, Framing, TCP/WS/UDS
├── session/                            # L5: Registry, Dispatcher, Coordinator, Checkpoints
├── presentation/                       # L6: Pipeline, Serializers, Codecs, Compression
├── protocols/                          # L7: HTTP, gRPC, GraphQL, Webhook, CLI, ErrorMapper
├── adapters/                           # Edge bridges (FastAPI, Health Probes, RemoteAdapter)
├── tests/                              # Unit, Integration, conftest.py fixtures
├── examples/                           # Embedded & Gateway mode runners
├── docker-compose.yml                  # Production-ready container orchestration
├── Dockerfile                          # Multi-stage, non-root, tini-init
├── ARCHITECTURE.md                     # 📘 Detailed layer diagrams, data flow, glossary
└── README.md                           # This file
```

---

## ⚙️ Configuration Reference

Edit `config/transport_example.yaml` to control behavior at runtime:

| Section | Key | Effect |
|---------|-----|--------|
| `network.load_balancer` | `round_robin` \| `least_active` | Channel routing strategy |
| `network.circuit_breaker` | `failure_threshold`, `recovery_timeout` | Cascade failure protection |
| `presentation.pipeline` | `compression: zstd` \| `gzip` \| `none` | L6 payload compression |
| `session` | `default_ttl`, `idle_timeout`, `checkpoint_sync` | Session lifecycle & state persistence |
| `protocols` | `http.enabled`, `graphql.enabled`, etc. | Enable/disable protocol pipelines |
| `health.endpoints` | `/live`, `/ready`, `/health` paths | Override probe URLs |

🔁 **Hot-Reload**: Set `fabric.config_reload_watch: true` to apply changes without restarting (WIP in v1.1).

---

## 🤝 Contributing

1. Fork & create a feature branch (`git checkout -b feat/your-idea`)
2. Ensure strict layer boundaries: no `import transporters` inside `protocols/`, etc.
3. Add tests for new contracts or adapters (`pytest -m integration` for networked features)
4. Run lint & format: `black . && flake8 . && mypy .`
5. Submit PR with architectural justification if modifying L3-L7 contracts

---

## 📜 License

MIT © [Your Name/Org]  
Built following **OSI Layering**, **Clean Architecture**, and **Cloud-Native Resilience** patterns.  
Designed for zero-downtime protocol switching, resilient session management, and clean separation between business logic and communication infrastructure.

---

> 💡 **Need help?** Open an issue, check `ARCHITECTURE.md` for deep dives, or run `python -m examples.embedded_mode.main` for a live demo.  
> 🚀 **Ready to deploy?** `docker compose up -d` and point your K8s `readinessProbe` to `/api/v1/ready`.