# Roadmap to Full Production-Ready Communication Fabric

## Schema (جميع ملفات CSV)

| Column | Type | Description |
|--------|------|-------------|
| `id` | string | معرف فريد: `{domain}-{NNN}` |
| `domain` | string | الطبقة/المجال |
| `category` | enum | `missing_component`, `incomplete_implementation`, `bug`, `design_flaw`, `performance`, `missing_integration`, `missing_test`, `missing_config`, `missing_docs` |
| `title` | string | عنوان قصير بالفجوة |
| `description` | text | شرح مفصل |
| `severity` | enum | `critical`, `high`, `medium`, `low` |
| `status` | enum | `open`, `in_progress`, `resolved`, `blocked` |
| `impact` | text | ماذا ينكسر أو يتأثر |
| `dependencies` | text | IDs للمهام التي يجب أن تسبق هذه |
| `effort_estimate` | enum | `XS` (<1d), `S` (1-3d), `M` (3-7d), `L` (1-3w), `XL` (3+w) |
| `proposed_solution` | text | اتجاه الحل المقترح |
| `evidence` | text | مسار ملف أو اختبار يوثق المشكلة |
| `notes` | text | ملاحظات إضافية |

## الملفات

| File | Scope |
|------|-------|
| `observability.csv` | Tracing, Metrics, Structured Logging, Health Probes |
| `testing.csv` | Unit, Integration, Test Infrastructure, CI |
| `security.csv` | TLS/mTLS, Authentication, Encryption, Secrets |
| `devops.csv` | Docker, CI/CD, Deployment, Config Mgmt |
| `transport_L4.csv` | OSI L4 Transport Layer |
| `network_L3.csv` | OSI L3 Network Layer |
| `session_L5.csv` | OSI L5 Session Layer |
| `presentation_L6.csv` | OSI L6 Presentation Layer |
| `protocols_L7.csv` | OSI L7 Protocol Handlers |
| `wiring_di.csv` | Wiring, DI, Assembler, Lifecycle |
| `gateway_sdk.csv` | Gateway Mode, RemoteAdapter, FabricService API |
