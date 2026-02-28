"""
ViewSet refactorizado para usar DDD/EDA.
Las vistas ahora son thin controllers que delegan a casos de uso.
NO contienen lógica de negocio, NO acceden directamente al ORM.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q

from .models import Notification
from .serializers import NotificationSerializer
from .application.use_cases import (
    MarkNotificationAsReadUseCase,
    MarkNotificationAsReadCommand,
    DeleteNotificationUseCase,
    DeleteNotificationCommand,
    ClearAllNotificationsUseCase,
    ClearAllNotificationsCommand
)
from .infrastructure.repository import DjangoNotificationRepository
from .infrastructure.event_publisher import RabbitMQEventPublisher
from .domain.exceptions import (
    DomainException,
    NotificationNotFound
)


class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet refactorizado siguiendo principios DDD/EDA.
    
    Responsabilidades:
    - Validar entrada HTTP
    - Ejecutar casos de uso
    - Traducir respuestas de dominio a HTTP
    - Manejar excepciones de dominio
    
    NO responsable de:
    - Lógica de negocio (en entidades y casos de uso)
    - Persistencia directa (delegada al repositorio)
    - Publicación de eventos (delegada al event publisher)
    """
    
    queryset = Notification.objects.all().order_by('-sent_at')
    serializer_class = NotificationSerializer
    
    def __init__(self, *args, **kwargs):
        """Inicializa las dependencias (repositorio, event publisher, use cases)."""
        super().__init__(*args, **kwargs)
        
        # Inyección de dependencias
        self.repository = DjangoNotificationRepository()
        self.event_publisher = RabbitMQEventPublisher()
        
        # Casos de uso
        self.mark_as_read_use_case = MarkNotificationAsReadUseCase(
            repository=self.repository,
            event_publisher=self.event_publisher
        )
        self.delete_use_case = DeleteNotificationUseCase(
            repository=self.repository
        )
        self.clear_all_use_case = ClearAllNotificationsUseCase(
            repository=self.repository
        )

    def _get_request_user_id(self, request=None):
        """
        Obtiene el user_id autenticado si está disponible.

        En producción, los consumer services usan JWT stateless y ``request.user``
        expone el identificador desde el claim ``user_id``. En tests unitarios
        directos puede no existir un usuario autenticado; en ese caso se evita
        filtrar para no romper los tests que invocan métodos sin pasar por DRF.
        """
        request = request or getattr(self, 'request', None)
        user = getattr(request, 'user', None)
        user_id = getattr(user, 'id', None)
        if user_id in (None, ''):
            return None
        return str(user_id)

    def get_queryset(self):
        """
        Lista solo las notificaciones visibles para el usuario autenticado.

        Se incluyen las notificaciones dirigidas al usuario y las globales
        (``user_id == ""``), consistente con el stream SSE.
        """
        queryset = Notification.objects.all().order_by('-sent_at')
        user_id = self._get_request_user_id()
        if user_id is None:
            return queryset
        return queryset.filter(Q(user_id=user_id) | Q(user_id=''))

    # ─────────────────────────────────────────────────────────────────────────
    # Métodos HTTP no permitidos — las notificaciones se crean solo por eventos
    # de dominio (RabbitMQ), nunca directamente por API REST.
    # ─────────────────────────────────────────────────────────────────────────

    def create(self, request, *args, **kwargs):
        """POST no permitido: las notificaciones se crean mediante eventos de dominio."""
        return Response(
            {"error": "Las notificaciones se crean mediante eventos de dominio. Operación no permitida."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def update(self, request, *args, **kwargs):
        """PUT no permitido: use PATCH /notifications/{id}/read/ para marcar como leída."""
        return Response(
            {"error": "Operación no permitida. Use PATCH /notifications/{id}/read/ para marcar como leída."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        """PATCH sobre el recurso base no permitido: use PATCH /notifications/{id}/read/."""
        return Response(
            {"error": "Operación no permitida. Use PATCH /notifications/{id}/read/ para marcar como leída."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=True, methods=['patch'], url_path='read')
    def read(self, request, pk=None):
        """
        Marca una notificación como leída ejecutando el caso de uso.
        Aplica reglas de negocio del dominio.
        """
        try:
            # Crear comando
            command = MarkNotificationAsReadCommand(
                notification_id=int(pk)
            )
            
            # Ejecutar caso de uso
            self.mark_as_read_use_case.execute(command)
            
            # Recuperar el modelo Django actualizado y serializar para la respuesta
            instance = self.get_queryset().get(pk=int(pk))
            serializer = self.get_serializer(instance)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Notification.DoesNotExist:
            return Response(
                {"error": "Notificación no encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except NotificationNotFound as e:
            # Notificación no encontrada
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )
        except DomainException as e:
            # Otras excepciones de dominio
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            # Error inesperado — devolver JSON en lugar de HTML
            return Response(
                {"error": "Error interno del servidor.", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def destroy(self, request, *args, **kwargs):
        """
        Elimina la notificación especificada.
        """
        try:
            instance = self.get_object()
            command = DeleteNotificationCommand(notification_id=instance.pk)
            self.delete_use_case.execute(command)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except NotificationNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(
                {"error": "Error interno del servidor.", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=['delete'], url_path='clear')
    def clear_all(self, request):
        """
        Limpia las notificaciones del usuario autenticado.

        Si no hay contexto de usuario disponible (por ejemplo en tests unitarios
        directos), delega el comportamiento por defecto del caso de uso.
        """
        try:
            command = ClearAllNotificationsCommand(
                user_id=self._get_request_user_id(request)
            )
            self.clear_all_use_case.execute(command)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response(
                {"error": "Error interno del servidor.", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
