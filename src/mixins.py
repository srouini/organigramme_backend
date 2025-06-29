from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction

class BulkCreateModelMixin:
    """
    Mixin to add bulk create functionality to ModelViewSets.
    Supports creating multiple objects in a single request with a single database transaction.
    
    To use this mixin:
    1. Add it to your ViewSet inheritance chain
    2. Ensure your ViewSet has a valid serializer_class
    
    Example usage in API:
    POST /api/your-endpoint/bulk-create/
    {
        "items": [
            { "field1": "value1", "field2": "value2" },
            { "field1": "value3", "field2": "value4" }
        ]
    }
    """
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request, *args, **kwargs):
        """
        Create multiple objects in a single request.
        The request data should contain an 'items' key with a list of objects to create.
        """
        items = request.data.get('items', [])
        
        if not items:
            return Response(
                {'detail': 'No items provided for bulk creation.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Use a transaction to ensure atomicity - either all succeed or none
        with transaction.atomic():
            # Create a list serializer with many=True
            serializer = self.get_serializer(data=items, many=True)
            serializer.is_valid(raise_exception=True)
            self.perform_bulk_create(serializer)
            
        headers = self.get_success_headers(serializer.data)
        return Response(
            {
                'detail': f'Successfully created {len(serializer.data)} items.',
                'items': serializer.data
            },
            status=status.HTTP_201_CREATED,
            headers=headers
        )
    
    def perform_bulk_create(self, serializer):
        """
        Perform the bulk create operation.
        Override this method if you need custom behavior during bulk creation.
        """
        serializer.save()
    
    def get_success_headers(self, data):
        """
        Return success headers for the creation response.
        """
        try:
            return {'Location': str(data[0].get('id', ''))}
        except (TypeError, KeyError, IndexError):
            return {}


class BulkDeleteModelMixin:
    """
    Mixin to add bulk delete functionality to ModelViewSets.
    Supports deleting multiple objects in a single request with a single database transaction.
    
    To use this mixin:
    1. Add it to your ViewSet inheritance chain
    
    Example usage in API:
    POST /api/your-endpoint/bulk-delete/
    {
        "ids": [1, 2, 3, 4]
    }
    """
    
    @action(detail=False, methods=['post'])
    def bulk_delete(self, request, *args, **kwargs):
        """
        Delete multiple objects in a single request.
        The request data should contain an 'ids' key with a list of object IDs to delete.
        """
        ids = request.data.get('ids', [])
        
        if not ids:
            return Response(
                {'detail': 'No IDs provided for bulk deletion.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Use a transaction to ensure atomicity - either all succeed or none
        with transaction.atomic():
            queryset = self.filter_queryset(self.get_queryset())
            # Filter objects by provided IDs
            filtered_queryset = queryset.filter(id__in=ids)
            
            if filtered_queryset.count() == 0:
                return Response(
                    {'detail': 'No matching objects found for deletion.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Count before deletion to report number of deleted objects
            deletion_count = filtered_queryset.count()
            
            # Perform deletion with pre_delete and post_delete signals
            self.perform_bulk_delete(filtered_queryset)
            
        return Response(
            {'detail': f'Successfully deleted {deletion_count} objects.'},
            status=status.HTTP_200_OK
        )
    
    def perform_bulk_delete(self, queryset):
        """
        Perform the bulk delete operation.
        Override this method if you need custom behavior during bulk deletion.
        """
        # This will trigger pre_delete and post_delete signals for each object
        queryset.delete()


class BulkUpdateModelMixin:
    """
    Mixin to add bulk update functionality to ModelViewSets.
    Supports updating multiple objects in a single request with a single database transaction.
    
    To use this mixin:
    1. Add it to your ViewSet inheritance chain
    2. Ensure your ViewSet has a valid serializer_class
    
    Example usage in API:
    POST /api/your-endpoint/bulk-update/
    {
        "items": [
            {"id": 1, "field1": "new value1"},
            {"id": 2, "field1": "new value2"}
        ]
    }
    """
    
    @action(detail=False, methods=['post'])
    def bulk_update(self, request, *args, **kwargs):
        """
        Update multiple objects in a single request.
        The request data should contain an 'items' key with a list of objects to update.
        Each object must include its ID and the fields to update.
        """
        items = request.data.get('items', [])
        
        if not items:
            return Response(
                {'detail': 'No items provided for bulk update.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Use a transaction to ensure atomicity - either all succeed or none
        with transaction.atomic():
            # Extract IDs from items
            ids = [item.get('id') for item in items if 'id' in item]
            
            if not ids:
                return Response(
                    {'detail': 'All items must have an ID for bulk update.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get the objects to update
            queryset = self.filter_queryset(self.get_queryset())
            instances = queryset.filter(id__in=ids)
            
            # Create a mapping of id -> instance for quick access
            id_to_instance = {str(instance.id): instance for instance in instances}
            
            updated_instances = []
            for item in items:
                item_id = str(item.get('id'))
                if item_id in id_to_instance:
                    instance = id_to_instance[item_id]
                    # Create serializer for this instance
                    serializer = self.get_serializer(instance, data=item, partial=True)
                    serializer.is_valid(raise_exception=True)
                    self.perform_update(serializer)
                    updated_instances.append(serializer.data)
            
        return Response(
            {
                'detail': f'Successfully updated {len(updated_instances)} items.',
                'items': updated_instances
            },
            status=status.HTTP_200_OK
        )
    
    def perform_update(self, serializer):
        """
        Perform the update operation.
        Override this method if you need custom behavior during update.
        """
        serializer.save()
