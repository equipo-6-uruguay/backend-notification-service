# USER STORIES Y CRITERIOS DE ACEPTACIÓN
## backend-notification-service — Sofka Training Leagues · Taller Semana 3

---

## 📋 Contexto de Negocio

El sistema de tickets permite a usuarios crear tickets de soporte y recibir respuestas de administradores. El **notification-service** es el microservicio responsable de registrar y exponer notificaciones hacia los usuarios finales. Se comunica con otros servicios exclusivamente mediante:

- **Entrada:** Eventos de dominio consumidos desde RabbitMQ (publicados por el ticket-service)
- **Salida:** API REST que expone notificaciones al frontend y otros consumidores

El servicio fue refactorizado a arquitectura DDD Pragmático, con separación estricta de capas: dominio, aplicación, infraestructura y presentación. Ningún otro microservicio accede directamente a su base de datos.

---

## 🎯 Objetivos del Producto

1. Registrar automáticamente notificaciones al usuario cuando ocurren eventos relevantes en sus tickets.
2. Exponer las notificaciones de forma consultable y filtrable mediante API REST.
3. Permitir al usuario gestionar el estado de lectura y la limpieza de su bandeja de notificaciones.
4. Garantizar resiliencia ante fallos del broker de mensajería, sin pérdida de eventos.
5. Asegurar idempotencia para que ningún evento genere notificaciones duplicadas.

---

## 📦 Épicas

| ID    | Nombre                                    | Valor principal                                                            |
|-------|-------------------------------------------|----------------------------------------------------------------------------|
| E1    | Ingesta de Eventos de Dominio             | El servicio reacciona a eventos del ticket-service y persiste notificaciones |
| E2    | Consulta de Notificaciones vía REST       | El frontend puede listar y consultar notificaciones individuales           |
| E3    | Gestión del Estado de Lectura             | El usuario puede marcar notificaciones como leídas                         |
| E4    | Eliminación de Notificaciones             | El usuario puede eliminar notificaciones individuales o todas a la vez     |
| E5    | Resiliencia del Consumidor RabbitMQ       | El consumidor sobrevive a fallos sin perder eventos                        |
| E6    | Infraestructura y CI/CD                   | El servicio es portable, contenerizado y su calidad se valida automáticamente |

---

# 📝 Historias de Usuario

---

## EPIC E1 — Ingesta de Eventos de Dominio

---

### US-E1-01 — Crear notificación al recibir evento `ticket.created`

**Como** notification-service
**quiero** procesar el evento `ticket.created` publicado por el ticket-service
**para** registrar una notificación que informe al usuario que su ticket fue creado exitosamente

#### Criterios de Aceptación

```gherkin
@epic:ingesta-eventos @story:US-E1-01 @priority:alta @risk:alto
Feature: Notificación por creación de ticket

  Como notification-service
  Quiero procesar el evento ticket.created
  Para registrar una notificación persistida para el usuario afectado

  Background:
    Given el consumidor RabbitMQ está activo y suscrito a la cola de eventos
    And la base de datos de notificaciones está disponible

  Scenario: Procesamiento exitoso de evento ticket.created
    Given se recibe un evento con event_type "ticket.created"
    And los campos ticket_id, title, user_id, status y timestamp están presentes y válidos
    When el consumidor procesa el mensaje
    Then se persiste una notificación con message que referencia el título del ticket
    And la notificación queda asociada al user_id del evento
    And la notificación queda en estado no leída
    And el mensaje es confirmado (ack) en la cola

  Scenario: Evento ticket.created con campos obligatorios ausentes
    Given se recibe un evento con event_type "ticket.created"
    And uno o más de los campos obligatorios (ticket_id, user_id, title) están ausentes
    When el consumidor intenta procesar el mensaje
    Then no se persiste ninguna notificación
    And el mensaje es enviado a la Dead Letter Queue
    And se registra un log de error estructurado con el motivo del rechazo

  Scenario Outline: Contenido del mensaje de notificación generado
    Given se recibe un evento ticket.created con title "<title>" y ticket_id <ticket_id>
    When el consumidor procesa el mensaje exitosamente
    Then el mensaje de la notificación menciona el título "<title>"
    And el ticket_id almacenado en la notificación es <ticket_id>

    Examples:
      | title                | ticket_id |
      | Error en facturación | 101       |
      | Solicitud de acceso  | 202       |
```

#### Notas
- **Valor de negocio:** El usuario sabe que su ticket fue recibido sin necesidad de consultar el ticket-service directamente.
- **Supuestos confirmados:** El mensaje siempre llega con los campos del contrato técnico definido.
- **Dependencias:** ticket-service debe publicar el evento con el contrato correcto.

#### Validación INVEST
```
I: ✅ No depende de otras US para ser implementada ni probada.
N: ✅ Describe intención de negocio, no implementación técnica.
V: ✅ El usuario es informado sin acoplamiento directo con el ticket-service.
E: ✅ Campos del evento definidos en contrato; alcance delimitado a un tipo de evento.
S: ✅ Limitada a un único tipo de evento; cabe en un sprint.
T: ✅ Criterios observables con Gherkin; verificable en tests de integración del consumer.
```

---

### US-E1-02 — Crear notificación al recibir evento `ticket.response_added`

**Como** notification-service
**quiero** procesar el evento `ticket.response_added` publicado por el ticket-service
**para** notificar al usuario original que un administrador respondió su ticket

#### Criterios de Aceptación

```gherkin
@epic:ingesta-eventos @story:US-E1-02 @priority:alta @risk:alto
Feature: Notificación por respuesta agregada a ticket

  Como notification-service
  Quiero procesar el evento ticket.response_added
  Para registrar una notificación dirigida al usuario dueño del ticket

  Background:
    Given el consumidor RabbitMQ está activo y suscrito a la cola de eventos
    And la base de datos de notificaciones está disponible

  Scenario: Procesamiento exitoso de evento ticket.response_added
    Given se recibe un evento con event_type "ticket.response_added"
    And los campos ticket_id, response_id, admin_id, response_text, user_id y timestamp están presentes
    When el consumidor procesa el mensaje
    Then se persiste una notificación asociada al user_id del evento
    And el message de la notificación referencia al ticket_id y la existencia de una nueva respuesta
    And el campo response_id queda almacenado en la notificación
    And la notificación queda en estado no leída
    And el mensaje es confirmado (ack) en la cola

  Scenario: Evento ticket.response_added con campos obligatorios ausentes
    Given se recibe un evento con event_type "ticket.response_added"
    And uno o más campos obligatorios (ticket_id, user_id, response_id) están ausentes
    When el consumidor intenta procesar el mensaje
    Then no se persiste ninguna notificación
    And el mensaje es enviado a la Dead Letter Queue
    And se registra un log de error estructurado

  Scenario: El texto de respuesta está vacío
    Given se recibe un evento ticket.response_added con response_text vacío
    And los demás campos obligatorios están presentes
    When el consumidor procesa el mensaje
    Then se persiste la notificación sin incluir el texto de respuesta en el message
    And la notificación queda correctamente asociada al ticket_id y user_id

  Scenario: El texto de respuesta supera el límite de caracteres permitido
    Given se recibe un evento ticket.response_added con response_text de más de 255 caracteres
    When el consumidor procesa el mensaje
    Then se persiste la notificación con el message truncado al límite permitido
    And no se lanza ningún error de validación

  Scenario: El mismo response_id es recibido dos veces (duplicado)
    Given existe ya una notificación para ticket_id 101 con response_id 55
    When se recibe nuevamente un evento ticket.response_added con ticket_id 101 y response_id 55
    Then no se crea una nueva notificación
    And el mensaje es confirmado (ack) en la cola
    And se registra un log de advertencia por evento duplicado

  Scenario: Dos respuestas distintas al mismo ticket no son duplicados
    Given existe una notificación para ticket_id 101 con response_id 55
    When se recibe un evento ticket.response_added con ticket_id 101 y response_id 56
    Then se persiste una nueva notificación independiente para response_id 56
```

#### Notas
- **Valor de negocio:** El usuario es alertado cuando un administrador responde, sin necesidad de hacer polling al ticket-service.
- **Supuestos confirmados:** El `user_id` del evento corresponde al dueño del ticket, no al admin que responde.
- **Supuestos confirmados:** La clave de idempotencia para este evento es `ticket_id + response_id`.
- **Supuestos confirmados:** `response_text` se trunca si supera el límite permitido.
- **Dependencias:** Ninguna dentro de esta épica.

#### Validación INVEST
```
I: ✅ Independiente; cubre un tipo de evento distinto al de US-E1-01.
N: ✅ No menciona tablas, modelos ni queries específicas.
V: ✅ El usuario recibe alerta de respuesta sin acoplamiento.
E: ✅ Contrato definido; caso del texto vacío y duplicado modelados explícitamente.
S: ✅ Scope de un evento; implementable en un sprint.
T: ✅ Escenarios observables y verificables por QA en consumer tests.
```

---

### US-E1-03 — Crear notificación al recibir evento `ticket.status_changed`

**Como** notification-service
**quiero** procesar el evento `ticket.status_changed`
**para** informar al usuario que el estado de su ticket fue actualizado por un administrador

#### Criterios de Aceptación

```gherkin
@epic:ingesta-eventos @story:US-E1-03 @priority:alta @risk:medio
Feature: Notificación por cambio de estado de ticket

  Como notification-service
  Quiero procesar el evento ticket.status_changed
  Para alertar al usuario sobre el nuevo estado de su ticket

  Background:
    Given el consumidor RabbitMQ está activo y suscrito a la cola de eventos
    And la base de datos de notificaciones está disponible

  Scenario: Procesamiento exitoso de evento ticket.status_changed
    Given se recibe un evento con event_type "ticket.status_changed"
    And los campos ticket_id, new_status, user_id y timestamp están presentes
    When el consumidor procesa el mensaje
    Then se persiste una notificación asociada al user_id del evento
    And el message incluye el nuevo estado del ticket
    And el ticket_id está almacenado en la notificación
    And la notificación queda en estado no leída
    And el mensaje es confirmado (ack) en la cola

  Scenario Outline: Notificación generada según el nuevo estado
    Given se recibe un evento ticket.status_changed con new_status "<new_status>" y ticket_id <ticket_id>
    When el consumidor procesa el mensaje
    Then el message de la notificación menciona el estado "<new_status>"

    Examples:
      | new_status  | ticket_id |
      | in_progress | 301       |
      | closed      | 302       |
      | open        | 303       |

  Scenario: Evento ticket.status_changed con campos obligatorios ausentes
    Given se recibe un evento con event_type "ticket.status_changed"
    And el campo new_status o user_id está ausente
    When el consumidor intenta procesar el mensaje
    Then no se persiste ninguna notificación
    And el mensaje es enviado a la Dead Letter Queue
    And se registra un log de error estructurado
```

#### Notas
- **Valor de negocio:** El usuario puede seguir el ciclo de vida de su ticket sin consultarlo activamente.
- **Supuestos confirmados:** Los valores de `new_status` son `open`, `in_progress`, `closed`.
- **Dependencias:** Ninguna dentro de esta épica.

#### Validación INVEST
```
I: ✅ Cubre únicamente eventos de cambio de estado; independiente de otras US.
N: ✅ Orientada a comportamiento del sistema ante el evento, no a implementación.
V: ✅ El usuario entiende el progreso de su ticket sin acoplamiento.
E: ✅ Scenario Outline cubre variaciones de estado conocidas del dominio.
S: ✅ Scope acotado a un tipo de evento.
T: ✅ Resultados observables; los Examples son verificables por QA.
```

---

### US-E1-04 — Crear notificación al recibir evento `ticket.priority_changed`

**Como** notification-service
**quiero** procesar el evento `ticket.priority_changed`
**para** informar al usuario que la prioridad de su ticket fue modificada

#### Criterios de Aceptación

```gherkin
@epic:ingesta-eventos @story:US-E1-04 @priority:media @risk:medio
Feature: Notificación por cambio de prioridad de ticket

  Como notification-service
  Quiero procesar el evento ticket.priority_changed
  Para alertar al usuario sobre el nuevo nivel de prioridad de su ticket

  Background:
    Given el consumidor RabbitMQ está activo y suscrito a la cola de eventos
    And la base de datos de notificaciones está disponible

  Scenario: Procesamiento exitoso de evento ticket.priority_changed
    Given se recibe un evento con event_type "ticket.priority_changed"
    And los campos ticket_id, new_priority, user_id y timestamp están presentes
    When el consumidor procesa el mensaje
    Then se persiste una notificación asociada al user_id del evento
    And el message incluye la nueva prioridad del ticket
    And el ticket_id está almacenado en la notificación
    And la notificación queda en estado no leída
    And el mensaje es confirmado (ack) en la cola

  Scenario Outline: Notificación generada según la nueva prioridad
    Given se recibe un evento ticket.priority_changed con new_priority "<new_priority>"
    When el consumidor procesa el mensaje
    Then el message de la notificación menciona la prioridad "<new_priority>"

    Examples:
      | new_priority |
      | high         |
      | medium       |
      | low          |

  Scenario: Evento ticket.priority_changed con prioridad fuera del catálogo válido
    Given se recibe un evento con new_priority "critical"
    When el consumidor intenta procesar el mensaje
    Then no se persiste ninguna notificación
    And el mensaje es enviado a la Dead Letter Queue
    And se registra un log de error indicando prioridad inválida

  Scenario: Evento ticket.priority_changed con campos obligatorios ausentes
    Given se recibe un evento con event_type "ticket.priority_changed"
    And el campo new_priority o user_id está ausente
    When el consumidor intenta procesar el mensaje
    Then no se persiste ninguna notificación
    And el mensaje es enviado a la Dead Letter Queue
    And se registra un log de error estructurado
```

#### Notas
- **Valor de negocio:** El usuario es informado de cambios de prioridad que pueden afectar su SLA de atención.
- **Supuestos confirmados:** Catálogo definitivo de prioridades: `high`, `medium`, `low`. Valores fuera de catálogo son rechazados.
- **Dependencias:** Ninguna dentro de esta épica.

#### Validación INVEST
```
I: ✅ Independiente de las demás US de ingesta.
N: ✅ Describe intención de negocio, no implementación técnica.
V: ✅ El usuario entiende el impacto de cambios de prioridad en su ticket.
E: ✅ Catálogo de prioridades confirmado; escenario de rechazo por valor inválido incluido.
S: ✅ Scope acotado a un tipo de evento.
T: ✅ Criterios observables; Examples verificables por QA.
```

---

### US-E1-05 — Garantizar idempotencia en la creación de notificaciones

**Como** notification-service
**quiero** detectar y descartar eventos duplicados usando claves de idempotencia por tipo de evento
**para** evitar que el usuario reciba notificaciones repetidas ante reenvíos o fallos de red

#### Criterios de Aceptación

```gherkin
@epic:ingesta-eventos @story:US-E1-05 @priority:alta @risk:alto
Feature: Idempotencia en la creación de notificaciones

  Como notification-service
  Quiero detectar eventos duplicados con claves específicas por tipo de evento
  Para garantizar que una misma ocurrencia no genere más de una notificación

  Background:
    Given el consumidor RabbitMQ está activo
    And la base de datos de notificaciones está disponible

  Scenario: Evento duplicado tick.created es descartado (clave: ticket_id + event_type)
    Given existe ya una notificación para ticket_id 101 con event_type "ticket.created"
    When se recibe nuevamente un evento con ticket_id 101 y event_type "ticket.created"
    Then no se crea una nueva notificación
    And el mensaje es confirmado (ack) en la cola
    And se registra un log de advertencia indicando que el evento fue descartado por duplicado

  Scenario: Idempotencia para ticket.response_added usa ticket_id + response_id
    Given existe una notificación para ticket_id 101 originada por response_id 55
    When se recibe un evento ticket.response_added con ticket_id 101 y response_id 55
    Then no se crea una nueva notificación
    And el mensaje es confirmado (ack) en la cola

  Scenario: Dos respuestas distintas al mismo ticket no son duplicados
    Given existe una notificación para ticket_id 101 con response_id 55
    When se recibe un evento ticket.response_added con ticket_id 101 y response_id 56
    Then se persiste una nueva notificación para response_id 56
    And ambas notificaciones coexisten en la base de datos

  Scenario: Evento del mismo ticket_id pero distinto event_type no es considerado duplicado
    Given existe una notificación para ticket_id 101 con event_type "ticket.created"
    When se recibe un evento con ticket_id 101 y event_type "ticket.status_changed"
    Then se persiste una nueva notificación para ticket_id 101
    And ambas notificaciones coexisten en la base de datos

  Scenario: Primer evento de un ticket_id nunca antes procesado
    Given no existe ninguna notificación para ticket_id 999
    When se recibe un evento con ticket_id 999 y event_type "ticket.created"
    Then se persiste la notificación correctamente
    And el mensaje es confirmado (ack) en la cola
```

#### Notas
- **Valor de negocio:** Garantiza experiencia consistente sin spam de notificaciones ante fallos de red o redelivery de RabbitMQ.
- **Supuestos confirmados:** La clave de idempotencia tiene dos variantes:
  - `ticket.response_added` → clave: `ticket_id + response_id`
  - todos los demás eventos → clave: `ticket_id + event_type`
- **Dependencias:** Aplica transversalmente a US-E1-01, US-E1-02, US-E1-03 y US-E1-04.

#### Validación INVEST
```
I: ✅ La historia describe un comportamiento independiente y verificable, aunque su regla sea transversal.
N: ✅ Define comportamiento esperado del sistema; no menciona mecanismo técnico de deduplicación.
V: ✅ Evita spam de notificaciones; protege la experiencia del usuario.
E: ✅ Clave de idempotencia definida con dos variantes confirmadas; sin ambigüedad.
S: ✅ Alcance acotado a la regla de deduplicación; implementable en un sprint.
T: ✅ Los cinco escenarios son verificables con datos concretos y observables.
```

---

## EPIC E2 — Consulta de Notificaciones vía REST

---

### US-E2-01 — Listar todas las notificaciones

**Como** frontend del sistema de tickets
**quiero** obtener la lista de todas las notificaciones existentes mediante una petición REST
**para** mostrar al usuario el historial completo de eventos relacionados con sus tickets

#### Criterios de Aceptación

```gherkin
@epic:consulta-rest @story:US-E2-01 @priority:alta @risk:bajo
Feature: Listar todas las notificaciones

  Como frontend del sistema de tickets
  Quiero obtener todas las notificaciones vía GET /api/notifications/
  Para presentar al usuario su historial de notificaciones

  Background:
    Given la API REST del notification-service está disponible

  Scenario: Listado exitoso con notificaciones existentes
    Given existen 3 notificaciones persistidas en el sistema
    When el frontend realiza un GET a /api/notifications/
    Then la respuesta tiene código HTTP 200
    And el body contiene una lista con las 3 notificaciones
    And cada notificación incluye los campos: id, ticket_id, message, read, sent_at

  Scenario: Listado exitoso con bandeja vacía
    Given no existe ninguna notificación en el sistema
    When el frontend realiza un GET a /api/notifications/
    Then la respuesta tiene código HTTP 200
    And el body contiene una lista vacía

  Scenario: Las notificaciones se devuelven ordenadas por fecha de creación descendente
    Given existen notificaciones creadas en distintos momentos
    When el frontend realiza un GET a /api/notifications/
    Then la primera notificación de la lista es la más reciente
```

#### Notas
- **Valor de negocio:** El usuario puede ver todos los eventos que ocurrieron sobre sus tickets desde una única consulta.
- **Supuestos confirmados:** No se aplica filtrado por `read` ni por `user_id` en este endpoint. El filtrado es responsabilidad del llamante.
- **Dependencias:** Requiere que E1 esté implementada para tener datos.

#### Validación INVEST
```
I: ✅ Independiente; no depende de otras historias de E2.
N: ✅ Describe el comportamiento del endpoint, no la implementación del serializador.
V: ✅ El frontend puede presentar el historial completo al usuario.
E: ✅ Comportamiento de lista vacía y ordenamiento definidos explícitamente.
S: ✅ Scope de un único endpoint GET.
T: ✅ Todos los escenarios son verificables con HTTP responses concretas.
```

---

### US-E2-02 — Consultar notificación individual por ID

**Como** frontend del sistema de tickets
**quiero** obtener el detalle de una notificación específica por su ID mediante REST
**para** mostrar la información completa de una notificación al usuario cuando la selecciona

#### Criterios de Aceptación

```gherkin
@epic:consulta-rest @story:US-E2-02 @priority:alta @risk:bajo
Feature: Consultar notificación por ID

  Como frontend del sistema de tickets
  Quiero obtener una notificación individual vía GET /api/notifications/{id}/
  Para mostrar el detalle completo de una notificación seleccionada por el usuario

  Background:
    Given la API REST del notification-service está disponible

  Scenario: Consulta exitosa de notificación existente
    Given existe una notificación con id 42
    When el frontend realiza un GET a /api/notifications/42/
    Then la respuesta tiene código HTTP 200
    And el body contiene los campos: id, message, read, ticket_id, user_id, created_at
    And el campo id del body es 42

  Scenario: Consulta de notificación inexistente
    Given no existe ninguna notificación con id 999
    When el frontend realiza un GET a /api/notifications/999/
    Then la respuesta tiene código HTTP 404
    And el body contiene un mensaje de error descriptivo

  Scenario: Consulta con ID de formato inválido
    Given el frontend envía un GET a /api/notifications/abc/
    When el servidor procesa la petición
    Then la respuesta tiene código HTTP 404
```

#### Notas
- **Valor de negocio:** Permite al frontend mostrar el detalle de una notificación sin recargar el listado completo.
- **Supuestos confirmados:** El ID es un entero positivo. IDs no numéricos resultan en 404 por el enrutador.
- **Dependencias:** US-E2-01 no es requisito técnico, pero ambas pertenecen al mismo endpoint base.

#### Validación INVEST
```
I: ✅ Independiente de US-E2-01; el endpoint /id/ funciona sin necesidad del listado.
N: ✅ Define comportamiento observable del endpoint, no la query ORM.
V: ✅ El usuario obtiene detalle sin recargar listado; reduce payload innecesario.
E: ✅ Casos de éxito, inexistencia e ID inválido cubiertos.
S: ✅ Scope de un único endpoint GET con ID.
T: ✅ Verificable con HTTP status codes y body structure.
```

---

## EPIC E3 — Gestión del Estado de Lectura

---

### US-E3-01 — Marcar notificación individual como leída

**Como** usuario del sistema de tickets
**quiero** marcar una notificación específica como leída mediante una acción REST
**para** indicar que ya tomé conocimiento del evento y distinguirla de las notificaciones nuevas

#### Criterios de Aceptación

```gherkin
@epic:estado-lectura @story:US-E3-01 @priority:alta @risk:bajo
Feature: Marcar notificación como leída

  Como usuario del sistema de tickets
  Quiero marcar una notificación como leída vía PATCH /api/notifications/{id}/read/
  Para gestionar el estado de mi bandeja de notificaciones

  Background:
    Given la API REST del notification-service está disponible

  Scenario: Marcar como leída una notificación no leída existente
    Given existe una notificación con id 42 en estado no leída (read: false)
    When el frontend realiza un PATCH a /api/notifications/42/read/
    Then la respuesta tiene código HTTP 200
    And el body contiene la notificación actualizada con read: true

  Scenario: Marcar como leída una notificación ya leída (idempotencia)
    Given existe una notificación con id 42 en estado leída (read: true)
    When el frontend realiza un PATCH a /api/notifications/42/read/
    Then la respuesta tiene código HTTP 200
    And el body contiene la notificación con read: true sin cambios adicionales
    And no se genera ningún error ni efecto secundario

  Scenario: Intentar marcar como leída una notificación inexistente
    Given no existe ninguna notificación con id 999
    When el frontend realiza un PATCH a /api/notifications/999/read/
    Then la respuesta tiene código HTTP 404
    And el body contiene un mensaje de error descriptivo
```

#### Notas
- **Valor de negocio:** El usuario puede gestionar su bandeja diferenciando notificaciones nuevas de las ya procesadas.
- **Supuestos confirmados:** La operación es idempotente; marcar como leída una notificación ya leída no genera error.
- **Dependencias:** Requiere que la notificación exista (E1 debe estar implementada).

#### Validación INVEST
```
I: ✅ Independiente de E2; no necesita del listado para funcionar.
N: ✅ Describe la intención del usuario (gestionar estado), no el campo de la BD.
V: ✅ Permite al usuario distinguir notificaciones nuevas de las ya vistas.
E: ✅ Caso idempotente definido explícitamente; sin ambigüedad de comportamiento.
S: ✅ Scope de un único endpoint PATCH.
T: ✅ HTTP status codes y campo read verificables en respuesta.
```

---

## EPIC E4 — Eliminación de Notificaciones

---

### US-E4-01 — Eliminar notificación individual

**Como** usuario del sistema de tickets
**quiero** eliminar una notificación específica de mi bandeja
**para** mantener mi historial de notificaciones limpio y relevante

#### Criterios de Aceptación

```gherkin
@epic:eliminacion @story:US-E4-01 @priority:media @risk:bajo
Feature: Eliminar notificación individual

  Como usuario del sistema de tickets
  Quiero eliminar una notificación específica vía DELETE /api/notifications/{id}/
  Para gestionar y limpiar mi bandeja de notificaciones

  Background:
    Given la API REST del notification-service está disponible

  Scenario: Eliminación exitosa de notificación existente
    Given existe una notificación con id 42
    When el frontend realiza un DELETE a /api/notifications/42/
    Then la respuesta tiene código HTTP 204
    And el body está vacío
    And la notificación con id 42 ya no existe en el sistema

  Scenario: Verificación de eliminación efectiva
    Given existe una notificación con id 42
    When el frontend realiza un DELETE a /api/notifications/42/
    And luego realiza un GET a /api/notifications/42/
    Then la segunda respuesta tiene código HTTP 404

  Scenario: Intentar eliminar una notificación inexistente
    Given no existe ninguna notificación con id 999
    When el frontend realiza un DELETE a /api/notifications/999/
    Then la respuesta tiene código HTTP 404
    And el body contiene un mensaje de error descriptivo
```

#### Notas
- **Valor de negocio:** El usuario puede remover notificaciones irrelevantes para mantener su bandeja organizada.
- **Supuestos confirmados:** La eliminación es permanente; no existe papelera ni soft delete.
- **Dependencias:** Ninguna dentro de esta épica.

#### Validación INVEST
```
I: ✅ Independiente de US-E4-02; el DELETE por ID no requiere el clear all.
N: ✅ Define comportamiento del endpoint, no implementación de la capa de persistencia.
V: ✅ El usuario mantiene su bandeja limpia eliminando notificaciones individuales.
E: ✅ Caso de verificación post-eliminación y caso de notificación inexistente cubiertos.
S: ✅ Scope de un único endpoint DELETE.
T: ✅ Verificable con HTTP 204/404 y ausencia del recurso tras eliminación.
```

---

### US-E4-02 — Eliminar todas las notificaciones (clear all)

**Como** usuario del sistema de tickets
**quiero** eliminar todas mis notificaciones de una sola acción
**para** limpiar mi bandeja completamente de forma rápida sin eliminar una por una

#### Criterios de Aceptación

```gherkin
@epic:eliminacion @story:US-E4-02 @priority:media @risk:medio
Feature: Eliminar todas las notificaciones

  Como usuario del sistema de tickets
  Quiero limpiar todas las notificaciones vía DELETE /api/notifications/clear/
  Para vaciar mi bandeja de notificaciones en una sola operación

  Background:
    Given la API REST del notification-service está disponible

  Scenario: Clear all con notificaciones existentes
    Given existen 5 notificaciones en el sistema
    When el frontend realiza un DELETE a /api/notifications/clear/
    Then la respuesta tiene código HTTP 204
    And el body está vacío
    And al realizar un GET a /api/notifications/ la lista está vacía

  Scenario: Clear all con bandeja ya vacía (idempotencia)
    Given no existe ninguna notificación en el sistema
    When el frontend realiza un DELETE a /api/notifications/clear/
    Then la respuesta tiene código HTTP 204
    And no se genera ningún error
```

#### Notas
- **Valor de negocio:** Permite al usuario vaciar su bandeja de forma eficiente sin múltiples llamadas.
- **Supuestos confirmados:** La operación elimina todas las notificaciones. No existe filtro por usuario en este endpoint; el alcance lo define el llamante.
- **Supuestos confirmados:** La operación es idempotente; ejecutarla sobre una bandeja vacía devuelve 204 sin error.
- **Dependencias:** US-E4-01 puede coexistir; son operaciones complementarias.

#### Validación INVEST
```
I: ✅ Independiente de US-E4-01; el clear all es una operación autónoma.
N: ✅ Define comportamiento de negocio (vaciar bandeja), no implementación del bulk delete.
V: ✅ Mejora significativamente la UX al evitar N llamadas para limpiar la bandeja.
E: ✅ Caso idempotente sobre bandeja vacía definido explícitamente.
S: ✅ Scope de un único endpoint DELETE con semántica de bulk.
T: ✅ Verificable con HTTP 204 y validación del listado vacío posterior.
```

---

## EPIC E5 — Resiliencia del Consumidor RabbitMQ

---

### US-E5-01 — Reconexión automática del consumidor ante caída del broker

**Como** notification-service
**quiero** reconectarme automáticamente al broker RabbitMQ cuando la conexión se interrumpe
**para** garantizar que ningún evento sea perdido permanentemente por una caída temporal del broker

#### Criterios de Aceptación

```gherkin
@epic:resiliencia @story:US-E5-01 @priority:alta @risk:alto
Feature: Reconexión automática del consumidor RabbitMQ

  Como notification-service
  Quiero reconectarme automáticamente al broker cuando la conexión falla
  Para no perder eventos publicados tras una interrupción temporal

  Background:
    Given el consumidor RabbitMQ está configurado con lógica de reconexión

  Scenario: Reconexión exitosa tras caída temporal del broker
    Given el consumidor está activo y procesando eventos
    When el broker RabbitMQ se vuelve inaccesible
    Then el consumidor detecta la pérdida de conexión
    And el consumidor intenta reconectarse de forma periódica
    And cuando el broker vuelve a estar disponible, el consumidor restablece la conexión
    And el consumidor retoma el procesamiento de mensajes sin intervención manual

  Scenario: Log de intento de reconexión
    Given el broker RabbitMQ está caído
    When el consumidor intenta reconectarse
    Then se registra un log de advertencia estructurado por cada intento fallido
    And el log incluye el número de intento y el motivo del fallo

  Scenario: El consumidor no termina su proceso por fallos de conexión
    Given el broker RabbitMQ está caído
    When el consumidor detecta la pérdida de conexión
    Then el proceso del consumidor continúa en ejecución esperando reconexión
    But no se lanza una excepción no capturada que termine el proceso
```

#### Notas
- **Valor de negocio:** Una caída del broker no implica pérdida de notificaciones; el sistema se recupera solo.
- **Supuestos confirmados:** El intervalo de reconexión puede ser fijo o con backoff exponencial; la implementación es decisión del equipo.
- **Dependencias:** Ninguna en otras épicas. Habilita confianza en E1.

#### Validación INVEST
```
I: ✅ Puede implementarse y probarse de forma aislada con un broker mock.
N: ✅ No prescribe el mecanismo de reconexión (backoff, fixed delay), solo el comportamiento.
V: ✅ Garantiza disponibilidad continua del consumidor sin intervención operacional.
E: ✅ Comportamiento de log y de no-terminación del proceso están definidos.
S: ✅ Scope acotado al mecanismo de reconexión; cabe en un sprint.
T: ✅ Verificable con tests de integración simulando caída y recuperación del broker.
```

---

### US-E5-02 — Enrutamiento de mensajes no procesables a Dead Letter Queue

**Como** notification-service
**quiero** enviar a la Dead Letter Queue los mensajes que no pueden ser procesados
**para** evitar que un mensaje corrupto o inválido bloquee el consumidor o se procese en bucle infinito

#### Criterios de Aceptación

```gherkin
@epic:resiliencia @story:US-E5-02 @priority:alta @risk:alto
Feature: Dead Letter Queue para mensajes no procesables

  Como notification-service
  Quiero enrutar mensajes fallidos a la DLQ
  Para que el consumidor no se bloquee ni entre en bucle de reintentos infinitos

  Background:
    Given el consumidor RabbitMQ está configurado con una Dead Letter Queue

  Scenario: Mensaje con formato JSON inválido es enviado a DLQ
    Given se recibe un mensaje cuyo body no es JSON válido
    When el consumidor intenta deserializar el mensaje
    Then el mensaje es enviado a la Dead Letter Queue
    And se registra un log de error estructurado con el motivo
    And el consumidor continúa procesando el siguiente mensaje sin interrumpirse

  Scenario: Mensaje con event_type desconocido es enviado a DLQ
    Given se recibe un mensaje con event_type "ticket.unknown_event"
    When el consumidor intenta identificar el handler correspondiente
    Then el mensaje es enviado a la Dead Letter Queue
    And se registra un log de advertencia indicando el event_type desconocido
    And el consumidor continúa sin interrumpirse

  Scenario: Mensaje con campos obligatorios ausentes es enviado a DLQ
    Given se recibe un mensaje con event_type válido pero sin los campos obligatorios
    When el consumidor intenta construir el comando de dominio correspondiente
    Then el mensaje es enviado a la Dead Letter Queue
    And se registra un log de error estructurado
    And el consumidor continúa procesando el siguiente mensaje

  Scenario: Error inesperado durante el procesamiento de un mensaje
    Given se recibe un mensaje estructuralmente válido
    When ocurre una excepción no controlada durante el procesamiento
    Then el mensaje es enviado a la Dead Letter Queue
    But no se termina el proceso del consumidor
    And se registra un log de error con el stack trace del fallo
```

#### Notas
- **Valor de negocio:** El consumidor no se cae ni entra en bucle por mensajes inválidos; los errores quedan trazados en DLQ para revisión posterior.
- **Supuestos confirmados:** La DLQ está configurada a nivel de infraestructura RabbitMQ. El consumidor no gestiona la DLQ directamente, solo hace nack/reject.
- **Dependencias:** Los escenarios de DLQ en US-E1-01 al US-E1-04 asumen que esta historia está implementada.

#### Validación INVEST
```
I: ✅ Independiente de las historias de ingesta; describe el mecanismo de error handling de infraestructura.
N: ✅ No prescribe si se usa nack, reject o dead-lettering de RabbitMQ; solo el comportamiento observable.
V: ✅ Garantiza que mensajes problemáticos no bloqueen el flujo de eventos válidos.
E: ✅ Cuatro tipos de fallos cubiertos: JSON inválido, event_type desconocido, campos ausentes, error inesperado.
S: ✅ Scope acotado al mecanismo de error handling del consumidor.
T: ✅ Verificable con tests de consumer usando mensajes intencionalmente malformados.
```

---

## EPIC E6 — Infraestructura y CI/CD

---

### US-INFRA-01 — Dockerfile optimizado

**Como** desarrollador del equipo,
**quiero** que el notification-service tenga un Dockerfile optimizado,
**para** garantizar que la imagen sea reproducible, segura y ligera en cualquier entorno.

#### Criterios de Aceptación

```gherkin
@epic:infraestructura @story:US-INFRA-01 @priority:alta @risk:bajo
Feature: Dockerfile optimizado para el notification-service

  Como desarrollador del equipo
  Quiero construir una imagen Docker del notification-service
  Para garantizar portabilidad y seguridad en cualquier entorno

  Scenario: Construcción exitosa de la imagen Docker
    Given el repositorio está clonado en el entorno de build
    When ejecuto `docker build -t notification-service .`
    Then la imagen se construye sin errores
    And el contenedor inicia y responde en el puerto configurado

  Scenario: El contenedor corre como usuario no-root
    Given la imagen está construida
    When inspecciono el usuario del proceso dentro del contenedor
    Then el proceso NO corre como root (uid != 0)

  Scenario: El tamaño de la imagen es razonable
    Given la imagen está construida
    When ejecuto `docker image inspect notification-service`
    Then el tamaño de la imagen es menor a 300MB
```

#### Validación INVEST
```
I: ✅ No depende de otros servicios para construirse.
N: ✅ Describe comportamiento de la imagen, no instrucciones Dockerfile específicas.
V: ✅ Garantiza que el servicio funciona igual en cualquier máquina.
E: ✅ Un solo artefacto (Dockerfile); estimable en 2-3 horas.
S: ✅ Scope de un solo archivo.
T: ✅ Verificable con `docker build` y `docker run`.
```

---

### US-INFRA-02 — Entorno local con docker-compose

**Como** desarrollador,
**quiero** levantar el notification-service con `docker-compose up`,
**para** desarrollar y testear el servicio de forma aislada sin configuración manual.

#### Criterios de Aceptación

```gherkin
@epic:infraestructura @story:US-INFRA-02 @priority:alta @risk:medio
Feature: Entorno local completo con docker-compose

  Como desarrollador
  Quiero levantar el ecosistema completo con un solo comando
  Para desarrollar y probar el notification-service de forma aislada

  Background:
    Given existe el archivo `.env` configurado a partir de `.env.example`

  Scenario: Levantamiento exitoso del ecosistema
    Given el archivo docker-compose.yml está en la raíz del proyecto
    When ejecuto `docker-compose up --build`
    Then el notification-service responde en `http://localhost:8003/api/notifications/`
    And PostgreSQL está accesible y las migraciones fueron aplicadas
    And RabbitMQ está accesible en `localhost:15672`

  Scenario: Los datos persisten tras reiniciar los contenedores
    Given existen notificaciones creadas vía la API
    When ejecuto `docker-compose restart`
    And realizo GET /api/notifications/
    Then las notificaciones siguen existiendo (volumen persistido)

  Scenario: El ecosistema se destruye limpiamente
    When ejecuto `docker-compose down`
    Then todos los contenedores se detienen sin errores
```

#### Validación INVEST
```
I: ✅ Levanta solo notification-service + postgres + rabbitmq; no depende de otros servicios del sistema.
N: ✅ Define comportamiento del entorno, no el contenido del YAML.
V: ✅ Elimina el "funciona en mi máquina"; el entorno es reproducible para todo el equipo.
E: ✅ Un solo docker-compose.yml; estimable en 3-4 horas.
S: ✅ Scope acotado a orquestación local del servicio.
T: ✅ Verificable con `docker-compose up` y requests a los endpoints.
```

---

### US-INFRA-03 — Pipeline CI con cobertura mínima

**Como** QA del equipo,
**quiero** que cada Push o PR dispare automáticamente los tests con cobertura,
**para** detectar regresiones antes de que lleguen a develop o main.

#### Criterios de Aceptación

```gherkin
@epic:infraestructura @story:US-INFRA-03 @priority:alta @risk:medio
Feature: Pipeline de integración continua en GitHub Actions

  Como QA del equipo
  Quiero que cada Push o PR ejecute los tests automáticamente
  Para detectar regresiones antes de integrar código

  Background:
    Given existe el archivo `.github/workflows/ci.yml` en el repositorio

  Scenario: El pipeline se dispara automáticamente en push
    Given un desarrollador realiza un push a cualquier rama (main, develop, feature/**)
    When GitHub procesa el push
    Then el pipeline ci.yml se ejecuta automáticamente

  Scenario: El pipeline falla si algún test no pasa
    Given un push contiene código que rompe un test existente
    When el pipeline ejecuta pytest
    Then el pipeline termina con exit code != 0
    And el resultado aparece en rojo en la pestaña Actions de GitHub
    And el PR no puede mergearse automáticamente

  Scenario: El pipeline falla si la cobertura es menor al 70%
    Given el código tiene cobertura por debajo del umbral mínimo
    When el pipeline mide cobertura con pytest-cov
    Then el pipeline termina con exit code != 0 por cobertura insuficiente
    And el reporte de cobertura está disponible como artefacto descargable

  Scenario: El pipeline pasa y muestra verde en Actions
    Given todos los tests pasan y la cobertura es >= 70%
    When el pipeline se ejecuta
    Then todos los pasos terminan con exit code 0
    And el resultado aparece en verde en la pestaña Actions de GitHub
```

#### Validación INVEST
```
I: ✅ El pipeline corre en este repo; no depende de otros servicios del sistema.
N: ✅ Define el comportamiento del CI, no los comandos específicos del workflow.
V: ✅ Detecta regresiones automáticamente antes de que lleguen a develop/main.
E: ✅ Un solo archivo ci.yml; estimable en 2-3 horas.
S: ✅ Scope de pipeline básico de tests y cobertura.
T: ✅ Verificable con la pestaña Actions de GitHub (verde/rojo).
```

---

## 📊 Resumen de Historias de Usuario

| ID           | Historia                                              | Épica | Prioridad | Riesgo |
|--------------|-------------------------------------------------------|-------|-----------|--------|
| US-E1-01     | Notificación por `ticket.created`                     | E1    | Alta      | Alto   |
| US-E1-02     | Notificación por `ticket.response_added`              | E1    | Alta      | Alto   |
| US-E1-03     | Notificación por `ticket.status_changed`              | E1    | Alta      | Medio  |
| US-E1-04     | Notificación por `ticket.priority_changed`            | E1    | Media     | Medio  |
| US-E1-05     | Idempotencia en la creación de notificaciones         | E1    | Alta      | Alto   |
| US-E2-01     | Listar todas las notificaciones                       | E2    | Alta      | Bajo   |
| US-E2-02     | Consultar notificación individual por ID              | E2    | Alta      | Bajo   |
| US-E3-01     | Marcar notificación individual como leída             | E3    | Alta      | Bajo   |
| US-E4-01     | Eliminar notificación individual                      | E4    | Media     | Bajo   |
| US-E4-02     | Eliminar todas las notificaciones (clear all)         | E4    | Media     | Medio  |
| US-E5-01     | Reconexión automática ante caída del broker           | E5    | Alta      | Alto   |
| US-E5-02     | Enrutamiento de mensajes no procesables a DLQ         | E5    | Alta      | Alto   |
| US-INFRA-01  | Dockerfile optimizado para el notification-service    | E6    | Alta      | Bajo   |
| US-INFRA-02  | Entorno local completo con docker-compose             | E6    | Alta      | Medio  |
| US-INFRA-03  | Pipeline CI con cobertura mínima >= 70%               | E6    | Alta      | Medio  |

---

*Documento generado por IRIS — Sofka Training Leagues · Taller Semana 3 · Febrero 2026*
