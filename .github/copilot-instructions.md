# Copilot Instructions — backend-notification-service

Microservicio Django de notificaciones extraído del monorepo `SistemaTickets`.
Puerto externo: `8001`. API base: `http://localhost:8001/api/notifications/`.

## Architecture (DDD Pragmático — already implemented)

```
domain/         ← Python puro. Zero Django imports. Entities, events, exceptions, repository ABC.
application/    ← Use cases + Commands (dataclasses). Orchestrate domain, no ORM.
infrastructure/ ← DjangoNotificationRepository, RabbitMQEventPublisher.
api.py          ← Thin ViewSet. Delegates 100% to use cases. No business logic.
models.py       ← ORM only. Infrastructure layer. Never import from domain.
messaging/consumer.py ← Standalone process. Dispatches to use cases or ORM fallback.
```

Dependency rule (strict): `domain ← application ← infrastructure ← presentation`

## Critical Asymmetry (current state)

`ticket.response_added` → `_handle_response_added()` → `CreateNotificationFromResponseUseCase` ✅ DDD  
All other events → `_handle_ticket_created()` → `Notification.objects.create()` ⚠️ ORM direct (DT-01, DT-07, DT-08)

Adding a new event handler means creating a Use Case + Command, not touching the ORM in the consumer.

## API Contract

Serializer exposes exactly **5 fields**: `id`, `ticket_id` (string), `message`, `read`, `sent_at`.  
`user_id` and `response_id` exist in `models.py` but are **intentionally excluded** from `serializers.py` — internal fields only.

`ticket_id` arrives as `int` from RabbitMQ → stored/exposed as `str` via `CharField`. Always `str(ticket_id)`.

## Event Contracts (RabbitMQ, fanout exchange)

| Event | Required fields | Handler |
|---|---|---|
| `ticket.created` | `ticket_id`, `title`, `user_id`, `status`, `timestamp` | `_handle_ticket_created` (ORM) |
| `ticket.response_added` | `ticket_id`, `response_id`, `admin_id`, `response_text`, `user_id`, `timestamp` | Use Case |
| `ticket.status_changed` | `ticket_id`, `old_status`, `new_status`, `timestamp` — **no `user_id`** | `_handle_ticket_created` (ORM) — DT-09 blocked |
| `ticket.priority_changed` | TBD | `_handle_ticket_created` (ORM) — DT-07/08 pending |

`InvalidEventSchema` → `basic_nack(requeue=False)` → Dead Letter Queue (`{queue}.dlq`).

## Use Case Pattern

```python
# 1. Command (dataclass in application/use_cases.py)
@dataclass
class CreateNotificationFromResponseCommand:
    ticket_id: Any; response_id: Optional[int]; user_id: Any; ...

# 2. Use Case (takes repository + optional event_publisher via __init__)
class CreateNotificationFromResponseUseCase:
    def __init__(self, repository: NotificationRepository): ...
    def execute(self, command: ...) -> Notification: ...

# 3. ViewSet wires DI in __init__, never in request handlers
self.repository = DjangoNotificationRepository()
self.mark_as_read_use_case = MarkNotificationAsReadUseCase(repository=..., event_publisher=...)
```

## Developer Workflows

```bash
# Tests (uses notification_service.test_settings — not settings.py)
pytest

# Run with coverage
pytest --cov=notifications --cov-report=term-missing

# Start consumer (standalone process, separate from Django)
python -m notifications.messaging.consumer

# Migrations
python manage.py migrate
```

## Key Files

- [`notifications/domain/entities.py`](../notifications/domain/entities.py) — `Notification` entity + `mark_as_read()` idempotency logic
- [`notifications/domain/exceptions.py`](../notifications/domain/exceptions.py) — `NotificationNotFound`, `InvalidEventSchema`, `NotificationAlreadyRead`
- [`notifications/application/use_cases.py`](../notifications/application/use_cases.py) — all commands and use cases
- [`notifications/messaging/consumer.py`](../notifications/messaging/consumer.py) — RabbitMQ dispatcher + DLQ setup
- [`notification_service/test_settings.py`](../notification_service/test_settings.py) — test DB (SQLite in-memory)
- [`ARCHITECTURE.md`](../ARCHITECTURE.md) — full contracts, DT-01 to DT-09, API docs
