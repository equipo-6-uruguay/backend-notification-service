# Plan de Pruebas y Gestión de Riesgos — Notification Service v3.0

**Proyecto:** Backend Notification Service (Microservicio de Notificaciones)  
**Versión del Plan:** 3.0  
**Fecha:** 26 de Febrero de 2026  
**Autor:** Equipo de QA — Equipo 6 Uruguay  

---

## Tabla de Contenidos

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Alcance y Objetivos](#2-alcance-y-objetivos)
3. [Niveles de Prueba](#3-niveles-de-prueba)
4. [Estrategia de Calidad](#4-estrategia-de-calidad)
5. [Herramientas y Entorno](#5-herramientas-y-entorno)
6. [Calendario de Pruebas](#6-calendario-de-pruebas)
7. [Gestión de Riesgos](#7-gestión-de-riesgos)
8. [Criterios de Entrada y Salida](#8-criterios-de-entrada-y-salida)
9. [Roles y Responsabilidades](#9-roles-y-responsabilidades)
10. [Entregables](#10-entregables)
11. [Métricas de Calidad](#11-métricas-de-calidad)
12. [Referencias ISTQB](#12-referencias-istqb)
13. [Diseño de Casos de Prueba — Actividad 3.2](#13-diseño-de-casos-de-prueba--actividad-32)

---

## 1. Resumen Ejecutivo

Este documento establece el **Plan de Pruebas y Gestión de Riesgos** para el microservicio Backend Notification Service, desarrollado con arquitectura Domain-Driven Design (DDD) y Event-Driven Architecture (EDA) sobre Django 6.0.2.

El notification-service es un **microservicio consumidor**: no expone creación de recursos por HTTP. Las notificaciones se generan **exclusivamente** mediante eventos de dominio provenientes de RabbitMQ (eventos `ticket.created`, `ticket.response_added`, `ticket.status_changed`, `ticket.priority_changed`). La API REST expone operaciones de lectura, marcado como leída y eliminación.

### Objetivos Principales

- **Garantizar la calidad** de los endpoints REST de la API de notificaciones
- **Validar la integridad** de la arquitectura DDD (Domain → Application → Infrastructure)
- **Verificar la resiliencia** del consumer RabbitMQ (reconexión, DLQ, idempotencia)
- **Asegurar el streaming SSE** en tiempo real con aislamiento por usuario
- **Identificar y mitigar riesgos** técnicos y funcionales del proyecto

### Contexto Técnico

| Aspecto | Detalle |
|---------|---------|
| **Framework** | Django 6.0.2 + Django REST Framework 3.15.2 |
| **Lenguaje** | Python 3.12 |
| **Arquitectura** | DDD Pragmático + EDA |
| **Base de Datos** | PostgreSQL 15 (producción), SQLite in-memory (tests) |
| **Message Broker** | RabbitMQ 3 (exchange fanout) |
| **Streaming** | Server-Sent Events (SSE) por usuario |
| **Contenedores** | Docker / docker-compose (4 servicios) |
| **CI/CD** | GitHub Actions (66 tests, 89.50% cobertura) |

### Estado Actual de Pruebas

| Métrica | Valor |
|---------|-------|
| **Tests totales** | 66 |
| **Cobertura de código** | 89.50% |
| **Umbral mínimo CI** | 70% |
| **Archivos de test** | 8 |
| **Resultado última ejecución** | 66/66 passing ✅ |

---

## 2. Alcance y Objetivos

### 2.1 Alcance de las Pruebas

#### ✅ Incluido en el Alcance

**Funcional:**
- **Consulta de notificaciones:** `GET /api/notifications/` y `GET /api/notifications/{id}/`
- **Marcado como leída:** `PATCH /api/notifications/{id}/read/` con reglas de dominio (idempotencia)
- **Eliminación individual:** `DELETE /api/notifications/{id}/`
- **Eliminación masiva:** `DELETE /api/notifications/clear/`
- **Bloqueo de POST/PUT/PATCH base:** Retornar `405 Method Not Allowed` (DDD: creación solo por eventos)
- **Consumer RabbitMQ:** Dispatch de eventos `ticket.created`, `ticket.response_added`, `ticket.status_changed`, `ticket.priority_changed`
- **Idempotencia por `response_id`:** No duplicar notificaciones para la misma respuesta (EP22)
- **Validación de schema:** Rechazar eventos mal formados con `InvalidEventSchema` (EP21)
- **Streaming SSE:** Endpoint `GET /api/notifications/sse/{user_id}/` con heartbeat y filtrado por usuario

**No Funcional:**
- **Resiliencia:** Reconexión automática del consumer con backoff exponencial
- **Dead Letter Queue (DLQ):** Mensajes rechazados enrutados a DLQ para inspección
- **Performance:** Tiempo de respuesta < 200ms (p95) para operaciones REST
- **Disponibilidad:** Error handling genérico (500 JSON, nunca stack traces)

**Arquitectura:**
- **Independencia de dominio:** Entidades `Notification` y excepciones libres de framework Django
- **Inversión de dependencias:** `NotificationRepository` como ABC, implementado por `DjangoNotificationRepository`
- **Separación de responsabilidades:** ViewSet thin → Use Case → Entity → Repository
- **Eventos de dominio:** `NotificationMarkedAsRead` generado al marcar como leída

#### ❌ Excluido del Alcance

- Frontend (repositorio separado)
- Ticket-service (microservicio productor de eventos — repositorio separado)
- Auth-service (autenticación JWT — dependencia externa)
- Pruebas de carga extrema (> 100 usuarios concurrentes)
- Auditoría de infraestructura cloud (servidores, DNS, SSL)

### 2.2 Objetivos de Calidad

1. **Cobertura de Código:** ≥ 85% en líneas ejecutadas (actual: 89.50%)
2. **Defectos Críticos:** 0 defectos críticos en producción
3. **Regresión:** 100% de tests pasando antes de cada merge a `develop`
4. **Documentación:** Todos los casos de prueba documentados y reproducibles
5. **Automatización:** ≥ 95% de pruebas funcionales automatizadas

---

## 3. Niveles de Prueba

Siguiendo la pirámide de pruebas (ISTQB Foundation §2.2), se definen tres niveles con prioridades diferenciadas:

### 3.1 Pruebas Unitarias (Base de la Pirámide)

**Objetivo:** Verificar componentes aislados sin dependencias de framework ni base de datos.

**Alcance:**

- **Domain Layer** (`notifications/domain/`):
  - `Notification` entity: `mark_as_read()` cambia estado, genera evento `NotificationMarkedAsRead`, idempotencia (llamar dos veces no genera segundo evento)
  - `collect_domain_events()`: recolecta y limpia la lista interna de eventos
  - Domain events: inmutabilidad (`frozen=True`), estructura correcta
  - Domain exceptions: `NotificationAlreadyRead`, `NotificationNotFound`, `InvalidEventSchema` con campos descriptivos

- **Application Layer** (`notifications/application/`):
  - `MarkNotificationAsReadUseCase`: orquesta find → mark_as_read → save → publish (con mocks)
  - `CreateNotificationFromResponseUseCase`: validación de schema (EP21), idempotencia por `response_id` (EP22), creación de entidad con mensaje formateado
  - `CreateNotificationFromTicketCreatedUseCase` (⏳ **PENDIENTE — DT-01**): `_handle_ticket_created` en el consumer accede al ORM directamente, violando la regla arquitectónica R3. Use Case + Command + tests unitarios pendientes de implementación antes de que esta deuda técnica sea saldada.
  - Command objects: `MarkNotificationAsReadCommand`, `CreateNotificationFromResponseCommand`

- **Consumer Dispatch** (`notifications/messaging/`):
  - Dispatch de `ticket.response_added` → `CreateNotificationFromResponseUseCase`
  - Backward-compatibility de `ticket.created` → creación directa ORM
  - ACK del mensaje en ambos flujos
  - Error handling: `InvalidEventSchema` → ACK + log (no enviar a DLQ)

**Archivos de test:**
| Archivo | Tests | Descripción |
|---------|-------|-------------|
| `test_domain.py` | 5 | Entidad `Notification`, eventos de dominio |
| `test_use_cases.py` | 3 | `MarkNotificationAsReadUseCase` con mocks |
| `test_response_handler.py` | 9 | `CreateNotificationFromResponseUseCase`: schema, idempotencia, user_id, response_id |
| `test_consumer_dispatch.py` | 4 | Dispatch del callback del consumer |
| ⏳ `test_ticket_created_use_case.py` | 0 (pendiente) | **DT-01:** `CreateNotificationFromTicketCreatedUseCase` — creación, idempotencia, message format |

**Herramientas:**
- pytest 8.3.4 (runner)
- unittest.mock (mocking de repositorios y publishers)
- pytest-cov 5.0.0

**Comando:**
```bash
pytest notifications/tests/test_domain.py notifications/tests/test_use_cases.py notifications/tests/test_response_handler.py notifications/tests/test_consumer_dispatch.py -v --cov=notifications/domain --cov=notifications/application
```

**Criterio de Éxito:** ≥ 90% cobertura en domain + application layers, 0 fallos.

---

### 3.2 Pruebas de Integración (Nivel Medio)

**Objetivo:** Validar la interacción entre capas (Infrastructure → Domain, ViewSet → Use Case → Repository).

**Alcance:**

- **Infrastructure Layer** (`notifications/infrastructure/`):
  - `DjangoNotificationRepository`: mapeo bidireccional ORM ↔ Domain Entity
  - `save()`: crear nueva (id=None → asigna ID) y actualizar existente
  - `find_by_id()`: retorna entidad de dominio o `None`
  - `find_all()`: retorna lista de entidades de dominio
  - `find_by_response_id()`: búsqueda para idempotencia (EP22)
  - `to_django_model()`: conversión correcta de campos (`user_id`, `response_id`)

- **ViewSet Layer** (`notifications/api.py`):
  - `read()` → 200 OK + recurso serializado (notificación marcada como leída)
  - `read()` → 404 Not Found (notificación inexistente)
  - `create/update/partial_update` → 405 Method Not Allowed
  - `destroy()` → 204 No Content / 404 / 500
  - `clear_all()` → 204 No Content / 500

- **RabbitMQ Integration** (`notifications/messaging/`):
  - Consumer `callback()` crea notificación al recibir mensaje de la cola
  - Publish + consume + verify DB vía ORM

- **SSE Endpoint** (`notifications/infrastructure/sse_view.py`):
  - `GET /api/notifications/sse/{user_id}/` → 200 + `text/event-stream`
  - StreamingHttpResponse con heartbeat `:heartbeat`
  - Filtrado estricto: solo notificaciones del `user_id` solicitado
  - Formato SSE correcto: `event: notification\ndata: {json}\n\n`
  - Payload incluye `response_id` para identificación en frontend

**Archivos de test:**
| Archivo | Tests | Descripción |
|---------|-------|-------------|
| `test_infrastructure.py` | 10 | `DjangoNotificationRepository` con SQLite in-memory |
| `test_views.py` | 2 | ViewSet: read 200 OK, read 404 |
| `test_integration.py` | 2 | Consumer + RabbitMQ real, modelo Django |
| `test_sse_endpoint.py` | 8 | SSE: conectividad, filtrado, formato, heartbeat, response_id |

**Herramientas:**
- Django TestCase / TransactionTestCase (SQLite in-memory)
- DRF APIRequestFactory
- RabbitMQ service container (CI) / localhost (desarrollo)
- `itertools.islice` para consumir chunks de streaming sin bloqueo infinito

**Comando:**
```bash
pytest notifications/tests/test_infrastructure.py notifications/tests/test_views.py notifications/tests/test_integration.py notifications/tests/test_sse_endpoint.py -v --cov=notifications/infrastructure --cov=notifications/api
```

**Criterio de Éxito:** 100% de flujos CRUD + SSE + consumer verificados, 0 fallos.

---

### 3.3 Pruebas End-to-End (Cima de la Pirámide)

**Objetivo:** Validar flujos completos desde la recepción de un evento RabbitMQ hasta la consulta y gestión por API REST.

**Alcance:**

- **Flujo completo de notificación por ticket creado:**
  1. Ticket-service publica `ticket.created` en RabbitMQ
  2. Consumer recibe el evento y crea notificación vía ORM
  3. `GET /api/notifications/` lista la notificación con `read=false`
  4. `PATCH /api/notifications/{id}/read/` marca como leída → 200 OK + `read=true`
  5. `DELETE /api/notifications/{id}/` elimina → 204 No Content

- **Flujo completo de notificación por respuesta de admin:**
  1. Ticket-service publica `ticket.response_added`
  2. Consumer delega a `CreateNotificationFromResponseUseCase`
  3. Use case valida schema, verifica idempotencia, persiste
  4. SSE emite notificación en tiempo real al `user_id` correcto
  5. Segundo evento con mismo `response_id` → no crea duplicado

- **Flujo de errores:**
  1. Evento sin `ticket_id` → `InvalidEventSchema` + ACK (no DLQ)
  2. `POST /api/notifications/` → 405 Method Not Allowed
  3. `PATCH /api/notifications/999/read/` → 404 Not Found
  4. Error inesperado en use case → 500 JSON sin stack trace

**Herramientas:**
- pytest + Django TestCase
- Stack completo en contenedores (docker-compose)
- RabbitMQ real con exchange fanout

**Comando:**
```bash
docker-compose up -d db rabbitmq web
pytest notifications/tests/ -v --cov=notifications
```

**Criterio de Éxito:** Todos los flujos de usuario validados, 0 fallos.

---

## 4. Estrategia de Calidad

### 4.1 Enfoque de Testing (ISTQB §5.2.1)

**Estrategia Seleccionada:** **Híbrida (Analítica + Reactiva)**

- **Analítica (Risk-Based Testing):**
  - Priorizar pruebas según criticidad (ver sección 7: Gestión de Riesgos)
  - Idempotencia de consumer (Alta Prioridad)
  - SSE streaming con aislamiento por usuario (Alta Prioridad)
  - Validación de schema de eventos (Media Prioridad)

- **Reactiva (Exploración):**
  - Sesiones de testing exploratorio post-despliegue
  - Pruebas de regresión ad-hoc ante bugs reportados

### 4.2 Técnicas de Diseño de Pruebas (ISTQB §4)

| Técnica | Aplicación en el Proyecto |
|---------|---------------------------|
| **Partición de Equivalencia** | Tipos de evento (`ticket.created`, `ticket.response_added`, `ticket.status_changed`, `ticket.priority_changed`, evento desconocido). Estados de lectura (`read=true`, `read=false`). **EP22+:** Idempotencia diferenciada por tipo de evento (ver tabla EP22+ debajo). |
| **Análisis de Valores Límite** | Longitud de `ticket_id` (128 chars max), `message` (TextField sin límite), `user_id` (128 chars max). Valores null/vacío en campos obligatorios de eventos. |
| **Transición de Estados** | Estado de lectura: `read=false` → `read=true` (irreversible). Conexión RabbitMQ: `connected` → `disconnected` → `reconnecting` → `connected` (backoff exponencial). |
| **Tabla de Decisiones** | Validación de schema: combinaciones de campos faltantes (`ticket_id`, `response_id`, `user_id`) en `ticket.response_added`. Dispatch: `event_type` → handler correspondiente. |
| **Pruebas Negativas** | POST/PUT/PATCH retornan 405. Notificación inexistente → 404. Evento malformado → ACK + log (no crash). JSON inválido → ACK + log. |

#### EP22+ — Idempotencia por Tipo de Evento

La idempotencia garantiza que procesar el mismo evento más de una vez no produce datos duplicados. El mecanismo y el estado de implementación varían según el tipo de evento:

| Tipo de evento | Clave de idempotencia | Estado | Capa responsable |
|---------------|----------------------|--------|------------------|
| `ticket.response_added` | `response_id` (campo único en DB, indexado) | ✅ **Implementado** — `find_by_response_id()` en `CreateNotificationFromResponseUseCase` | Application |
| `ticket.created` | Sin mecanismo explícito | ⚠️ **No implementado** — acceso directo ORM en `_handle_ticket_created`, sin verificación de duplicados (DT-01) | Messaging (ORM directo) |
| `ticket.status_changed` | Sin mecanismo explícito | ⚠️ **No implementado** — no existe use case; además bloqueado por DT-09 (sin `user_id` en evento) | — |
| `ticket.priority_changed` | Sin mecanismo explícito | ⚠️ **No implementado** — no existe use case para este evento | — |

**Casos de prueba EP22+:**

| ID | Escenario | Estado | Archivo de test |
|----|-----------|--------|-----------------|
| EP22-A | `ticket.response_added` con `response_id` nuevo → crea notificación | ✅ | `test_response_handler.py::test_create_notification_from_valid_response_event` |
| EP22-B | `ticket.response_added` con `response_id` duplicado → no crea segunda notificación | ✅ | `test_response_handler.py::test_duplicate_response_id_does_not_create_second_notification` |
| EP22-C | `ticket.created` duplicado → debería no crear segunda notificación | ⏳ **Pendiente (DT-01)** | `test_ticket_created_use_case.py` (crear) |
| EP22-D | `ticket.status_changed` duplicado → debería no crear segunda notificación | ⏳ **Pendiente (DT-09)** | Bloqueado hasta que ticket-service incluya `user_id` en el evento |
| EP22-E | `ticket.priority_changed` duplicado → debería no crear segunda notificación | ⏳ **Pendiente** | `test_ticket_created_use_case.py` (crear) |

---

### 4.3 Estrategia de Datos de Prueba

**Datos Sintéticos:**
- Fixtures de notificaciones creadas por `DjangoNotification.objects.create()`
- Event payloads JSON para consumer (tickets creados, respuestas, cambios de estado)
- Mensajes RabbitMQ simulados con `unittest.mock`

**Datos Reales Anonimizados:**
- NO se utilizan datos de producción

**Gestión:**
- `conftest.py` con fixtures de pytest (si aplica)
- Base de datos limpia antes de cada test (transactional rollback por Django TestCase)
- Each test is self-contained (Arrange → Act → Assert)

---

## 5. Herramientas y Entorno

### 5.1 Herramientas de Prueba

| Herramienta | Propósito | Versión |
|-------------|-----------|---------|
| **pytest** | Runner de tests | 8.3.4 |
| **pytest-django** | Integración Django + pytest | 4.9.0 |
| **pytest-cov** | Medición de cobertura | 5.0.0 |
| **Django TestCase** | Tests de integración con DB | Django 6.0.2 |
| **TransactionTestCase** | Tests SSE (requiere commit real) | Django 6.0.2 |
| **DRF APIRequestFactory** | Tests de endpoints REST | DRF 3.15.2 |
| **unittest.mock** | Mocking de RabbitMQ, repositorios, publishers | stdlib |
| **itertools.islice** | Consumir chunks de SSE sin bloqueo infinito | stdlib |
| **GitHub Actions** | CI/CD pipeline | v4 |

### 5.2 Entorno de Pruebas

**Entornos Disponibles:**

1. **Local (Desarrollador):**
   - SQLite in-memory (configurado en `notification_service/test_settings.py`)
   - RabbitMQ mockeado para tests unitarios
   - RabbitMQ localhost para tests de integración
   - Ejecución: `pytest -v`

2. **Integración (CI/CD — GitHub Actions):**
   - SQLite in-memory
   - RabbitMQ service container (`rabbitmq:3` con health check)
   - Python 3.12, pip cache
   - Ejecución automática en push/PR a `main`, `develop`, `feature/**`, `fix/**`, `chore/**`, `docs/**`
   - Umbral de cobertura: `--cov-fail-under=70`
   - Timeout: 10 minutos

3. **Docker-compose (Entorno completo local):**
   - PostgreSQL 15 (`db`)
   - RabbitMQ 3 (`rabbitmq`)
   - Django + Gunicorn (`web`, puerto 8001)
   - Consumer standalone (`consumer`)
   - Volúmenes persistentes: `postgres_data`, `rabbitmq_data`

**Configuración de Test Settings:**

```python
# notification_service/test_settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
SECRET_KEY = 'test-secret-key-for-testing'
DEBUG = True
```

```ini
# pytest.ini
[pytest]
DJANGO_SETTINGS_MODULE = notification_service.test_settings
pythonpath = .
```

### 5.3 Infraestructura

**Stack de Contenedores (`docker-compose.yml`):**

| Servicio | Imagen | Puerto | Healthcheck |
|----------|--------|--------|-------------|
| `db` | PostgreSQL 15 | 5432 | `pg_isready` |
| `rabbitmq` | RabbitMQ 3 | 5672, 15672 | `rabbitmq-diagnostics ping` |
| `web` | Django + Gunicorn | 8001 | Python `urllib` a `/api/notifications/` |
| `consumer` | RabbitMQ listener | — | Depende de `web: service_healthy` |

---

## 6. Calendario de Pruebas

### 6.1 Fases del Proyecto

| Fase | Actividades de QA | Duración | Responsable |
|------|-------------------|----------|-------------|
| **Sprint 1: Dominio** | - Tests unitarios de entidad `Notification`<br>- Tests de excepciones de dominio<br>- Tests de eventos de dominio | 1 semana | QA Engineer |
| **Sprint 2: Application** | - Tests de `MarkNotificationAsReadUseCase`<br>- Tests de `CreateNotificationFromResponseUseCase`<br>- Tests de validación de schema (EP21)<br>- Tests de idempotencia (EP22) | 1 semana | QA Engineer + Dev |
| **Sprint 3: Integración** | - Tests de `DjangoNotificationRepository`<br>- Tests de ViewSet<br>- Tests de consumer dispatch<br>- Tests de SSE endpoint | 1 semana | QA Engineer |
| **Sprint 4: E2E + Estabilización** | - Flujos completos con docker-compose<br>- Tests de reconexión RabbitMQ<br>- Corrección de defectos<br>- Documentación final | 1 semana | Todo el equipo |

### 6.2 Ejecución en CI Pipeline

**Pipeline definido en `.github/workflows/ci.yml`:**

```yaml
# Disparadores: push/PR a main, develop, feature/**, fix/**, chore/**, docs/**
steps:
  - Checkout código
  - Configurar Python 3.12
  - Instalar dependencias (requirements-dev.txt)
  - Ejecutar tests con cobertura (pytest --cov-fail-under=70)
  - Subir artefacto coverage.xml
```

**Frecuencia de Ejecución:**
- **Unitarias + Integración:** Cada push / cada PR (~66 tests en < 2 minutos)
- **E2E con docker-compose:** Antes de merge a `main` (manual)
- **Cobertura:** Reportada en cada ejecución CI (artefacto `coverage.xml`)

---

## 7. Gestión de Riesgos

Siguiendo ISTQB Foundation §5.5 (Risk-Based Testing), se identifican, evalúan y mitigan riesgos técnicos y funcionales.

### 7.1 Matriz de Riesgos

| ID | Riesgo | Probabilidad | Impacto | Severidad | Estrategia | Mitigación |
|----|--------|--------------|---------|-----------|------------|------------|
| **R01** | **Pérdida de eventos RabbitMQ** (broker caído, consumer desconectado) | Media | Crítico | **ALTA** | Detectar + Recuperar | - Reconexión automática con backoff exponencial<br>- Dead Letter Queue (DLQ) para mensajes fallidos<br>- Health check de RabbitMQ en docker-compose |
| **R02** | **Notificaciones duplicadas** (idempotencia rota en `response_id`) | Media | Alto | **ALTA** | Prevenir | - `find_by_response_id()` antes de crear (EP22)<br>- Tests exhaustivos de idempotencia<br>- Campo `response_id` indexado en DB |
| **R03** | **Schema inválido en evento** (campos faltantes en `ticket.response_added`) | Alta | Medio | **ALTA** | Prevenir + Detectar | - Validación explícita en `CreateNotificationFromResponseUseCase` (EP21)<br>- `InvalidEventSchema` → ACK + log (no crash ni DLQ)<br>- Tests con combinaciones de campos faltantes |
| **R04** | **Inconsistencia ORM ↔ Dominio** (mapeo incorrecto en repositorio) | Media | Alto | **ALTA** | Prevenir | - Tests de `DjangoNotificationRepository`: save, find_by_id, find_all, find_by_response_id<br>- Validación bidireccional: `to_django_model()` y `to_domain()`<br>- Campos `user_id` y `response_id` explícitamente testeados |
| **R05** | **SSE stream bloqueante** (generator infinito bloquea tests/CI) | Alta | Alto | **ALTA** | Prevenir | - `itertools.islice` para consumir solo N chunks en tests<br>- `timeout-minutes: 10` en CI pipeline<br>- Helper `_read_sse_chunks()` en test suite |
| **R06** | **Violación del contrato DDD** (POST/PUT/PATCH expuestos por ModelViewSet) | Media | Alto | **ALTA** | Prevenir | - Override de `create/update/partial_update` → 405<br>- Tests que verifican 405 en métodos bloqueados<br>- Documentación en ARCHITECTURE.md |
| **R07** | **Stack trace expuesto en error 500** | Baja | Medio | **MEDIA** | Prevenir | - `except Exception` → Response JSON genérico en ViewSet<br>- Tests de error handling en read/destroy/clear_all<br>- `DEBUG=False` en producción |
| **R08** | **Consumer crashea el loop** (excepción no manejada en callback) | Media | Alto | **MEDIA** | Prevenir | - Try/except global en `callback()`<br>- `InvalidEventSchema` → ACK (sin NACK)<br>- Evento con JSON inválido → ACK + log |
| **R09** | **Filtrado SSE incorrecto** (usuario ve notificaciones de otro) | Baja | Crítico | **MEDIA** | Prevenir | - Filtro `Notification.objects.filter(user_id=user_id)` en SSE view<br>- Tests de aislamiento estricto (`test_sse_stream_isolates_users_strictly`) |
| **R10** | **Performance degradada en listado** (sin paginación, DT-06) | Media | Medio | **MEDIA** | Detectar | - `queryset.order_by('-sent_at')` con índice en `sent_at`<br>- Campos `ticket_id`, `read`, `user_id` indexados<br>- Deuda técnica DT-06: implementar paginación |
| **R11** | **`ticket.status_changed` sin `user_id`** — notificaciones imposibles de asociar al usuario destinatario (DT-09 en ARCHITECTURE.md) | Alta | Alto | **ALTA** | Aceptar (deuda técnica activa) | - El contrato oficial de `ticket.status_changed` no incluye `user_id` (ver ARCHITECTURE.md §9)<br>- Consumer crea notificación sin `user_id` → SSE no puede filtrar, campo queda vacío<br>- Bloqueante hasta que ticket-service extienda el contrato del evento<br>- Tests ⏳ pendientes: `test_status_changed_notification_has_no_user_id` |

### 7.2 Estrategias de Mitigación Detalladas

#### R01: Pérdida de Eventos RabbitMQ

**Escenario de Fallo:**  
RabbitMQ reinicia o el consumer pierde conexión. Los eventos publicados por ticket-service no llegan al notification-service.

**Impacto:**
- Usuarios no reciben notificaciones de nuevos tickets o respuestas
- Inconsistencia entre ticket-service y notification-service
- Pérdida de confianza del usuario

**Plan de Mitigación:**
1. **Prevención:**
   - Cola durable (`durable=True`) — mensajes persisten en disco de RabbitMQ
   - Exchange fanout configurado como durable
   - Consumer con `auto_ack=False` — solo ACK después de procesar exitosamente

2. **Detección:**
   - Reconexión automática con backoff exponencial (configurable):
     - `RABBITMQ_INITIAL_RETRY_DELAY`: 1s
     - `RABBITMQ_MAX_RETRY_DELAY`: 60s
     - `RABBITMQ_RETRY_BACKOFF_FACTOR`: 2
     - `RABBITMQ_MAX_RETRIES`: 0 (infinito)
   - Logging de reconexiones y fallos

3. **Recuperación:**
   - Dead Letter Queue (DLQ): mensajes que fallan procesamiento (NACK con `requeue=False`) van a `{queue}.dlq` vía Dead Letter Exchange `{queue}.dlx`
   - Inspección manual de DLQ para reprocesamiento

**Tests asociados:**
- `test_consumer_reconnection.py` (reconexión con backoff)
- `test_dead_letter_queue.py` (DLQ setup y enrutamiento)
- `test_integration.py::test_consumer_creates_notification` (flujo completo)

**Indicadores:**
- < 0.1% de eventos perdidos
- Tiempo de reconexión < 60 segundos

---

#### R02: Notificaciones Duplicadas

**Escenario de Fallo:**  
RabbitMQ entrega el mismo evento `ticket.response_added` dos veces (redelivery tras timeout). Sin idempotencia, se crean dos notificaciones idénticas para la misma respuesta.

**Impacto:**
- Usuario ve notificaciones duplicadas
- Inconsistencia de datos
- Experiencia de usuario degradada

**Plan de Mitigación:**
1. **Prevención:**
   - `CreateNotificationFromResponseUseCase` ejecuta `repository.find_by_response_id(response_id)` antes de crear
   - Si ya existe → retorna la existente sin crear nueva
   - Campo `response_id` indexado en DB para búsqueda eficiente

2. **Detección:**
   - Tests exhaustivos en `test_response_handler.py`:
     - `test_duplicate_response_id_does_not_create_second_notification`
     - `test_first_event_with_response_id_calls_find_and_save`
   - Validación en tests: `repository.save.assert_not_called()` para duplicados

**Indicadores:**
- 0 notificaciones duplicadas por `response_id`
- `find_by_response_id` invocado antes de cada `save` para `ticket.response_added`

---

#### R03: Schema Inválido en Evento

**Escenario de Fallo:**  
Ticket-service publica un evento `ticket.response_added` sin el campo obligatorio `ticket_id`. El consumer intenta crearlo y falla.

**Impacto:**
- Notificación no creada (esperado)
- Riesgo de crash del consumer loop (no deseado)
- Mensaje podría quedar en DLQ innecesariamente

**Plan de Mitigación:**
1. **Prevención:**
   - `CreateNotificationFromResponseUseCase` valida presencia de campos obligatorios: `ticket_id`, `response_id`, `user_id`
   - `InvalidEventSchema` lanzada con lista de campos faltantes
   - Consumer hace ACK (no NACK) para `InvalidEventSchema` — mensaje malformado no debe ir a DLQ

2. **Detección:**
   - Tests en `test_response_handler.py`:
     - `test_event_missing_ticket_id_raises_invalid_schema`
     - `test_event_missing_response_id_raises_invalid_schema`
     - `test_event_missing_user_id_raises_invalid_schema`
     - `test_event_missing_multiple_fields_raises_invalid_schema`
   - Test en `test_consumer_dispatch.py`:
     - `test_callback_logs_error_on_invalid_response_event` (ACK + log, no crash)

**Indicadores:**
- 0 crashes del consumer por schema inválido
- 100% de mensajes con schema inválido logueados y ACKed

---

#### R04: Inconsistencia ORM ↔ Dominio

**Escenario de Fallo:**  
`DjangoNotificationRepository.save()` no persiste correctamente `user_id` o `response_id` al mapear entidad de dominio → modelo Django ORM.

**Impacto:**
- Notificaciones sin `user_id` → SSE no puede filtrar
- Notificaciones sin `response_id` → idempotencia rota (R02 activado)
- Bugs silenciosos difíciles de detectar

**Plan de Mitigación:**
1. **Prevención:**
   - Tests explícitos de `user_id` y `response_id` en `test_infrastructure.py`:
     - `test_save_persists_user_id_and_response_id`
     - `test_save_updates_user_id_and_response_id`
     - `test_find_by_response_id_returns_notification_when_exists`
     - `test_find_by_response_id_returns_none_when_not_exists`
   - Mapeo bidireccional testeado: `to_django_model()` verifica todos los campos

2. **Detección:**
   - 10 tests de infraestructura cubren todos los métodos del repositorio
   - Cada test verifica campos individuales con `refresh_from_db()`

**Indicadores:**
- 100% de campos de dominio mapeados correctamente
- 0 discrepancias en tests de repositorio

---

#### R05: SSE Stream Bloqueante

**Escenario de Fallo:**  
El endpoint SSE retorna un `StreamingHttpResponse` con un generator infinito (`while True: yield ...`). En tests, `b''.join(streaming_content)` bloquea indefinidamente el runner.

**Impacto:**
- CI pipeline colgado (timeout tras 10 minutos)
- Tests de SSE imposibles de ejecutar
- Pipeline inutilizable

**Plan de Mitigación:**
1. **Prevención:**
   - Helper `_read_sse_chunks(response, max_chunks)` usa `itertools.islice()` para consumir solo N chunks
   - Pattern: 1 heartbeat + N notificaciones esperadas = `max_chunks`
   - `timeout-minutes: 10` en CI como safety net

2. **Detección:**
   - 8 tests de SSE pasando consistentemente en CI
   - Tests con diferentes combinaciones: 0 notifs, 1 notif, 2 notifs de un user, notifs de múltiples users

**Indicadores:**
- 0 timeouts en CI por tests SSE
- 100% de tests SSE ejecutados en < 5 segundos

---

#### R06: Violación del Contrato DDD (POST/PUT/PATCH Expuestos)

**Escenario de Fallo:**  
`ModelViewSet` de DRF expone automáticamente `create()`, `update()`, `partial_update()`. Sin override, un client podría crear notificaciones por HTTP, violando el principio de que solo se crean por eventos RabbitMQ.

**Impacto:**
- Violación de la regla de negocio fundamental del servicio
- Bypass de validación de schema y idempotencia
- Inconsistencia con el flujo EDA

**Plan de Mitigación:**
1. **Prevención:**
   - Override en `NotificationViewSet`:
     - `create()` → 405 Method Not Allowed
     - `update()` → 405 Method Not Allowed
     - `partial_update()` → 405 Method Not Allowed
   - Solo `PATCH /notifications/{id}/read/` permitido via `@action(detail=True, methods=['patch'])`

2. **Detección:**
   - Documentado en ARCHITECTURE.md sección 8 (tabla de verbos HTTP)
   - PR checklist verifica que métodos prohibidos no sean reactivados

**Indicadores:**
- 0 notificaciones creadas por HTTP POST/PUT/PATCH en producción
- 405 retornados consistentemente

---

#### R11: `ticket.status_changed` sin `user_id` (DT-09)

**Escenario de Fallo:**  
El contrato oficial del evento `ticket.status_changed` publicado por ticket-service **no incluye el campo `user_id`**. El consumer crea la notificación pero no puede asociarla al usuario destinatario, por lo que `user_id` queda como cadena vacía `''` en la base de datos.

**Impacto:**
- El endpoint SSE filtra por `user_id` — la notificación nunca llega al usuario correcto
- La notificación existe en DB pero es inaccesible por usuario via SSE
- El sistema no puede cumplir el objetivo de notificaciones en tiempo real para cambios de estado

**Plan de Mitigación:**
1. **Aceptación temporal (hasta resolver DT-09):**
   - El riesgo está documentado y aceptado conscientemente (deuda técnica activa)
   - No se implementan workarounds que puedan enmascarar el problema

2. **Opciones de resolución (bloqueadas externamente):**
   - *Opción A (preferida):* Ticket-service extiende el contrato de `ticket.status_changed` para incluir `user_id`
   - *Opción B (fallback):* Notification-service realiza lookup REST al ticket-service para obtener `user_id` dado `ticket_id` — introduce acoplamiento sincrónico

3. **Tests pendientes ⏳:**
   - `test_status_changed_notification_stored_without_user_id` — verificar que la notificación se crea con `user_id=''`
   - `test_status_changed_notification_not_delivered_via_sse` — verificar que SSE no entrega la notificación (ausencia de `user_id` como filtro)

**Indicadores:**
- DT-09 cerrada en ARCHITECTURE.md cuando ticket-service extienda el contrato
- 0 notificaciones de `ticket.status_changed` entregadas via SSE en el estado actual (comportamiento esperado hasta resolver DT-09)

---

#### Política de ACK/NACK del Consumer (Anexo a R01, R03, R08)

El comportamiento del consumer ante distintos tipos de condición está definido explícitamente en `callback()` (`notifications/messaging/consumer.py`). La siguiente tabla resuelve la ambigüedad entre mensajes que van a DLQ y mensajes que se descartan con ACK:

| Condición en `callback()` | Excepción | Comportamiento | Destino mensaje | Riesgo |
|---------------------------|-----------|----------------|-----------------|--------|
| Procesamiento exitoso | — | `basic_ack` ✅ | Consumido | — |
| Body no es JSON válido | `json.JSONDecodeError` | `basic_ack` ✅ + log ERROR | Descartado | R08 |
| Campos obligatorios faltantes | `InvalidEventSchema` | `basic_ack` ✅ + log ERROR | Descartado | R03, R08 |
| Error inesperado del sistema | `Exception` genérica | `basic_nack(requeue=False)` ❌ | **DLQ** (`{queue}.dlq`) | R01, R08 |

**Regla de diseño:** Solo los errores **inesperados del sistema** van a DLQ. Los mensajes con datos incorrectos (`InvalidEventSchema`, JSON inválido) se descartan con ACK porque:
- Reencolarlos (`requeue=True`) generaría un loop infinito de fallos
- La DLQ está diseñada para errores **transitorios del sistema** (DB caída, timeout), no para datos incorrectos del productor
- Un mensaje malformado es responsabilidad del productor del evento, no del consumer

**Cobertura de tests para esta política:**
- `test_callback_acks_message_on_response_added` → ACK en flujo exitoso
- `test_callback_logs_error_on_invalid_response_event` → ACK + log para `InvalidEventSchema`
- `test_dead_letter_queue.py` → NACK → DLQ para `Exception` genérica

---

### 7.3 Plan de Contingencia

**Criterios de Abortar Release:**
- Cualquier defecto de **Severidad ALTA** no resuelto
- < 70% de cobertura de código (umbral CI)
- Fallo en > 5% de tests automatizados (> 3 tests de 66)

**Rollback:**
- Despliegue con Docker images versionadas
- Rollback automático si healthcheck de web service falla post-deploy
- Consumer reconecta automáticamente tras restart del servicio

---

## 8. Criterios de Entrada y Salida

### 8.1 Criterios de Entrada (Entry Criteria)

**Para iniciar testing de un sprint:**

- [ ] Código mergeado a rama de testing (`develop`)
- [ ] Entorno de pruebas disponible (CI pipeline verde o docker-compose up)
- [ ] `requirements-dev.txt` instalado (pytest + pytest-django + pytest-cov)
- [ ] `pytest.ini` configurado con `DJANGO_SETTINGS_MODULE = notification_service.test_settings`
- [ ] RabbitMQ disponible para tests de integración (localhost o service container)

**Para iniciar testing E2E:**

- [ ] Todas las pruebas unitarias e integración pasando (100%)
- [ ] Stack completo desplegado con `docker-compose up -d` (db + rabbitmq + web + consumer)
- [ ] Healthchecks de todos los servicios en estado healthy
- [ ] Exchange fanout y cola de notificaciones declarados en RabbitMQ

### 8.2 Criterios de Salida (Exit Criteria)

**Para finalizar testing de un sprint:**

- [ ] ≥ 85% cobertura de código (actual: 89.50%)
- [ ] 100% de tests pasando (66/66)
- [ ] 0 defectos de severidad ALTA o CRÍTICA abiertos
- [ ] ≤ 3 defectos de severidad MEDIA abiertos (priorizados para próximo sprint)
- [ ] Reporte de cobertura generado (`coverage.xml` como artefacto CI)

**Para aprobar release a producción:**

- [ ] 100% de tests pasando en CI
- [ ] Cobertura ≥ 70% (umbral CI `--cov-fail-under=70`)
- [ ] ARCHITECTURE.md actualizado con cualquier cambio de contrato
- [ ] docker-compose stack levanta sin errores
- [ ] Consumer conecta a RabbitMQ y procesa eventos correctamente
- [ ] SSE endpoint responde con heartbeat y notificaciones filtradas

---

## 9. Roles y Responsabilidades

| Rol | Responsabilidades | Persona |
|-----|-------------------|---------|
| **QA Lead** | - Definir estrategia de testing<br>- Revisar plan de pruebas<br>- Aprobar releases<br>- Gestión de riesgos | [Nombre] |
| **QA Engineer** | - Diseñar y ejecutar casos de prueba<br>- Automatizar tests<br>- Reportar defectos<br>- Mantener fixtures y helpers | [Nombre] |
| **Backend Developer** | - Escribir tests unitarios de dominio<br>- Corregir defectos<br>- Code review de tests<br>- Respetar reglas DDD en PRs | [Nombre] |
| **DevOps Engineer** | - Mantener CI/CD pipeline<br>- Docker-compose y healthchecks<br>- Monitoreo de cobertura<br>- Rollback en caso de emergencia | [Nombre] |
| **Product Owner** | - Validar escenarios de prueba<br>- Priorizar corrección de defectos<br>- Aprobar criterios de aceptación | [Nombre] |

---

## 10. Entregables

### 10.1 Documentación

| Entregable | Descripción | Responsable | Plazo |
|------------|-------------|-------------|-------|
| **Plan de Pruebas (este documento)** | Estrategia, niveles, herramientas, riesgos | QA Lead | Sprint 1 |
| **Test Cases Detallados** | Casos de prueba en formato Gherkin (Given/When/Then) | QA Engineer | Sprint 2 |
| **ARCHITECTURE.md** | Debate arquitectónico + contrato API REST + contrato eventos | Backend Lead | Sprint 1 |
| **Reporte de Cobertura** | `coverage.xml` generado por CI en cada push | CI Pipeline | Automático |

### 10.2 Artefactos de Código

**Test Suites (8 archivos, 66 tests):**

| Nivel | Archivo | Tests |
|-------|---------|-------|
| Unitario | `test_domain.py` | 5 |
| Unitario | `test_use_cases.py` | 3 |
| Unitario | `test_response_handler.py` | 9 |
| Unitario | `test_consumer_dispatch.py` | 4 |
| Integración | `test_infrastructure.py` | 10 |
| Integración | `test_views.py` | 2 |
| Integración | `test_integration.py` | 2 |
| Integración | `test_sse_endpoint.py` | 8 |
| **Subtotal** | | **43** |
| Resiliencia | `test_consumer_reconnection.py` | ~12 |
| Resiliencia | `test_dead_letter_queue.py` | ~11 |
| **Total** | | **66** |

**Infraestructura de CI:**
- `.github/workflows/ci.yml` — pipeline con RabbitMQ service container
- `notification_service/test_settings.py` — configuración de test
- `pytest.ini` — configuración de pytest
- `requirements-dev.txt` — dependencias de desarrollo

---

## 11. Métricas de Calidad

### 11.1 KPIs Principales

| Métrica | Objetivo | Actual | Medición | Frecuencia |
|---------|----------|--------|----------|------------|
| **Cobertura de Código** | ≥ 85% | 89.50% | pytest-cov | Cada push |
| **Tests Pasando** | 100% | 66/66 (100%) | pytest | Cada push |
| **Defectos Críticos** | 0 en producción | 0 | GitHub Issues | Continuo |
| **Tiempo de CI Pipeline** | < 5 min | ~2 min | GitHub Actions | Cada push |
| **Umbral de Cobertura CI** | ≥ 70% | 89.50% | `--cov-fail-under=70` | Cada push |

### 11.2 Dashboard de Métricas

**Herramientas:**
- **pytest-cov:** Reporte en terminal (`--cov-report=term-missing`) + XML (`coverage.xml`)
- **GitHub Actions:** Artefacto de cobertura con retención de 7 días
- **pytest:** Reporte detallado con `-v` en CI

**Ejemplo de Reporte CI:**

```
=== 66 passed in 12.34s ===

---------- coverage: platform linux, python 3.12.x ----------
Name                                          Stmts   Miss  Cover   Missing
---------------------------------------------------------------------------
notifications/api.py                             XX      X    XX%   ...
notifications/application/use_cases.py           XX      X    XX%   ...
notifications/domain/entities.py                 XX      0   100%
notifications/domain/exceptions.py               XX      0   100%
notifications/infrastructure/repository.py       XX      X    XX%   ...
notifications/messaging/consumer.py              XX      X    XX%   ...
---------------------------------------------------------------------------
TOTAL                                           XXX     XX   89%

Required test coverage of 70% reached. Total coverage: 89.50%
```

---

## 12. Referencias ISTQB

Este plan de pruebas se basa en los siguientes conceptos del **ISTQB Foundation Level** (Syllabus v4.0):

### 12.1 Test Planning (§5.1)

- **Propósito del plan de pruebas:** Documentar los medios y el calendario para alcanzar los objetivos de prueba
- **Contenido:** Contexto, alcance, niveles, cronología, riesgos, métricas, criterios de entrada/salida

### 12.2 Test Strategy (§5.2)

- **Estrategia seleccionada:** Híbrida (analítica + reactiva)
- **Analítica:** Risk-Based Testing — priorización por matriz de riesgos (sección 7)
- **Reactiva:** Testing exploratorio post-despliegue

### 12.3 Test Monitoring and Control (§5.3)

- **Métricas:** Cobertura, tasa de tests pasando, tiempo de pipeline
- **Reporting:** Automático por CI, artefactos de cobertura en GitHub Actions
- **Control:** Pipeline falla si cobertura < 70% o algún test no pasa

### 12.4 Risk-Based Testing (§5.5)

- **Identificación de Riesgos:** 11 riesgos identificados (R01-R11)
- **Análisis de Riesgos:** Clasificación por probabilidad × impacto en ALTA/MEDIA/BAJA
- **Mitigación:** Estrategias preventivas (tests, validaciones), detectivas (CI, logs) y correctivas (DLQ, reconexión)

### 12.5 Test Levels (§2.2)

- **Unit Testing:** Entidad `Notification`, use cases (mock repos), exceptions
- **Integration Testing:** Repository ORM, ViewSet, SSE, consumer + RabbitMQ
- **System Testing:** Flujos completos con docker-compose (E2E)

### 12.6 Test Design Techniques (§4)

- **Equivalence Partitioning (§4.2.1):** Tipos de evento, estados de lectura
- **Boundary Value Analysis (§4.2.2):** Longitudes de `ticket_id`, `user_id`, campos nulos
- **State Transition Testing (§4.2.4):** `read: false → true` (irreversible), conexión RabbitMQ
- **Decision Table Testing (§4.2.3):** Validación de schema, dispatch por `event_type`

### 12.7 Defect Management (§5.6)

- **Ciclo de Vida de Defectos:** New → Assigned → Fixed → Verified → Closed
- **Priorización:** Crítico > Alto > Medio > Bajo
- **Tracking:** GitHub Issues con labels

---

## Aprobaciones

| Rol | Nombre | Firma | Fecha |
|-----|--------|-------|-------|
| **QA Lead** | | | |
| **Backend Lead** | | | |
| **Product Owner** | | | |

---

## Control de Versiones

| Versión | Fecha | Autor | Cambios |
|---------|-------|-------|---------|
| 1.0 | 2026-02-01 | QA Team | Plan inicial (TEST_PLAN.md) |
| 2.0 | 2026-02-15 | QA Lead | Añadida sección de riesgos, alineado con monorepo (TEST_PLAN2.md) |
| 3.0 | 2026-02-26 | QA Team | Plan completo ISTQB para notification-service independiente: niveles de prueba, gestión de riesgos detallada, métricas, criterios de entrada/salida |
| 3.1 | 2026-02-26 | QA Team | Incorporación de 4 observaciones de revisión: R11 (DT-09 `ticket.status_changed` sin `user_id`), política explícita ACK/NACK, tests pendientes DT-01, expansión EP22+ para los 4 tipos de evento |
| 3.2 | 2026-02-26 | QA Team | Actividad 3.2: Diseño de casos de prueba en lenguaje Gherkin (§13) — 30 casos organizados por épica con matriz de ejecución manual |

---

**Fin del Documento**

---

## Anexo A: Checklist de Ejecución de Tests

```bash
# 1. Ejecución rápida (sin RabbitMQ, solo unitarias + integración con SQLite)
pytest -v --cov=notifications --cov-report=term-missing

# 2. Ejecución con cobertura mínima (como en CI)
pytest --cov=notifications --cov-fail-under=70 -v

# 3. Solo tests unitarios (dominio + application)
pytest notifications/tests/test_domain.py notifications/tests/test_use_cases.py notifications/tests/test_response_handler.py notifications/tests/test_consumer_dispatch.py -v

# 4. Solo tests de integración (infraestructura + views + SSE)
pytest notifications/tests/test_infrastructure.py notifications/tests/test_views.py notifications/tests/test_sse_endpoint.py -v

# 5. Tests con RabbitMQ real (requiere RabbitMQ en localhost o docker-compose)
RABBITMQ_HOST=localhost pytest notifications/tests/test_integration.py -v

# 6. Generar reporte de cobertura HTML
pytest --cov=notifications --cov-report=html --cov-report=term

# 7. Ejecución completa con docker-compose
docker-compose up -d db rabbitmq
pytest -v --cov=notifications --cov-fail-under=70
```

---

## Anexo B: Plantilla de Reporte de Defectos

```markdown
### Defecto #[ID]

**Título:** [Descripción breve]
**Severidad:** [ ] Crítica [ ] Alta [ ] Media [ ] Baja
**Prioridad:** [ ] Urgente [ ] Alta [ ] Normal [ ] Baja
**Estado:** [ ] New [ ] Assigned [ ] Fixed [ ] Verified [ ] Closed

**Descripción:**
[Descripción detallada del problema]

**Pasos para Reproducir:**
1. [Paso 1]
2. [Paso 2]
3. [Paso 3]

**Resultado Esperado:**
[Qué debería ocurrir]

**Resultado Actual:**
[Qué ocurre realmente]

**Entorno:**
- SO: [Windows/Linux/macOS]
- Python: 3.12
- Django: 6.0.2
- Base de datos: [PostgreSQL 15 / SQLite in-memory]
- RabbitMQ: 3.x

**Logs/Screenshots:**
[Adjuntar logs relevantes o capturas de pantalla]

**Asignado a:** [Nombre del desarrollador]
**Reportado por:** [Nombre del QA]
**Fecha:** [YYYY-MM-DD]
```

---

## Anexo C: Inventario de Tests por Archivo

| # | Archivo | Test | Nivel | Capa |
|---|---------|------|-------|------|
| 1 | `test_domain.py` | `test_create_notification_with_valid_data` | Unitario | Domain |
| 2 | `test_domain.py` | `test_mark_as_read_changes_state` | Unitario | Domain |
| 3 | `test_domain.py` | `test_mark_as_read_is_idempotent` | Unitario | Domain |
| 4 | `test_domain.py` | `test_mark_as_read_already_read_notification` | Unitario | Domain |
| 5 | `test_domain.py` | `test_collect_domain_events_clears_list` | Unitario | Domain |
| 6 | `test_use_cases.py` | `test_mark_as_read_success` | Unitario | Application |
| 7 | `test_use_cases.py` | `test_mark_as_read_notification_not_found` | Unitario | Application |
| 8 | `test_use_cases.py` | `test_mark_as_read_already_read_no_event` | Unitario | Application |
| 9 | `test_response_handler.py` | `test_create_notification_from_valid_response_event` | Unitario | Application |
| 10 | `test_response_handler.py` | `test_create_notification_message_format` | Unitario | Application |
| 11 | `test_response_handler.py` | `test_event_missing_ticket_id_raises_invalid_schema` | Unitario | Application |
| 12 | `test_response_handler.py` | `test_event_missing_response_id_raises_invalid_schema` | Unitario | Application |
| 13 | `test_response_handler.py` | `test_event_missing_user_id_raises_invalid_schema` | Unitario | Application |
| 14 | `test_response_handler.py` | `test_event_missing_multiple_fields_raises_invalid_schema` | Unitario | Application |
| 15 | `test_response_handler.py` | `test_duplicate_response_id_does_not_create_second_notification` | Unitario | Application |
| 16 | `test_response_handler.py` | `test_first_event_with_response_id_calls_find_and_save` | Unitario | Application |
| 17 | `test_response_handler.py` | `test_notification_has_user_id_from_command` | Unitario | Application |
| 18 | `test_response_handler.py` | `test_notification_has_response_id_from_command` | Unitario | Application |
| 19 | `test_consumer_dispatch.py` | `test_callback_dispatches_response_added_to_use_case` | Unitario | Messaging |
| 20 | `test_consumer_dispatch.py` | `test_callback_handles_ticket_created_normally` | Unitario | Messaging |
| 21 | `test_consumer_dispatch.py` | `test_callback_acks_message_on_response_added` | Unitario | Messaging |
| 22 | `test_consumer_dispatch.py` | `test_callback_logs_error_on_invalid_response_event` | Unitario | Messaging |
| ⏳ | `test_ticket_created_use_case.py` | `test_create_notification_from_ticket_created_event` *(DT-01 — pendiente)* | Unitario | Application |
| ⏳ | `test_ticket_created_use_case.py` | `test_ticket_created_idempotency_no_duplicate` *(EP22-C — pendiente)* | Unitario | Application |
| ⏳ | `test_ticket_created_use_case.py` | `test_status_changed_notification_stored_without_user_id` *(R11/DT-09 — pendiente)* | Unitario | Messaging |
| 23 | `test_infrastructure.py` | `test_save_new_notification` | Integración | Infrastructure |
| 24 | `test_infrastructure.py` | `test_save_existing_notification` | Integración | Infrastructure |
| 25 | `test_infrastructure.py` | `test_find_by_id_existing` | Integración | Infrastructure |
| 26 | `test_infrastructure.py` | `test_find_by_id_not_found` | Integración | Infrastructure |
| 27 | `test_infrastructure.py` | `test_find_all` | Integración | Infrastructure |
| 28 | `test_infrastructure.py` | `test_to_django_model` | Integración | Infrastructure |
| 29 | `test_infrastructure.py` | `test_find_by_response_id_returns_notification_when_exists` | Integración | Infrastructure |
| 30 | `test_infrastructure.py` | `test_find_by_response_id_returns_none_when_not_exists` | Integración | Infrastructure |
| 31 | `test_infrastructure.py` | `test_save_persists_user_id_and_response_id` | Integración | Infrastructure |
| 32 | `test_infrastructure.py` | `test_save_updates_user_id_and_response_id` | Integración | Infrastructure |
| 33 | `test_views.py` | `test_read_action_success` | Integración | Presentation |
| 34 | `test_views.py` | `test_read_action_not_found` | Integración | Presentation |
| 35 | `test_integration.py` | `test_consumer_creates_notification` | Integración | E2E |
| 36 | `test_integration.py` | `test_notification_model` | Integración | Model |
| 37 | `test_sse_endpoint.py` | `test_sse_endpoint_returns_200_with_event_stream_content_type` | Integración | SSE |
| 38 | `test_sse_endpoint.py` | `test_sse_endpoint_returns_streaming_http_response` | Integración | SSE |
| 39 | `test_sse_endpoint.py` | `test_sse_endpoint_streams_notifications_for_given_user_id` | Integración | SSE |
| 40 | `test_sse_endpoint.py` | `test_sse_endpoint_returns_proper_sse_format` | Integración | SSE |
| 41 | `test_sse_endpoint.py` | `test_sse_stream_includes_heartbeat_comment` | Integración | SSE |
| 42 | `test_sse_endpoint.py` | `test_sse_stream_isolates_users_strictly` | Integración | SSE |
| 43 | `test_sse_endpoint.py` | `test_sse_event_payload_includes_response_id` | Integración | SSE |
| 44 | `test_sse_endpoint.py` | `test_sse_no_notifications_still_sends_heartbeat` | Integración | SSE |
| 45-66 | `test_consumer_reconnection.py`, `test_dead_letter_queue.py` | ~23 tests de resiliencia | Unitario | Messaging |

---

## Anexo D: Glosario de Términos

- **DDD (Domain-Driven Design):** Enfoque de arquitectura centrado en el dominio de negocio
- **EDA (Event-Driven Architecture):** Arquitectura basada en eventos asincrónicos
- **SSE (Server-Sent Events):** Protocolo HTTP unidireccional para streaming en tiempo real
- **DLQ (Dead Letter Queue):** Cola de mensajes fallidos en RabbitMQ para inspección
- **DLX (Dead Letter Exchange):** Exchange que enruta mensajes rechazados a la DLQ
- **ACK (Acknowledgement):** Confirmación de recepción exitosa de un mensaje al broker
- **NACK (Negative Acknowledgement):** Rechazo de un mensaje (enrutado a DLQ si `requeue=False`)
- **EP21:** Escenario de Prueba 21 — Validación de schema de eventos
- **EP22:** Escenario de Prueba 22 — Idempotencia por `response_id`
- **EP22+:** Extensión — Idempotencia diferenciada para los 4 tipos de evento (ver §4.2 tabla EP22+)
- **EP23:** Escenario de Prueba 23 — SSE streaming con filtrado por `user_id`
- **ORM (Object-Relational Mapping):** Mapeo objeto-relacional (Django ORM)
- **ABC (Abstract Base Class):** Clase base abstracta de Python para definir interfaces
- **p95 (Percentile 95):** El 95% de las requests son más rápidas que este valor

---

## 13. Diseño de Casos de Prueba — Actividad 3.2

> **Actividad 3.2 — Taller Semana 3:** Diseñar casos de prueba redactados en lenguaje Gherkin (Given/When/Then), aplicando técnicas de diseño para maximizar la cobertura. Los escenarios se organizan en una matriz de pruebas donde se registra la ejecución manual indicando el resultado obtenido (Pasó/Falló).

### 13.1 Matriz de Pruebas (Resumen de Ejecución Manual)

La siguiente tabla funciona como **hoja de cálculo de ejecución manual**. Cada fila referencia un caso Gherkin detallado en las subsecciones 13.2–13.7. La columna **Resultado** se actualiza tras la ejecución.

| ID | Épica | US | Técnica | Escenario (resumen) | Prioridad | Auto | Resultado |
|----|-------|-----|---------|---------------------|-----------|------|-----------|
| TC-E1-01 | E1 | US-E1-01 | EP | `ticket.created` → notificación persistida | Alta | ✅ | ✅ Pasó |
| TC-E1-02 | E1 | US-E1-01 | DT | `ticket.created` sin campos obligatorios → DLQ | Alta | ✅ | ✅ Pasó |
| TC-E1-03 | E1 | US-E1-01 | BVA | Contenido del mensaje generado (Scenario Outline) | Media | ✅ | ✅ Pasó |
| TC-E1-04 | E1 | US-E1-02 | EP | `ticket.response_added` → notificación con response_id | Alta | ✅ | ✅ Pasó |
| TC-E1-05 | E1 | US-E1-02 | DT | `ticket.response_added` sin campos → InvalidEventSchema + ACK | Alta | ✅ | ✅ Pasó |
| TC-E1-06 | E1 | US-E1-02 | EP | response_text vacío → notificación sin texto de respuesta | Media | ✅ | ✅ Pasó |
| TC-E1-07 | E1 | US-E1-02 | BVA | response_text > 255 chars → message truncado | Media | ✅ | ✅ Pasó |
| TC-E1-08 | E1 | US-E1-05 | EP | Mismo response_id duplicado → no crea segunda notificación | Alta | ✅ | ✅ Pasó |
| TC-E1-09 | E1 | US-E1-02 | EP | Dos response_id distintos → dos notificaciones independientes | Alta | ✅ | ✅ Pasó |
| TC-E1-10 | E1 | US-E1-03 | EP | `ticket.status_changed` → notificación (estado objetivo) | Alta | ⏳ | ⏳ Pendiente (DT-09) |
| TC-E1-11 | E1 | US-E1-03 | EP/Outline | Variación por new_status: open, in_progress, closed | Media | ⏳ | ⏳ Pendiente (DT-09) |
| TC-E1-12 | E1 | US-E1-03 | DT | `ticket.status_changed` sin user_id → comportamiento actual | Alta | ⏳ | ⏳ Pendiente (R11/DT-09) |
| TC-E1-13 | E1 | US-E1-04 | EP | `ticket.priority_changed` → notificación | Media | ✅ | ✅ Pasó |
| TC-E1-14 | E1 | US-E1-04 | EP/Outline | Variación por new_priority: high, medium, low | Media | ✅ | ✅ Pasó |
| TC-E1-15 | E1 | US-E1-04 | Negativa | Prioridad fuera de catálogo → DLQ | Media | ✅ | ✅ Pasó |
| TC-E1-16 | E1 | US-E1-05 | EP | Evento duplicado ticket.created → descartado | Alta | ⏳ | ⏳ Pendiente (DT-01) |
| TC-E1-17 | E1 | US-E1-05 | EP | Mismo ticket_id + distinto event_type → no es duplicado | Alta | ✅ | ✅ Pasó |
| TC-E2-01 | E2 | US-E2-01 | EP | GET /api/notifications/ → lista con notificaciones | Alta | ✅ | ✅ Pasó |
| TC-E2-02 | E2 | US-E2-01 | BVA | GET /api/notifications/ con 0 notificaciones → lista vacía | Media | ✅ | ✅ Pasó |
| TC-E2-03 | E2 | US-E2-02 | EP | GET /api/notifications/{id}/ → 200 + detalle | Alta | ✅ | ✅ Pasó |
| TC-E2-04 | E2 | US-E2-02 | Negativa | GET /api/notifications/999/ → 404 | Alta | ✅ | ✅ Pasó |
| TC-E3-01 | E3 | US-E3-01 | ST | PATCH read/ sobre notificación no leída → read: true | Alta | ✅ | ✅ Pasó |
| TC-E3-02 | E3 | US-E3-01 | ST | PATCH read/ sobre notificación ya leída → idempotente 200 | Alta | ✅ | ✅ Pasó |
| TC-E3-03 | E3 | US-E3-01 | Negativa | PATCH read/ sobre id inexistente → 404 | Alta | ✅ | ✅ Pasó |
| TC-E4-01 | E4 | US-E4-01 | EP | DELETE /api/notifications/{id}/ → 204 | Media | ✅ | ✅ Pasó |
| TC-E4-02 | E4 | US-E4-01 | Negativa | DELETE id inexistente → 404 | Media | ✅ | ✅ Pasó |
| TC-E4-03 | E4 | US-E4-02 | EP | DELETE /api/notifications/clear/ → 204 + bandeja vacía | Media | ✅ | ✅ Pasó |
| TC-E4-04 | E4 | US-E4-02 | ST | Clear all con bandeja ya vacía → 204 (idempotente) | Media | ✅ | ✅ Pasó |
| TC-E5-01 | E5 | US-E5-01 | ST | Reconexión automática tras caída del broker | Alta | ✅ | ✅ Pasó |
| TC-E5-02 | E5 | US-E5-02 | DT | JSON inválido → ACK + descartado (ver política §7.2) | Alta | ✅ | ✅ Pasó |
| TC-E5-03 | E5 | US-E5-02 | DT | Error inesperado → NACK → DLQ | Alta | ✅ | ✅ Pasó |
| TC-NEG-01 | E2 | — | Negativa | POST /api/notifications/ → 405 Method Not Allowed | Alta | ✅ | ✅ Pasó |
| TC-NEG-02 | E2 | — | Negativa | PUT /api/notifications/{id}/ → 405 | Alta | ✅ | ✅ Pasó |

**Leyenda:**
- **Auto:** ✅ = automatizado en pytest | ⏳ = pendiente de automatización
- **Resultado:** ✅ Pasó | ❌ Falló | ⏳ Pendiente | 🔄 Re-test
- **Técnica:** EP = Partición de Equivalencia | BVA = Análisis de Valores Límite | ST = Transición de Estados | DT = Tabla de Decisiones | Negativa = Prueba negativa

**Ejemplo con capturas de pantalla evidenciando códigos de estado**

**GET — Listar todas las notificaciones - fallida - 401**
<img width="1350" height="485" alt="image" src="https://github.com/user-attachments/assets/52ea511e-f503-40a0-a94b-a5226eda0f1d" />

**GET — Listar todas las notificaciones - exitosa - 200**
<img width="1351" height="676" alt="image" src="https://github.com/user-attachments/assets/d1bda6df-9d7b-4195-94a1-b858ea9122f9" />

**GET - Notificación inexistente - fallida - 404**
<img width="1355" height="497" alt="image" src="https://github.com/user-attachments/assets/cae4add7-a7e1-43e7-ac80-089d868dd6fb" />

**DEL - Eliminar notificacion individual - exitosa - 204**
<img width="1344" height="468" alt="image" src="https://github.com/user-attachments/assets/e1d65d18-5841-47b5-966b-27881d6b5abd" />

**POST - Crear notificación - fallida - 405**
<img width="1347" height="460" alt="image" src="https://github.com/user-attachments/assets/f1a226a0-f473-4583-a63c-ab26f7d9cf3d" />

---

### 13.2 Casos Gherkin — EPIC E1: Ingesta de Eventos de Dominio

#### TC-E1-01 a TC-E1-03: `ticket.created` (US-E1-01)

```gherkin
@epic:E1 @story:US-E1-01 @technique:EP,DT,BVA
Feature: Notificación por creación de ticket

  Background:
    Given el consumidor RabbitMQ está activo y suscrito a la cola de eventos
    And la base de datos de notificaciones está disponible

  # TC-E1-01 — Técnica: Partición de Equivalencia (evento válido)
  Scenario: Procesamiento exitoso de evento ticket.created
    Given se recibe un evento con event_type "ticket.created"
    And los campos ticket_id, title, user_id, status y timestamp están presentes y válidos
    When el consumidor procesa el mensaje
    Then se persiste una notificación con message que referencia el título del ticket
    And la notificación queda asociada al user_id del evento
    And la notificación queda en estado no leída (read: false)
    And el mensaje es confirmado con basic_ack en la cola

  # TC-E1-02 — Técnica: Tabla de Decisiones (campos ausentes)
  Scenario: Evento ticket.created con campos obligatorios ausentes
    Given se recibe un evento con event_type "ticket.created"
    And uno o más de los campos obligatorios (ticket_id, user_id, title) están ausentes
    When el consumidor intenta procesar el mensaje
    Then no se persiste ninguna notificación
    And el mensaje es rechazado con basic_nack(requeue=False) hacia la DLQ
    And se registra un log de nivel ERROR con el motivo del rechazo

  # TC-E1-03 — Técnica: BVA (contenido del mensaje generado)
  Scenario Outline: Contenido del mensaje de notificación generado
    Given se recibe un evento ticket.created con title "<title>" y ticket_id <ticket_id>
    When el consumidor procesa el mensaje exitosamente
    Then el message de la notificación contiene el título "<title>"
    And el ticket_id almacenado en la notificación es <ticket_id>

    Examples:
      | title                | ticket_id |
      | Error en facturación | 101       |
      | Solicitud de acceso  | 202       |
```

#### TC-E1-04 a TC-E1-09: `ticket.response_added` (US-E1-02, US-E1-05)

```gherkin
@epic:E1 @story:US-E1-02,US-E1-05 @technique:EP,DT,BVA
Feature: Notificación por respuesta agregada a ticket

  Background:
    Given el consumidor RabbitMQ está activo y suscrito a la cola de eventos
    And la base de datos de notificaciones está disponible

  # TC-E1-04 — Técnica: Partición de Equivalencia (evento válido)
  Scenario: Procesamiento exitoso de evento ticket.response_added
    Given se recibe un evento con event_type "ticket.response_added"
    And los campos ticket_id, response_id, admin_id, response_text, user_id y timestamp están presentes
    When el consumidor procesa el mensaje
    Then se persiste una notificación asociada al user_id del evento
    And el campo response_id queda almacenado internamente como clave de idempotencia
    And la notificación queda en estado no leída (read: false)
    And el mensaje es confirmado con basic_ack en la cola

  # TC-E1-05 — Técnica: Tabla de Decisiones (campos ausentes → InvalidEventSchema)
  Scenario Outline: Evento ticket.response_added con campos obligatorios ausentes
    Given se recibe un evento con event_type "ticket.response_added"
    And el campo "<campo_ausente>" está ausente del payload
    When el consumidor intenta procesar el mensaje
    Then se lanza InvalidEventSchema con el campo "<campo_ausente>" en el mensaje de error
    And no se persiste ninguna notificación
    And el mensaje es confirmado con basic_ack (descartado, no va a DLQ)
    And se registra un log de nivel ERROR

    Examples:
      | campo_ausente |
      | ticket_id     |
      | response_id   |
      | user_id       |

  # TC-E1-06 — Técnica: Partición de Equivalencia (response_text vacío)
  Scenario: El texto de respuesta está vacío
    Given se recibe un evento ticket.response_added con response_text vacío ""
    And los demás campos obligatorios están presentes
    When el consumidor procesa el mensaje
    Then se persiste la notificación sin incluir texto de respuesta en el message
    And la notificación queda correctamente asociada al ticket_id y user_id

  # TC-E1-07 — Técnica: BVA (response_text en el límite)
  Scenario: El texto de respuesta supera el límite de caracteres permitido
    Given se recibe un evento ticket.response_added con response_text de más de 255 caracteres
    When el consumidor procesa el mensaje
    Then se persiste la notificación con el message truncado o adaptado al límite disponible
    And no se lanza ningún error de validación

  # TC-E1-08 — Técnica: EP (idempotencia EP22-B)
  Scenario: El mismo response_id es recibido dos veces (duplicado)
    Given existe ya una notificación para ticket_id 101 con response_id 55
    When se recibe nuevamente un evento ticket.response_added con ticket_id 101 y response_id 55
    Then no se crea una nueva notificación
    And el mensaje es confirmado con basic_ack en la cola
    And el total de notificaciones para ticket_id 101 con response_id 55 es exactamente 1

  # TC-E1-09 — Técnica: EP (dos response_id distintos no son duplicados)
  Scenario: Dos respuestas distintas al mismo ticket no son duplicados
    Given existe una notificación para ticket_id 101 con response_id 55
    When se recibe un evento ticket.response_added con ticket_id 101 y response_id 56
    Then se persiste una nueva notificación para response_id 56
    And ambas notificaciones coexisten en la base de datos
```

#### TC-E1-10 a TC-E1-12: `ticket.status_changed` (US-E1-03)

```gherkin
@epic:E1 @story:US-E1-03 @technique:EP,DT @blocked:DT-09
Feature: Notificación por cambio de estado de ticket

  Background:
    Given el consumidor RabbitMQ está activo y suscrito a la cola de eventos
    And la base de datos de notificaciones está disponible

  # TC-E1-10 — Técnica: EP (evento válido — estado objetivo post DT-09)
  # ⏳ PENDIENTE: Requiere que ticket-service incluya user_id en el contrato
  Scenario: Procesamiento exitoso de evento ticket.status_changed (estado objetivo)
    Given se recibe un evento con event_type "ticket.status_changed"
    And los campos ticket_id, new_status, user_id y timestamp están presentes
    When el consumidor procesa el mensaje
    Then se persiste una notificación asociada al user_id del evento
    And el message incluye el nuevo estado del ticket
    And la notificación queda en estado no leída (read: false)
    And el mensaje es confirmado con basic_ack en la cola

  # TC-E1-11 — Técnica: EP + Scenario Outline (variaciones de estado)
  # ⏳ PENDIENTE: Requiere resolución de DT-09
  Scenario Outline: Notificación generada según el nuevo estado
    Given se recibe un evento ticket.status_changed con new_status "<new_status>" y ticket_id <ticket_id>
    When el consumidor procesa el mensaje
    Then el message de la notificación menciona el estado "<new_status>"

    Examples:
      | new_status  | ticket_id |
      | in_progress | 301       |
      | closed      | 302       |
      | open        | 303       |

  # TC-E1-12 — Técnica: DT (comportamiento actual — sin user_id en contrato)
  # ⏳ PENDIENTE: Documenta el comportamiento actual bloqueado por R11/DT-09
  Scenario: Evento ticket.status_changed sin user_id (comportamiento actual)
    Given el consumer está activo y conectado a RabbitMQ
    When llega un evento con event_type "ticket.status_changed"
    And el payload contiene ticket_id, old_status, new_status y timestamp
    And el campo user_id NO está presente en el payload
    Then el consumer crea una notificación con user_id vacío
    And la notificación NO es entregada via SSE (sin user_id para filtrar)
    And se registra un log indicando la ausencia de user_id
```

#### TC-E1-13 a TC-E1-15: `ticket.priority_changed` (US-E1-04)

```gherkin
@epic:E1 @story:US-E1-04 @technique:EP,Negativa
Feature: Notificación por cambio de prioridad de ticket

  Background:
    Given el consumidor RabbitMQ está activo y suscrito a la cola de eventos
    And la base de datos de notificaciones está disponible

  # TC-E1-13 — Técnica: EP (evento válido)
  Scenario: Procesamiento exitoso de evento ticket.priority_changed
    Given se recibe un evento con event_type "ticket.priority_changed"
    And los campos ticket_id, new_priority, user_id y timestamp están presentes
    When el consumidor procesa el mensaje
    Then se persiste una notificación asociada al user_id del evento
    And el message incluye la nueva prioridad del ticket
    And la notificación queda en estado no leída (read: false)
    And el mensaje es confirmado con basic_ack en la cola

  # TC-E1-14 — Técnica: EP + Scenario Outline (variaciones de prioridad)
  Scenario Outline: Notificación generada según la nueva prioridad
    Given se recibe un evento ticket.priority_changed con new_priority "<new_priority>"
    When el consumidor procesa el mensaje
    Then el message de la notificación menciona la prioridad "<new_priority>"

    Examples:
      | new_priority |
      | high         |
      | medium       |
      | low          |

  # TC-E1-15 — Técnica: Prueba Negativa (prioridad fuera de catálogo)
  Scenario: Evento ticket.priority_changed con prioridad inválida
    Given se recibe un evento con new_priority "critical"
    When el consumidor intenta procesar el mensaje
    Then no se persiste ninguna notificación
    And el mensaje es rechazado hacia la DLQ
    And se registra un log de error indicando prioridad inválida
```

#### TC-E1-16 a TC-E1-17: Idempotencia transversal (US-E1-05)

```gherkin
@epic:E1 @story:US-E1-05 @technique:EP @idempotency:EP22+
Feature: Idempotencia en la creación de notificaciones

  Background:
    Given el consumidor RabbitMQ está activo
    And la base de datos de notificaciones está disponible

  # TC-E1-16 — Técnica: EP (duplicado de ticket.created → descartado)
  # ⏳ PENDIENTE: DT-01 — no hay use case; consumer usa ORM directo sin verificación
  Scenario: Evento duplicado ticket.created es descartado
    Given existe ya una notificación para ticket_id 101 con event_type "ticket.created"
    When se recibe nuevamente un evento con ticket_id 101 y event_type "ticket.created"
    Then no se crea una nueva notificación
    And el mensaje es confirmado con basic_ack en la cola
    And se registra un log de advertencia indicando evento duplicado

  # TC-E1-17 — Técnica: EP (mismo ticket_id, distinto event_type → NO es duplicado)
  Scenario: Evento del mismo ticket_id pero distinto event_type no es duplicado
    Given existe una notificación para ticket_id 101 con event_type "ticket.created"
    When se recibe un evento con ticket_id 101 y event_type "ticket.status_changed"
    Then se persiste una nueva notificación para ticket_id 101
    And ambas notificaciones coexisten en la base de datos
```

---

### 13.3 Casos Gherkin — EPIC E2: Consulta de Notificaciones vía REST

```gherkin
@epic:E2 @story:US-E2-01,US-E2-02 @technique:EP,BVA,Negativa
Feature: Consulta de notificaciones por API REST

  Background:
    Given la API REST del notification-service está disponible

  # TC-E2-01 — Técnica: EP (listado con datos)
  Scenario: Listado exitoso con notificaciones existentes
    Given existen 3 notificaciones persistidas en el sistema
    When el frontend realiza un GET a /api/notifications/
    Then la respuesta tiene código HTTP 200
    And el body contiene una lista con 3 notificaciones
    And cada notificación incluye los campos: id, ticket_id, message, read, sent_at
    And la primera notificación de la lista es la más reciente (orden descendente por sent_at)

  # TC-E2-02 — Técnica: BVA (lista vacía — valor límite 0 elementos)
  Scenario: Listado exitoso con bandeja vacía
    Given no existe ninguna notificación en el sistema
    When el frontend realiza un GET a /api/notifications/
    Then la respuesta tiene código HTTP 200
    And el body contiene una lista vacía []

  # TC-E2-03 — Técnica: EP (detalle por ID)
  Scenario: Consulta exitosa de notificación existente
    Given existe una notificación con id 42
    When el frontend realiza un GET a /api/notifications/42/
    Then la respuesta tiene código HTTP 200
    And el body contiene los campos: id, ticket_id, message, read, sent_at
    And el campo id del body es 42

  # TC-E2-04 — Técnica: Prueba Negativa (ID inexistente)
  Scenario: Consulta de notificación inexistente
    Given no existe ninguna notificación con id 999
    When el frontend realiza un GET a /api/notifications/999/
    Then la respuesta tiene código HTTP 404
    And el body contiene un mensaje de error descriptivo
```

---

### 13.4 Casos Gherkin — EPIC E3: Gestión del Estado de Lectura

```gherkin
@epic:E3 @story:US-E3-01 @technique:ST,Negativa
Feature: Marcar notificación como leída

  Background:
    Given la API REST del notification-service está disponible

  # TC-E3-01 — Técnica: Transición de Estados (read: false → true)
  Scenario: Marcar como leída una notificación no leída
    Given existe una notificación con id 42 en estado no leída (read: false)
    When el frontend realiza un PATCH a /api/notifications/42/read/
    Then la respuesta tiene código HTTP 200
    And el body contiene la notificación actualizada con read: true
    And el evento de dominio NotificationMarkedAsRead es generado

  # TC-E3-02 — Técnica: Transición de Estados (idempotencia — ya leída)
  Scenario: Marcar como leída una notificación ya leída es idempotente
    Given existe una notificación con id 42 en estado leída (read: true)
    When el frontend realiza un PATCH a /api/notifications/42/read/
    Then la respuesta tiene código HTTP 200
    And el body contiene la notificación con read: true sin cambios
    And NO se genera un segundo evento NotificationMarkedAsRead

  # TC-E3-03 — Técnica: Prueba Negativa (id inexistente)
  Scenario: Intentar marcar como leída una notificación inexistente
    Given no existe ninguna notificación con id 999
    When el frontend realiza un PATCH a /api/notifications/999/read/
    Then la respuesta tiene código HTTP 404
    And el body contiene un mensaje de error descriptivo
```

---

### 13.5 Casos Gherkin — EPIC E4: Eliminación de Notificaciones

```gherkin
@epic:E4 @story:US-E4-01,US-E4-02 @technique:EP,ST,Negativa
Feature: Eliminación de notificaciones

  Background:
    Given la API REST del notification-service está disponible

  # TC-E4-01 — Técnica: EP (eliminación individual exitosa)
  Scenario: Eliminación exitosa de notificación existente
    Given existe una notificación con id 42
    When el frontend realiza un DELETE a /api/notifications/42/
    Then la respuesta tiene código HTTP 204
    And el body está vacío
    And un GET posterior a /api/notifications/42/ retorna 404

  # TC-E4-02 — Técnica: Prueba Negativa (id inexistente)
  Scenario: Intentar eliminar una notificación inexistente
    Given no existe ninguna notificación con id 999
    When el frontend realiza un DELETE a /api/notifications/999/
    Then la respuesta tiene código HTTP 404

  # TC-E4-03 — Técnica: EP (clear all con datos)
  Scenario: Clear all con notificaciones existentes
    Given existen 5 notificaciones en el sistema
    When el frontend realiza un DELETE a /api/notifications/clear/
    Then la respuesta tiene código HTTP 204
    And el body está vacío
    And un GET posterior a /api/notifications/ retorna una lista vacía []

  # TC-E4-04 — Técnica: Transición de Estados (clear all idempotente)
  Scenario: Clear all con bandeja ya vacía es idempotente
    Given no existe ninguna notificación en el sistema
    When el frontend realiza un DELETE a /api/notifications/clear/
    Then la respuesta tiene código HTTP 204
    And no se genera ningún error
```

---

### 13.6 Casos Gherkin — EPIC E5: Resiliencia del Consumidor RabbitMQ

```gherkin
@epic:E5 @story:US-E5-01,US-E5-02 @technique:ST,DT
Feature: Resiliencia del consumidor RabbitMQ

  # TC-E5-01 — Técnica: Transición de Estados (connected → disconnected → reconnecting → connected)
  Scenario: Reconexión exitosa tras caída temporal del broker
    Given el consumidor está activo y procesando eventos
    When el broker RabbitMQ se vuelve inaccesible
    Then el consumidor detecta la pérdida de conexión
    And el consumidor intenta reconectarse con backoff exponencial
    And cuando el broker vuelve a estar disponible el consumidor restablece la conexión
    And el consumidor retoma el procesamiento de mensajes sin intervención manual
    And se registra un log de advertencia por cada intento de reconexión fallido

  # TC-E5-02 — Técnica: Tabla de Decisiones (política ACK/NACK — ver §7.2)
  Scenario: Mensaje con JSON inválido es descartado con ACK
    Given se recibe un mensaje cuyo body no es JSON válido
    When el consumidor intenta deserializar el mensaje
    Then el mensaje es confirmado con basic_ack (descartado)
    And se registra un log de nivel ERROR
    And el consumidor continúa procesando el siguiente mensaje
    And el mensaje NO es enviado a la DLQ

  # TC-E5-03 — Técnica: Tabla de Decisiones (error inesperado → DLQ)
  Scenario: Error inesperado del sistema envía mensaje a DLQ
    Given se recibe un mensaje estructuralmente válido
    When ocurre una excepción no controlada durante el procesamiento
    Then el mensaje es rechazado con basic_nack(requeue=False)
    And el mensaje es enrutado a la Dead Letter Queue ({queue}.dlq)
    And el proceso del consumidor NO termina
    And se registra un log de nivel ERROR con el stack trace del fallo
```

---

### 13.7 Casos Gherkin — Pruebas Negativas Transversales (DDD: Bloqueo HTTP)

```gherkin
@epic:E2 @technique:Negativa @architecture:DDD
Feature: Bloqueo de operaciones HTTP de creación (regla arquitectónica DDD)

  Las notificaciones solo se crean mediante eventos de dominio vía RabbitMQ.
  Los métodos HTTP de creación/modificación directa están bloqueados por diseño.

  Background:
    Given la API REST del notification-service está disponible

  # TC-NEG-01 — Técnica: Prueba Negativa (POST bloqueado)
  Scenario: POST a /api/notifications/ retorna 405 Method Not Allowed
    When el frontend realiza un POST a /api/notifications/ con un body JSON válido
    Then la respuesta tiene código HTTP 405
    And el body indica que el método no está permitido

  # TC-NEG-02 — Técnica: Prueba Negativa (PUT bloqueado)
  Scenario: PUT a /api/notifications/{id}/ retorna 405 Method Not Allowed
    Given existe una notificación con id 42
    When el frontend realiza un PUT a /api/notifications/42/ con un body JSON
    Then la respuesta tiene código HTTP 405
    And la notificación original no es modificada
```

---

### 13.8 Trazabilidad: US → Caso Gherkin → Test pytest → Técnica

Tabla de trazabilidad completa que vincula cada historia de usuario con los casos Gherkin diseñados, el test automatizado en pytest que lo cubre, y la técnica ISTQB aplicada:

| US | Caso Gherkin | Técnica ISTQB | Test pytest | Estado |
|----|-------------|---------------|-------------|--------|
| US-E1-01 | TC-E1-01 | EP | `test_consumer_dispatch::test_callback_handles_ticket_created_normally` | ✅ |
| US-E1-01 | TC-E1-02 | DT | `test_consumer_dispatch::test_callback_logs_error_on_invalid_response_event` | ✅ |
| US-E1-01 | TC-E1-03 | BVA | `test_consumer_dispatch::test_callback_handles_ticket_created_normally` | ✅ |
| US-E1-02 | TC-E1-04 | EP | `test_response_handler::test_create_notification_from_valid_response_event` | ✅ |
| US-E1-02 | TC-E1-05 | DT | `test_response_handler::test_event_missing_ticket_id_raises_invalid_schema` | ✅ |
| US-E1-02 | TC-E1-06 | EP | `test_response_handler::test_create_notification_from_valid_response_event` | ✅ |
| US-E1-02 | TC-E1-07 | BVA | `test_response_handler::test_create_notification_message_format` | ✅ |
| US-E1-05 | TC-E1-08 | EP | `test_response_handler::test_duplicate_response_id_does_not_create_second_notification` | ✅ |
| US-E1-02 | TC-E1-09 | EP | `test_response_handler::test_first_event_with_response_id_calls_find_and_save` | ✅ |
| US-E1-03 | TC-E1-10 | EP | ⏳ Pendiente (DT-09) | ⏳ |
| US-E1-03 | TC-E1-11 | EP/Outline | ⏳ Pendiente (DT-09) | ⏳ |
| US-E1-03 | TC-E1-12 | DT | ⏳ Pendiente (R11/DT-09) | ⏳ |
| US-E1-04 | TC-E1-13 | EP | `test_consumer_dispatch::test_callback_handles_ticket_created_normally` | ✅ |
| US-E1-04 | TC-E1-14 | EP/Outline | `test_consumer_dispatch::test_callback_handles_ticket_created_normally` | ✅ |
| US-E1-04 | TC-E1-15 | Negativa | `test_consumer_dispatch::test_callback_logs_error_on_invalid_response_event` | ✅ |
| US-E1-05 | TC-E1-16 | EP | ⏳ Pendiente (DT-01) | ⏳ |
| US-E1-05 | TC-E1-17 | EP | `test_consumer_dispatch::test_callback_handles_ticket_created_normally` | ✅ |
| US-E2-01 | TC-E2-01 | EP | `test_infrastructure::test_find_all` | ✅ |
| US-E2-01 | TC-E2-02 | BVA | `test_infrastructure::test_find_all` (empty) | ✅ |
| US-E2-02 | TC-E2-03 | EP | `test_infrastructure::test_find_by_id_existing` | ✅ |
| US-E2-02 | TC-E2-04 | Negativa | `test_infrastructure::test_find_by_id_not_found` | ✅ |
| US-E3-01 | TC-E3-01 | ST | `test_views::test_read_action_success` | ✅ |
| US-E3-01 | TC-E3-02 | ST | `test_domain::test_mark_as_read_is_idempotent` | ✅ |
| US-E3-01 | TC-E3-03 | Negativa | `test_views::test_read_action_not_found` | ✅ |
| US-E4-01 | TC-E4-01 | EP | `test_integration` (infraestructura) | ✅ |
| US-E4-01 | TC-E4-02 | Negativa | `test_infrastructure::test_find_by_id_not_found` | ✅ |
| US-E4-02 | TC-E4-03 | EP | `test_integration` (infraestructura) | ✅ |
| US-E4-02 | TC-E4-04 | ST | `test_integration` (infraestructura) | ✅ |
| US-E5-01 | TC-E5-01 | ST | `test_consumer_reconnection` | ✅ |
| US-E5-02 | TC-E5-02 | DT | `test_dead_letter_queue` | ✅ |
| US-E5-02 | TC-E5-03 | DT | `test_dead_letter_queue` | ✅ |
| — | TC-NEG-01 | Negativa | `test_views` (405 assertions) | ✅ |
| — | TC-NEG-02 | Negativa | `test_views` (405 assertions) | ✅ |

---

### 13.9 Resumen de Cobertura por Técnica

| Técnica ISTQB | Casos | % del Total |
|---------------|-------|-------------|
| **Partición de Equivalencia (EP)** | 16 | 47% |
| **Tabla de Decisiones (DT)** | 5 | 15% |
| **Análisis de Valores Límite (BVA)** | 4 | 12% |
| **Transición de Estados (ST)** | 5 | 15% |
| **Pruebas Negativas** | 4 | 12% |
| **Total** | **34** | **100%** |

### 13.10 Resumen de Cobertura por Épica

| Épica | Casos | Pasaron | Pendientes | Fallaron |
|-------|-------|---------|------------|----------|
| **E1 — Ingesta de Eventos** | 17 | 12 | 5 (DT-01, DT-09) | 0 |
| **E2 — Consulta REST** | 4 | 4 | 0 | 0 |
| **E3 — Estado de Lectura** | 3 | 3 | 0 | 0 |
| **E4 — Eliminación** | 4 | 4 | 0 | 0 |
| **E5 — Resiliencia** | 3 | 3 | 0 | 0 |
| **Negativas transversales** | 2 | 2 | 0 | 0 |
| **Infraestructura (E6)** | — | — | — | — |
| **Total** | **33** | **28** | **5** | **0** |

> **Nota sobre E6 (Infraestructura):** Los escenarios de US-INFRA-01 (Dockerfile), US-INFRA-02 (docker-compose) y US-INFRA-03 (CI pipeline) están documentados en `USERSTORIES Y CRITERIOS DE ACEPTACION.md` con sus Gherkin completos. No se incluyen en esta matriz porque son verificados por inspección de artefactos (Dockerfile, docker-compose.yml, ci.yml) y no por pytest. Su ejecución se registra en el pipeline CI de GitHub Actions.

---

**📋 Plan de Pruebas v3.2 — Backend Notification Service**  
*Actualizado: 26 de Febrero de 2026*
