├───application
│   ├───.docs
│   ├───.obsolete
│   └───__pycache__
├───network
│   ├───adapters
│   │   └───__pycache__
│   ├───algorithms
│   │   └───__pycache__
│   ├───resilience
│   │   └───__pycache__
│   └───__pycache__
├───presentation
│   ├───.docs
│   ├───codecs
│   │   └───__pycache__
│   └───__pycache__
├───protocols
│   └───__pycache__
├───session
│   ├───adapters
│   │   └───__pycache__
│   ├───hooks
│   │   └───__pycache__
│   └───__pycache__
├───transport
│   ├───.obsoletes
│   ├───channel
│   │   └───__pycache__
│   ├───config
│   │   └───__pycache__
│   ├───context
│   │   └───__pycache__
│   └───__pycache__
└───wiring
    ├───adapters
    ├───config
    │   └───__pycache__
    ├───contracts
    │   └───__pycache__
    ├───factories
    │   └───__pycache__
    ├───pipelines
    │   └───__pycache__
    ├───registry
    │   └───__pycache__
    └───__pycache__



domains: 

[0.1] network
[0.2] transport
[0.3] session
[0.4] presentation
[0.5] protocols
[0.6] wiring
[0.7] application


=======================
sub domains:
[0.1.1] adapters
[0.1.2] algorithms
[0.1.3] resillience

[0.2.1] channel
[0.2.2] config
[0.2.3] context

[0.3.1] adapters
[0.3.2] hooks

[0.4.1] codecs

[0.6.1] adapters
[0.6.2] config
[0.6.3] contracts
[0.6.4] factories
[0.6.5] pipelines
[0.6.6] registries

============================
files:

# [0.1] network

[0.1.1.f] protocol.py
[0.1.2.f] __init__.py

[0.1.1.1.1.f] config_resolver.py
[0.1.1.1.2.f] dns_resolver.py
[0.1.1.1.3.f] pool_adapter.py
[0.1.1.1.4.f] router_adapter.py
[0.1.1.1.5.f] __init__.py


[0.1.1.2.1.f] least_active.py
[0.1.1.2.2.f] round_robin.py
[0.1.1.2.3.f] __init__.py


[0.1.1.3.1.f] circuit_breaker.py
[0.1.1.3.2.f] __init__.py


# [0.2] transport:


[0.2.1.f] base.py
[0.2.2.f] composite.py
[0.2.3.f] consumer_example.py
[0.2.4.f] factory.py
[0.2.5.f] inprocess.py
[0.2.6.f] retry.py
[0.2.7.f] subprocess.py
[0.2.8.f] tcp.py
[0.2.9.f] transport_example.yaml
[0.2.10.f] uds.py
[0.2.11.f] websocket.py
[0.2.12.f] _ws_framing.py
[0.2.13.f] _ws_keepalive.py
[0.2.14.f] __init__.py


[0.2.1.1.f] channel.py
[0.2.1.2.f] protocol.py
[0.2.1.3.f] types.py
[0.2.1.4.f] __init__.py

[0.2.2.1.f] transport_config.py
[0.2.2.2.f] __init__.py



[0.2.3.1.f] retry_hook.py
[0.2.3.2.f] transport_context.py
[0.2.3.3.f] __init__.py

 

# [0.3] session

[0.3.1.f] coordinator.py
[0.3.2.f] factory.py
[0.3.3.f] ICheckpointSync.py
[0.3.4.f] ISessionLifecycle.py
[0.3.5.f] protocol.py
[0.3.6.f] session_dispatcher.py
[0.3.7.f] session_registry.py
[0.3.8.f] __init__.py

[0.3.1.1.f] cli_session.py
[0.3.1.2.f] inprocess_session.py
[0.3.1.3.f] network_session.py

[0.3.2.1.f] retry_hooks.py



# [0.4] presentation


[0.4.1.f] pipeline.py
[0.4.2.f] protocol.py
[0.4.3.f] request_types.py
[0.4.4.f] __init__.py

[0.4.1.1.f] compression.py
[0.4.1.2.f] json_serializer.py
[0.4.1.3.f] sse_stream_codec.py
[0.4.1.4.f] __init__.py


# [0.5] protocols


[0.5.1.f] cli_handler.py
[0.5.2.f] error_mapper.py
[0.5.3.f] graphql_handler.py
[0.5.4.f] grpc_handler.py
[0.5.5.f] http_handler.py
[0.5.6.f] inprocess_handler.py
[0.5.7.f] local_ipc_handler.py
[0.5.8.f] protocol.py
[0.5.9.f] webhook_handler.py
[0.5.10.f] __init__.py


# [0.6] wiring

[0.6.1.f] assembler.py
[0.6.2.f] runner.py

[0.6.1.1.f] fabric_health.py

[0.6.2.1.f] loader.py
[0.6.2.2.f] transport_example.yaml

[0.6.3.1.f] communication_gateway.py


[0.6.4.1.f] network_provider.py
[0.6.4.2.f] presentation_provider.py
[0.6.4.3.f] protocol_provider.py
[0.6.4.4.f] session_provider.py
[0.6.4.5.f] transport_provider.py


[0.6.5.1.f] base.py
[0.6.5.2.f] inbound.py
[0.6.5.3.f] outbound.py
[0.6.5.4.f] __init__.py

[0.6.6.1.f] layer_registry.py
[0.6.6.2.f] pipeline_registry.py
[0.6.6.3.f] __init__.py


# [0.7] application

[0.7.1.f] fastapi_router.py
[0.7.2.f] __init__.py








============================================

Now I understand the naming convention. Let me compile all NEW components that need to be added to files.csv:

## Complete List of New Components to Add

### src Files (0.x.y.z.f format) - to be added to files.csv:

| element_number | element_name | full_path | classification |
|---------------|-------------|-----------|----------------|
| 0.1.1.6.f | periodic_health_checker.py | network/adapters/periodic_health_checker.py | Missing |
| 0.1.2.4.f | weighted_round_robin.py | network/algorithms/weighted_round_robin.py | Missing |
| 0.1.2.5.f | random_strategy.py | network/algorithms/random_strategy.py | Missing |
| 0.1.2.6.f | latency_aware_strategy.py | network/algorithms/latency_aware_strategy.py | Missing |
| 0.2.15.f | backpressure.py | transport/backpressure.py | Missing |
| 0.2.16.f | heartbeat.py | transport/heartbeat.py | Missing |
| 0.2.17.f | large_payload_handler.py | transport/large_payload_handler.py | Missing |
| 0.3.9.f | redis_registry.py | session/distributed/redis_registry.py | Missing |
| 0.4.1.5.f through 0.4.1.12.f | serializers/analyzers | presentation/codecs/ | Missing |
| 0.5.11.f through 0.5.15.f | protocol handlers/factory | protocols/ | Missing |
| 0.6.2.4.f through 0.6.2.6.f | loggers | wiring/config/ | Missing |
| 0.6.4.6.f | metrics_endpoint.py | wiring/factories/metrics_endpoint.py | Missing |
| 0.7.3.f | fabric_service.py | application/fabric_service.py | Missing |
| 0.7.4.f | remote_adapter.py | application/remote_adapter.py | Missing |
| 0.8.1.f | actors package | actors/base_actor.py | Missing |

### Non-src Files (L1.x.y.z.f format):
- Tests: L1.0.1.f through L1.0.x.f series
- Devops: L1.1.x.f series  
- Security: L1.2.x.f series (if security/ folder created)

Shall I proceed to add these new entries to files.csv, or would you like me to verify the exact count and format first?



distributed


Security/Actors (requires new domains):
Element ID	Component	Required Domain/Subdomain
0.8.1.f	actors/base_actor.py	NEW: actors/ domain needed
0.x.x	security/ components	NEW: security/ domain needed