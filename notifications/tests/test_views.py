"""
Tests del ViewSet refactorizado (capa de presentación).
Prueban que las vistas deleguen correctamente a casos de uso.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from rest_framework import status
from datetime import datetime

from notifications.api import NotificationViewSet
from notifications.domain.entities import Notification as DomainNotification
from notifications.domain.exceptions import NotificationNotFound
from notifications.models import Notification as DjangoNotification


class TestNotificationViewSet(TestCase):
    """Tests del NotificationViewSet refactorizado."""
    
    def setUp(self):
        """Setup común para todos los tests."""
        self.factory = APIRequestFactory()
        self.viewset = NotificationViewSet()
    
    @patch('notifications.api.MarkNotificationAsReadUseCase')
    @patch('notifications.api.DjangoNotificationRepository')
    @patch('notifications.api.RabbitMQEventPublisher')
    def test_read_action_success(self, mock_publisher, mock_repository, mock_use_case):
        """Marcar como leída una notificación existente retorna 200 OK con el recurso actualizado."""
        # Arrange — crear notificación Django en DB para que Notification.objects.get() funcione
        django_notification = DjangoNotification.objects.create(
            ticket_id="T-123",
            message="Test",
            read=False,
            user_id="user-1"
        )
        notification_id = django_notification.pk

        # Mock del caso de uso
        mock_use_case_instance = Mock()
        mock_use_case_instance.execute.return_value = None
        mock_use_case.return_value = mock_use_case_instance

        # Crear viewset con mocks — se necesita request y format_kwarg para get_serializer
        viewset = NotificationViewSet()
        viewset.mark_as_read_use_case = mock_use_case_instance
        request = self.factory.patch(f'/api/notifications/{notification_id}/read/')
        viewset.request = request
        viewset.format_kwarg = None

        # Act
        response = viewset.read(request, pk=notification_id)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == notification_id
        mock_use_case_instance.execute.assert_called_once()
    
    @patch('notifications.api.MarkNotificationAsReadUseCase')
    @patch('notifications.api.DjangoNotificationRepository')
    @patch('notifications.api.RabbitMQEventPublisher')
    def test_read_action_not_found(self, mock_publisher, mock_repository, mock_use_case):
        """Marcar como leída una notificación inexistente retorna 404."""
        # Arrange
        notification_id = 999
        
        # Mock del caso de uso que lanza excepción
        mock_use_case_instance = Mock()
        mock_use_case_instance.execute.side_effect = NotificationNotFound(notification_id)
        mock_use_case.return_value = mock_use_case_instance
        
        # Crear viewset con mocks
        viewset = NotificationViewSet()
        viewset.mark_as_read_use_case = mock_use_case_instance
        
        # Act
        request = self.factory.patch(f'/api/notifications/{notification_id}/read/')
        response = viewset.read(request, pk=notification_id)
        
        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'error' in response.data

    def test_get_queryset_filters_notifications_by_authenticated_user(self):
        """El listado REST solo debe devolver notificaciones del usuario autenticado y globales."""
        user_notification = DjangoNotification.objects.create(
            ticket_id="T-100",
            message="User notification",
            read=False,
            user_id="user-1",
        )
        global_notification = DjangoNotification.objects.create(
            ticket_id="T-101",
            message="Global notification",
            read=False,
            user_id="",
        )
        DjangoNotification.objects.create(
            ticket_id="T-102",
            message="Other user notification",
            read=False,
            user_id="user-2",
        )

        request = self.factory.get('/api/notifications/')
        request.user = SimpleNamespace(id='user-1')

        viewset = NotificationViewSet()
        viewset.request = request

        queryset_ids = list(viewset.get_queryset().values_list('id', flat=True))

        assert user_notification.id in queryset_ids
        assert global_notification.id in queryset_ids
        assert len(queryset_ids) == 2

    @patch('notifications.api.ClearAllNotificationsUseCase')
    @patch('notifications.api.DjangoNotificationRepository')
    @patch('notifications.api.RabbitMQEventPublisher')
    def test_clear_all_action_uses_authenticated_user_scope(self, mock_publisher, mock_repository, mock_use_case):
        """Clear all debe delegar el borrado scoped al user_id autenticado."""
        mock_use_case_instance = Mock()
        mock_use_case.return_value = mock_use_case_instance

        request = self.factory.delete('/api/notifications/clear/')
        request.user = SimpleNamespace(id='user-1')

        viewset = NotificationViewSet()
        viewset.clear_all_use_case = mock_use_case_instance

        response = viewset.clear_all(request)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_use_case_instance.execute.assert_called_once()
        command = mock_use_case_instance.execute.call_args.args[0]
        assert command.user_id == 'user-1'
