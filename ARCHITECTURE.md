# ARCHITECTURE.md — Debate Arquitectónico
## Notification Service · Taller Semana 3 · Sofka Training Leagues

---

## 📋 Tabla de Contenidos

1. [Contexto del Sistema Original](#1-contexto-del-sistema-original)
2. [Análisis del Monolito Heredado](#2-análisis-del-monolito-heredado)
3. [Diagnóstico de Dolores del Monolito](#3-diagnóstico-de-dolores-del-monolito)
4. [La Migración Realizada — DDD Pragmático](#4-la-migración-realizada--ddd-pragmático)
5. [Contraste Teórico — Monolito vs Clean Architecture](#5-contraste-teórico--monolito-vs-clean-architecture)
6. [Mapa de Capas Actual](#6-mapa-de-capas-actual)
7. [Reglas Arquitectónicas No Negociables](#7-reglas-arquitectónicas-no-negociables)
8. [Contrato de API REST](#8-contrato-de-api-rest)
9. [Contrato de Eventos RabbitMQ](#9-contrato-de-eventos-rabbitmq)
10. [Deuda Técnica Remanente](#10-deuda-técnica-remanente)
11. [Conclusiones](#11-conclusiones)

---

## 1. Contexto del Sistema Original

El sistema **SistemaTickets** nació como un **monorepo monolítico** bajo el repositorio
`equipo-6-uruguay/SistemaTickets`. En esa estructura, todos los servicios —gestión de
tickets, autenticación, notificaciones— convivían en un único proyecto Django, compartiendo:

- Una sola base de datos PostgreSQL
- Un único proceso de servidor (Gunicorn/Runserver)
- Un único `settings.py` con toda la configuración
- Modelos ORM con relaciones directas entre dominios distintos
- Lógica de negocio mezclada en vistas, serializers y modelos

El `notification-service` fue extraído de ese monorepo como parte del proceso de
separación en microservicios independientes, resultando en este repositorio:
`equipo-6-uruguay/backend-notification-service`.

---

## 2. Análisis del Monolito Heredado

### 2.1 Estructura original (antes de refactorizar)

```
SistemaTickets/                        ← Monorepo
├── tickets/
│   ├── models.py                      ← Ticket, Response, User (todo junto)
│   ├── views.py                       ← Lógica de negocio + presentación
│   ├── serializers.py
│   └── urls.py
├── notifications/
│   ├── models.py                      ← Notification con FK directa a Ticket
│   ├── views.py                       ← CRUD + lógica mezclada
│   └── tests.py                       ← Tests sin estructura
├── settings.py                        ← Configuración única para todo
└── manage.py
```

### 2.2 Características del monolito identificadas

| Característica | Descripción | Evidencia en el código |
|---|---|---|
| **Acoplamiento de dominio** | `Notification` tenía FK directa al modelo `Ticket` | `models.py` original |
| **Lógica en vistas** | Las views contenían reglas de negocio | `views.py` sin separación |
| **Acceso directo al ORM** | Los handlers de mensajería llamaban `Notification.objects.create()` directamente | `consumer.py` pre-refactor |
| **Base de datos compartida** | Todos los servicios usaban la misma DB | `settings.py` único |
| **Sin capa de dominio** | No existían entidades de dominio puras | Ausencia de `/domain` |
| **Sin abstracción de repositorio** | Los modelos Django eran el repositorio | Sin interfaz ABC |
| **Configuración hardcodeada** | Hosts, queues y secrets en el código | Variables literales en código |

---

## 3. Diagnóstico de Dolores del Monolito

### 🔴 Dolor 1 — Acoplamiento Total entre Servicios

**Problema:**
En el monolito, el módulo de notificaciones accedía directamente a los modelos
del módulo de tickets mediante Foreign Keys de Django ORM.

```python
# ANTES — Notification acoplada al modelo Ticket del mismo proyecto
class Notification(models.Model):
    ticket = models.ForeignKey('tickets.Ticket', on_delete=models.CASCADE)
    message = models.TextField()
```

**Consecuencia:**
- Imposible desplegar `notifications` sin desplegar `tickets`
- Un cambio en el modelo `Ticket` rompía `Notification` inmediatamente
- Imposible escalar los servicios de forma independiente
- Los tests de notificaciones requerían datos de tickets

**Impacto:** 🔴 Crítico — Bloquea la separación en microservicios

---

### 🔴 Dolor 2 — Lógica de Negocio en la Capa de Presentación

**Problema:**
Las vistas Django (`views.py`) contenían decisiones de negocio: validaciones,
construcción de mensajes, reglas de idempotencia.

```python
# ANTES — Regla de negocio en la vista
def create(self, request):
    ticket_id = request.data.get('ticket_id')
    # Lógica de negocio directamente en el ViewSet
    if Notification.objects.filter(ticket_id=ticket_id).exists():
        return Response({'error': 'ya existe'}, status=400)
    Notification.objects.create(...)
```

**Consecuencia:**
- No se podía reutilizar la lógica desde el consumer de RabbitMQ
- Tests de negocio requerían hacer requests HTTP
- Cambiar el framework web implicaba reescribir lógica de negocio

**Impacto:** 🔴 Crítico — Duplicación de lógica, tests frágiles

---

### 🟠 Dolor 3 — Consumer de Mensajería Bypasseando el Dominio

**Problema:**
El handler `_handle_ticket_created` en `consumer.py` accedía directamente al ORM
de Django, saltando completamente las capas de dominio y aplicación.

```python
# ANTES (y parcialmente presente aún) — ORM directo en mensajería
def _handle_ticket_created(data: dict) -> None:
    Notification.objects.create(
        ticket_id=str(data.get('ticket_id')),
        message=f"Nuevo Ticket #{data.get('ticket_id')}",
    )
```

**Consecuencia:**
- La lógica de construcción del mensaje estaba duplicada
- No había validación de schema del evento
- No había garantía de idempotencia desde el consumer
- Imposible testear sin base de datos real

**Impacto:** 🟠 Importante — Viola el contrato arquitectónico DDD

---

### 🟠 Dolor 4 — Ausencia de Abstracción de Repositorio

**Problema:**
No existía interfaz entre la lógica de negocio y el mecanismo de persistencia.
El ORM de Django era el repositorio, sin posibilidad de sustitución.

**Consecuencia:**
- Imposible hacer tests unitarios sin base de datos
- Cambiar de PostgreSQL a otra DB requería tocar lógica de negocio
- Sin contrato claro sobre qué operaciones de persistencia existen

**Impacto:** 🟠 Importante — Tests lentos, alta fragilidad

---

### 🟡 Dolor 5 — Configuración Acoplada al Entorno de Producción

**Problema:**
Un único `settings.py` para todos los entornos. Los tests corrían con la
configuración de producción, incluyendo conexión real a RabbitMQ.

```python
# ANTES — Sin separación de settings
RABBITMQ_HOST = 'rabbitmq'          # hardcodeado
DATABASES = { ... }                  # producción en tests
```

**Consecuencia:**
- Tests fallaban en CI por ausencia de RabbitMQ
- Riesgo de tests que modifican datos de producción
- Sin `test_settings.py` separado

**Impacto:** 🟡 Recomendado — Pipeline CI roto

---

### 🟡 Dolor 6 — Sin Separación de Responsabilidades en Tests

**Problema:**
Archivo `notifications/tests.py` único en la raíz de la app, mezclando pruebas
de dominio, integración y vistas sin estructura ni separación.

**Consecuencia:**
- Test discovery conflictivo con la carpeta `tests/`
- Imposible correr solo tests unitarios vs integración
- Sin cobertura medible por capa

**Impacto:** 🟡 Recomendado — Conflictos en pytest

---

## 4. La Migración Realizada — DDD Pragmático

Como respuesta a los dolores identificados, el servicio fue refactorizado a una
arquitectura de **DDD Pragmático** con separación explícita de capas:

### 4.1 Estructura resultante

```
notifications/
├── domain/                    ← Python puro — CERO imports de Django
│   ├── entities.py            ← Notification como entidad de dominio
│   ├── repositories.py        ← Interfaz ABC NotificationRepository
│   ├── events.py              ← Eventos de dominio (value objects)
│   └── exceptions.py          ← Excepciones de dominio tipadas
│
├── application/               ← Casos de uso — orquesta dominio
│   └── use_cases.py           ← CreateNotificationFromResponseUseCase
│                              ← (pendiente: CreateNotificationFromTicketCreatedUseCase)
│
├── infrastructure/            ← Adaptadores concretos
│   ├── repository.py          ← DjangoNotificationRepository implements ABC
│   └── publisher.py           ← RabbitMQEventPublisher
│
├── messaging/                 ← Entrada por eventos
│   └── consumer.py            ← Dispatcher → delega a Use Cases
│
├── models.py                  ← ORM Django (solo persistencia)
├── serializers.py             ← DRF (solo serialización)
└── api.py                     ← ViewSet thin controller
```

### 4.2 Flujo de dependencias (Dependency Rule)

```
api.py / consumer.py
        ↓
  application/use_cases.py
        ↓
  domain/entities.py + domain/repositories.py (ABC)
        ↑
  infrastructure/repository.py (implementación concreta)
```

> **Regla de oro:** Las flechas de dependencia apuntan **siempre hacia adentro**.
> El dominio no conoce Django. La aplicación no conoce RabbitMQ.

---

## 5. Contraste Teórico — Monolito vs Clean Architecture

### 5.1 Tabla comparativa

| Dimensión | Monolito Original | DDD Pragmático Actual | Clean Architecture Ideal |
|---|---|---|---|
| **Separación de capas** | ❌ Sin capas explícitas | ✅ 4 capas definidas | ✅ Capas con fronteras estrictas |
| **Independencia del framework** | ❌ Django en todo | 🟡 Django en infra/api | ✅ Framework intercambiable |
| **Testabilidad unitaria** | ❌ Requiere DB | ✅ Domain testeable solo | ✅ Todo testeable con mocks |
| **Independencia de DB** | ❌ ORM acoplado | ✅ Via Repository ABC | ✅ Completamente intercambiable |
| **Reglas de negocio** | ❌ En vistas | ✅ En use_cases/domain | ✅ Solo en dominio |
| **Escalabilidad independiente** | ❌ Todo o nada | ✅ Servicio independiente | ✅ Módulos independientes |
| **Comunicación entre servicios** | ❌ DB compartida | ✅ REST + eventos | ✅ Contratos explícitos |
| **Onboarding** | ❌ Difícil, todo acoplado | 🟡 Estructura clara | ✅ Fronteras autodocumentadas |
| **Tiempo de build/test** | ❌ Tests lentos (DB real) | 🟡 Parcialmente rápido | ✅ Tests unitarios ms |
| **Gestión de cambio** | ❌ Cambio = riesgo global | ✅ Cambio contenido | ✅ Impacto predecible |

### 5.2 Beneficios teóricos de Clean Architecture sobre el monolito

#### Independencia de Frameworks
> *"El framework es un detalle."* — Robert C. Martin, Clean Architecture

En un monolito Django puro, cambiar de Django a FastAPI implicaría reescribir
toda la lógica de negocio. En Clean Architecture, el dominio y los casos de uso
son Python puro: el framework es solo el mecanismo de entrega.

#### La Regla de Dependencia
La única regla fundamental: **el código fuente solo puede apuntar hacia adentro**.

```
[Frameworks & Drivers]
        ↓
[Interface Adapters]
        ↓
[Application Business Rules]
        ↓
[Enterprise Business Rules]  ← nada apunta hacia afuera desde aquí
```

#### Testabilidad por diseño
Con repositorios como interfaces ABC, cada caso de uso puede testearse con un
repositorio en memoria sin necesidad de base de datos real:

```python
# Posible gracias a la abstracción ABC
repo = InMemoryNotificationRepository()
use_case = CreateNotificationFromResponseUseCase(repository=repo)
use_case.execute(command)
assert len(repo.all()) == 1
```

#### Casos de uso como documentación viva
Cada `UseCase` en la capa de aplicación documenta explícitamente qué puede
hacer el sistema. En el monolito, esta información estaba oculta en vistas.

### 5.3 Trade-offs honestos

| Trade-off | Monolito | Clean Architecture |
|---|---|---|
| **Velocidad inicial de desarrollo** | ✅ Más rápido al principio | 🟡 Más setup inicial |
| **Complejidad de estructura** | ✅ Simple | 🟡 Más archivos, más capas |
| **Curva de aprendizaje** | ✅ Cualquier dev Django lo entiende | 🟡 Requiere entender DDD |
| **Over-engineering para servicios pequeños** | ✅ Sin overhead | ⚠️ Puede ser excesivo para CRUD puro |
| **Consistencia a largo plazo** | ❌ Se degrada rápido | ✅ Se mantiene con disciplina |

---

## 6. Mapa de Capas Actual

```
┌─────────────────────────────────────────────────────────────┐
│                    ENTRYPOINTS                              │
│  ┌─────────────────────┐   ┌─────────────────────────────┐  │
│  │   api.py            │   │   messaging/consumer.py     │  │
│  │   (REST ViewSet)    │   │   (RabbitMQ Dispatcher)     │  │
│  └──────────┬──────────┘   └──────────────┬──────────────┘  │
└─────────────┼────────────────────────────┼─────────────────┘
              ↓                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  APPLICATION LAYER                          │
│   CreateNotificationFromResponseUseCase                     │
│   CreateNotificationFromTicketCreatedUseCase  ← (pendiente) │
└─────────────────────────┬───────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                    DOMAIN LAYER                             │
│   entities.py  │  repositories.py (ABC)                    │
│   events.py    │  exceptions.py                            │
│                                                             │
│   ✅ CERO imports de Django                                 │
└─────────────────────────┬───────────────────────────────────┘
                          ↑ (implementa ABC)
┌─────────────────────────────────────────────────────────────┐
│                 INFRASTRUCTURE LAYER                        │
│   DjangoNotificationRepository  (implements ABC)           │
│   RabbitMQEventPublisher                                    │
│   models.py (ORM)  │  serializers.py (DRF)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Reglas Arquitectónicas No Negociables

Estas reglas aplican a **todo código nuevo** en este servicio:

| # | Regla | Razón |
|---|---|---|
| **R1** | `domain/` debe ser Python puro — sin imports de Django | Independencia de framework |
| **R2** | Lógica de negocio solo en `domain/` y `application/` | Nunca en Views ni en handlers |
| **R3** | Handlers de mensajería siempre delegan a Use Cases | Consumer no contiene lógica |
| **R4** | Servicios se comunican solo por REST o eventos | Nunca por DB compartida |
| **R5** | Secrets siempre desde variables de entorno | Nunca hardcodeados en código |
| **R6** | Idempotencia garantizada en la capa de aplicación | Use Cases verifican duplicados |
| **R7** | Tests unitarios del dominio sin base de datos | Usar repositorios en memoria |

---

## 8. Contrato de API REST

### Base URL
```
/api/notifications/
```

### Decisiones sobre Verbos HTTP

| Verbo    | ¿Se usa en este servicio? | Justificación |
|----------|--------------------------|---------------|
| `GET`    | ✅ Sí | Consulta de recursos sin efectos secundarios. Idempotente. |
| `POST`   | ✅ Sí | Creación de nuevos recursos — responde `201 Created`. |
| `PATCH`  | ✅ Sí | Actualización **parcial**: solo el campo `read` cambia. Idempotente. |
| `PUT`    | ❌ No aplica | `PUT` reemplaza el recurso completo con el payload enviado. Una notificación no se reemplaza, solo se marca como leída. Aplicar `PUT` sería semánticamente incorrecto y requeriría enviar todos los campos del recurso. |
| `DELETE` | ✅ Sí | Eliminación de recursos individuales (`/id/`) y en lote (`/clear/`). |

---

### Endpoints

| Verbo | Endpoint | Descripción | Código éxito | Código error |
|---|---|---|---|---|
| `GET` | `/api/notifications/` | Listar todas las notificaciones | `200 OK` | — |
| `GET` | `/api/notifications/{id}/` | Obtener notificación por ID | `200 OK` | `404 Not Found` |
| `POST` | `/api/notifications/` | Crear notificación manualmente | `201 Created` | `400 Bad Request` |
| `PATCH` | `/api/notifications/{id}/read/` | Marcar notificación como leída | `200 OK` | `404 Not Found` |
| `DELETE` | `/api/notifications/{id}/` | Eliminar notificación individual | `204 No Content` | `404 Not Found` |
| `DELETE` | `/api/notifications/clear/` | Eliminar todas las notificaciones | `204 No Content` | — |

### Schema de Notificación

> ⚠️ Schema basado en `notifications/serializers.py` — fuente de verdad.

```json
{
  "id": 1,
  "ticket_id": 42,
  "message": "Nuevo Ticket #42 creado: Error en login",
  "read": false,
  "sent_at": "2025-01-15T10:30:00Z"
}
```

| Campo       | Tipo     | Descripción                                      |
|-------------|----------|--------------------------------------------------|
| `id`        | integer  | Identificador único autoincremental              |
| `ticket_id` | integer  | ID del ticket asociado (entero, consistente con el contrato de eventos) |
| `message`   | string   | Contenido descriptivo de la notificación         |
| `read`      | boolean  | Estado de lectura (`false` por defecto)          |
| `sent_at`   | datetime | Fecha y hora de creación (ISO 8601 UTC)          |

### Ejemplo de respuesta exitosa — GET /api/notifications/

```json
HTTP 200 OK
[
  {
    "id": 1,
    "ticket_id": 42,
    "message": "Nuevo Ticket #42 creado: Error en login",
    "read": false,
    "sent_at": "2025-01-15T10:30:00Z"
  },
  {
    "id": 2,
    "ticket_id": 42,
    "message": "El administrador respondió el Ticket #42",
    "read": true,
    "sent_at": "2025-01-15T11:00:00Z"
  }
]
```

### Ejemplo de respuesta de error — GET /api/notifications/999/

```json
HTTP 404 Not Found
{
  "detail": "No found."
}
```

---

## 9. Contrato de Eventos RabbitMQ

### Configuración del broker

| Parámetro | Variable de entorno | Descripción |
|---|---|---|
| Host | `RABBITMQ_HOST` | Hostname del servidor RabbitMQ |
| Exchange | `RABBITMQ_EXCHANGE_NAME` | Exchange fanout donde se publican eventos |
| Queue | `RABBITMQ_QUEUE_NOTIFICATION` | Cola exclusiva de este servicio |

### Exchange Type
`fanout` — todos los suscriptores reciben todos los eventos. El filtrado por
`event_type` ocurre en el consumer, no en el broker.

### Eventos consumidos

#### `ticket.created`
```json
{
  "event_type": "ticket.created",
  "ticket_id": 42,
  "title": "Error en módulo de login",
  "user_id": 7,
  "status": "open",
  "timestamp": "2025-01-15T10:30:00Z"
}
```
→ Genera: `"Nuevo Ticket #42 creado: Error en módulo de login"`

#### `ticket.response_added`
```json
{
  "event_type": "ticket.response_added",
  "ticket_id": 42,
  "response_id": 15,
  "admin_id": 3,
  "response_text": "Hemos identificado el problema...",
  "user_id": 7,
  "timestamp": "2025-01-15T11:00:00Z"
}
```
→ Delegado a `CreateNotificationFromResponseUseCase`

#### `ticket.status_changed`
```json
{
  "event_type": "ticket.status_changed",
  "ticket_id": 42,
  "old_status": "open",
  "new_status": "in_progress",
  "timestamp": "2025-01-15T12:00:00Z"
}
```
→ Genera: `"El estado del Ticket #42 cambió a in_progress"`

> ⚠️ Este evento **no incluye `user_id`** en el contrato oficial. Ver DT-09 en Sección 10.

#### `ticket.priority_changed`
```json
{
  "event_type": "ticket.priority_changed",
  "ticket_id": 42,
  "new_priority": "high",
  "user_id": 7,
  "timestamp": "2025-01-15T12:30:00Z"
}
```
→ Genera: `"La prioridad del Ticket #42 cambió a high"`

### Mecanismo de resiliencia

```
Flujo normal:
  Exchange (fanout)
    → Queue: notifications.queue
      → Consumer: callback()
        → Use Case
          → ACK ✅

Flujo de error (schema inválido o excepción):
  Exchange (fanout)
    → Queue: notifications.queue
      → Consumer: callback()
        → Excepción capturada
          → NACK (requeue=False) ❌
            → Dead Letter Exchange (DLX)
              → Dead Letter Queue (DLQ) para inspección
```

### Reconexión automática

El consumer implementa backoff exponencial configurable:

| Variable | Default | Descripción |
|---|---|---|
| `RABBITMQ_INITIAL_RETRY_DELAY` | `1` seg | Delay inicial |
| `RABBITMQ_MAX_RETRY_DELAY` | `60` seg | Delay máximo |
| `RABBITMQ_RETRY_BACKOFF_FACTOR` | `2` | Factor multiplicador |
| `RABBITMQ_MAX_RETRIES` | `0` | 0 = reintentos infinitos |

---

## 10. Deuda Técnica Remanente

| ID | Deuda | Prioridad | Descripción |
|---|---|---|---|
| **DT-01** | `CreateNotificationFromTicketCreatedUseCase` faltante | � Crítica | `_handle_ticket_created` aún accede al ORM directamente, viola DDD |
| **DT-02** | `test_integration.py` con host hardcodeado | 🔴 Crítica | `RABBIT_HOST = 'rabbitmq'` rompe CI |
| **DT-03** | `notifications/tests.py` deprecado | 🟠 Alta | Conflicto de test discovery con `tests/` |
| **DT-04** | `requirements.txt` sin versiones fijas | 🟡 Media | `Django>=x` en lugar de `Django==x.x.x` |
| **DT-05** | Dockerfile con usuario root | 🟡 Media | Riesgo de seguridad en contenedor |
| **DT-06** | Sin paginación en listado de notificaciones | 🟡 Media | Performance con grandes volúmenes |
| **DT-07** | `CreateNotificationFromStatusChangedUseCase` faltante | 🟠 Alta | No existe handler DDD para `ticket.status_changed` |
| **DT-08** | `CreateNotificationFromPriorityChangedUseCase` faltante | 🟠 Alta | No existe handler DDD para `ticket.priority_changed` |
| **DT-09** | Evento `ticket.status_changed` sin `user_id` | 🟠 Alta | El contrato oficial no incluye `user_id`; el servicio no puede generar notificaciones por cambio de estado hasta que el ticket-service extienda el contrato o se implemente lookup via REST |

---

## 11. Conclusiones

### ¿Valió la pena migrar del monolito a DDD Pragmático?

**Sí, con matices.**

Para un microservicio del tamaño del `notification-service`, la arquitectura DDD
Pragmático representa el punto de equilibrio correcto:

- **Suficientemente estructurada** para mantener la salud del código a largo plazo
- **Suficientemente simple** para no caer en over-engineering
- **Preparada para crecer** sin romper contratos internos

El monolito original era funcional para una primera versión, pero su acoplamiento
directo entre módulos habría bloqueado la separación en microservicios y la
escalabilidad independiente.

### El próximo paso natural

Una vez saldada la deuda técnica remanente (especialmente **DT-01** y **DT-02**),
el servicio estará en condiciones de:

1. Correr un pipeline CI verde con cobertura ≥ 70%
2. Desplegarse de forma completamente independiente via Docker
3. Escalar horizontalmente sin afectar otros servicios
4. Incorporar nuevos tipos de eventos sin modificar la infraestructura

> *"La arquitectura limpia no es un destino, es una dirección."*

---

**Documento generado para:** Taller Semana 3 — Sofka Training Leagues  
**Servicio:** `backend-notification-service`  
**Última actualización:** Febrero 2026

---

---

# Actividad 1.2: Construcción de la API REST

---

## A. Debate sobre Verbos HTTP y Códigos de Estado

### A.1. Decisión: Verbos HTTP semánticamente correctos

| Operación                        | Verbo HTTP | Justificación semántica                                                              |
|----------------------------------|------------|--------------------------------------------------------------------------------------|
| Listar notificaciones            | `GET`      | Operación de lectura segura e idempotente; no modifica estado del servidor           |
| Obtener notificación por ID      | `GET`      | Lectura de recurso identificado; idempotente                                         |
| Crear notificación               | `POST`     | Creación de nuevo recurso en la colección; no idempotente                            |
| Marcar como leída                | `PATCH`    | Modificación **parcial** del recurso (solo campo `read`); semánticamente más correcto que `PUT` |
| Eliminar notificación individual | `DELETE`   | Elimina recurso identificado; resultado observable: 404 posterior                   |
| Eliminar todas las notificaciones| `DELETE`   | Operación destructiva sobre la colección completa                                    |

> **Nota sobre `PUT`:** La letra del taller menciona `PUT` como verbo a dominar. En este servicio se eligió **no usar `PUT`** de forma deliberada porque ninguna operación requiere reemplazar el recurso completo con un payload enviado por el cliente. La única modificación parcial disponible es marcar como leída, para la cual `PATCH` es semánticamente más preciso.

> **Por qué `PATCH` y no `PUT` para marcar como leída:**
> `PUT` implica reemplazar el recurso completo con el payload enviado. `PATCH` indica una modificación parcial, lo cual es semánticamente preciso ya que solo se cambia el campo `read`. Además, la operación es idempotente (aplicarla múltiples veces produce el mismo resultado), lo que es consistente con el comportamiento esperado de `PATCH`.

---

### A.2. Decisión: Códigos de estado HTTP

| Situación                               | Código       | Justificación                                                                 |
|-----------------------------------------|--------------|-------------------------------------------------------------------------------|
| Recurso retornado correctamente         | `200 OK`     | La solicitud fue procesada y hay contenido en la respuesta                    |
| Recurso creado exitosamente             | `201 Created`| Se creó un nuevo recurso; incluye ID del nuevo recurso en el body             |
| Operación exitosa sin contenido         | `204 No Content` | La operación fue exitosa pero no hay body que retornar (DELETE)           |
| Datos de entrada inválidos              | `400 Bad Request` | El cliente envió datos malformados o incompletos                         |
| Recurso no encontrado                   | `404 Not Found` | El recurso solicitado no existe                                            |
| Error interno del servidor              | `500 Internal Server Error` | Error no controlado en el servidor                              |

---

### A.3. Decisión: Idempotencia como regla de dominio

Las operaciones idempotentes de la API reflejan reglas definidas en la capa de dominio (`domain/entities.py`):

- **Marcar como leída:** Si la notificación ya está leída, el dominio no genera evento de dominio ni modifica el estado. La respuesta es `200 OK` con el recurso sin cambios.
- **Clear all sobre bandeja vacía:** Retorna `204 No Content` sin error.

> La idempotencia **vive en el dominio**, no en la vista. El ViewSet simplemente delega.

---

### A.4. Decisión: Manejo de excepciones de dominio → HTTP

Las excepciones de dominio se traducen a códigos HTTP en la capa de presentación:

```python
except NotificationNotFound:   → HTTP 404
except DomainException:        → HTTP 400
except Exception:              → HTTP 500
```

---

## B. Documentación de Endpoints — Contrato de la API

**Base URL:** `http://localhost:8001/api`
**Content-Type:** `application/json`

---

### B.1. Listar todas las notificaciones

```
GET /api/notifications/
```

**Descripción:** Retorna la lista completa de notificaciones ordenadas por fecha de creación descendente.

**Response 200 OK — Con notificaciones:**
```json
[
  {
    "id": 3,
    "ticket_id": 103,
    "message": "El estado de tu ticket 'Error en facturación' cambió a in_progress.",
    "read": false,
    "sent_at": "2026-02-11T16:00:00Z"
  },
  {
    "id": 1,
    "ticket_id": 101,
    "message": "Tu ticket 'Error en facturación' fue creado exitosamente.",
    "read": false,
    "sent_at": "2026-02-11T14:00:00Z"
  }
]
```

**Response 200 OK — Bandeja vacía:** `[]`

| Código | Descripción |
|--------|-------------|
| `200`  | Listado retornado correctamente |
| `500`  | Error interno del servidor |

---

### B.2. Obtener notificación por ID

```
GET /api/notifications/{id}/
```

**Response 200 OK:**
```json
{
  "id": 42,
  "ticket_id": 101,
  "message": "Tu ticket 'Error en facturación' fue creado exitosamente.",
  "read": false,
  "sent_at": "2026-02-11T14:00:00Z"
}
```

**Response 404 Not Found:**
```json
{ "detail": "Not found." }
```

| Código | Descripción |
|--------|-------------|
| `200`  | Notificación encontrada y retornada |
| `404`  | No existe una notificación con el ID indicado |
| `500`  | Error interno del servidor |

---

### B.3. Crear notificación

```
POST /api/notifications/
```

**Request Body:**
```json
{
  "ticket_id": 101,
  "message": "Tu ticket 'Error en facturación' fue creado exitosamente."
}
```

| Campo       | Tipo    | Requerido | Descripción |
|-------------|---------|-----------|-------------|
| `ticket_id` | integer | ✅        | Identificador del ticket relacionado |
| `message`   | string  | ✅        | Contenido de la notificación |

**Response 201 Created:**
```json
{
  "id": 43,
  "ticket_id": 101,
  "message": "Tu ticket 'Error en facturación' fue creado exitosamente.",
  "read": false,
  "sent_at": "2026-02-11T14:30:00Z"
}
```

**Response 400 Bad Request:**
```json
{
  "ticket_id": ["This field is required."],
  "user_id": ["This field is required."]
}
```

| Código | Descripción |
|--------|-------------|
| `201`  | Notificación creada exitosamente |
| `400`  | Datos inválidos o campos requeridos ausentes |
| `500`  | Error interno del servidor |

---

### B.4. Marcar notificación como leída

```
PATCH /api/notifications/{id}/read/
```

**Descripción:** Marca una notificación como leída. Operación **idempotente**: si ya estaba leída, retorna `200 OK` sin error. No requiere body.

**Response 200 OK:**
```json
{
  "id": 42,
  "ticket_id": 101,
  "message": "Tu ticket 'Error en facturación' fue creado exitosamente.",
  "read": true,
  "sent_at": "2026-02-11T14:00:00Z"
}
```

**Response 404 Not Found:**
```json
{ "error": "Notification with id 999 not found." }
```

| Código | Descripción |
|--------|-------------|
| `200`  | Marcada como leída (o ya lo estaba) |
| `404`  | No existe una notificación con el ID indicado |
| `500`  | Error interno del servidor |

---

### B.5. Eliminar notificación individual

```
DELETE /api/notifications/{id}/
```

**Response 204 No Content:** `(sin body)`

**Response 404 Not Found:**
```json
{ "error": "Notification with id 999 not found." }
```

| Código | Descripción |
|--------|-------------|
| `204`  | Notificación eliminada exitosamente |
| `404`  | No existe una notificación con el ID indicado |
| `500`  | Error interno del servidor |

---

### B.6. Eliminar todas las notificaciones

```
DELETE /api/notifications/clear/
```

**Descripción:** Elimina permanentemente todas las notificaciones. **Idempotente**: ejecutar sobre bandeja vacía retorna `204 No Content` sin error.

**Response 204 No Content:** `(sin body)`

| Código | Descripción |
|--------|-------------|
| `204`  | Todas eliminadas (o bandeja ya vacía) |
| `500`  | Error interno del servidor |

---

## C. Resumen de Endpoints

| Método   | Endpoint                        | Descripción                        | Código Éxito     |
|----------|---------------------------------|------------------------------------|------------------|
| `GET`    | `/api/notifications/`           | Listar todas las notificaciones    | `200 OK`         |
| `GET`    | `/api/notifications/{id}/`      | Obtener notificación por ID        | `200 OK`         |
| `POST`   | `/api/notifications/`           | Crear notificación                 | `201 Created`    |
| `PATCH`  | `/api/notifications/{id}/read/` | Marcar notificación como leída     | `200 OK`         |
| `DELETE` | `/api/notifications/{id}/`      | Eliminar notificación individual   | `204 No Content` |
| `DELETE` | `/api/notifications/clear/`     | Eliminar todas las notificaciones  | `204 No Content` |

---

## D. Flujo de Integración con RabbitMQ

Los eventos de dominio generan notificaciones a través del consumer, que **delega directamente a los Use Cases** — nunca realiza requests HTTP internas:

```
ticket-service
    └─→ RabbitMQ Exchange (fanout)
            └─→ notification_queue
                    └─→ consumer.py — identifica event_type
                            ├─→ ticket.created         → CreateNotificationFromTicketCreatedUseCase   ⚠️ pendiente
                            ├─→ ticket.response_added  → CreateNotificationFromResponseUseCase        ✅ implementado
                            ├─→ ticket.status_changed  → CreateNotificationFromStatusChangedUseCase   ⚠️ pendiente
                            └─→ ticket.priority_changed→ CreateNotificationFromPriorityChangedUseCase ⚠️ pendiente
                                        ↓
                            DjangoNotificationRepository
                                        ↓
                                   PostgreSQL DB
```

> ⚠️ **Estado objetivo** — Los Use Cases marcados como `pendiente` no están implementados aún. Ver Sección 10: Deuda Técnica (DT-01, DT-07, DT-08).

> **Principio clave:** El consumer es un **adaptador de entrada** — no contiene lógica de negocio ni realiza llamadas HTTP. La lógica vive en los Use Cases.

| Evento                    | Clave Idempotencia         |
|---------------------------|----------------------------|
| `ticket.created`          | `ticket_id + event_type`   |
| `ticket.response_added`   | `ticket_id + response_id`  |
| `ticket.status_changed`   | `ticket_id + event_type`   |
| `ticket.priority_changed` | `ticket_id + event_type`   |

---

## E. Manejo de Errores

| Origen del error                | Excepción de dominio   | Código HTTP |
|---------------------------------|------------------------|-------------|
| Notificación no encontrada      | `NotificationNotFound` | `404`       |
| Regla de negocio violada        | `DomainException`      | `400`       |
| Campos requeridos ausentes      | Validación DRF         | `400`       |
| Error no controlado en servidor | `Exception`            | `500`       |

---

## F. Principios Aplicados

| Principio         | Aplicación concreta |
|-------------------|---------------------|
| **SRP**           | ViewSet solo traduce HTTP ↔ dominio; la lógica vive en `use_cases.py` y `entities.py` |
| **DIP**           | El dominio define `NotificationRepository` (ABC); la infraestructura lo implementa |
| **DRY**           | Idempotencia centralizada en la entidad de dominio, no duplicada en vistas |
| **Semántica HTTP**| Verbos y códigos elegidos por significado, no por conveniencia |
| **Idempotencia**  | `PATCH /read/` y `DELETE /clear/` son seguros de reintentar |
