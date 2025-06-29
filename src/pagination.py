from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class CustomPageNumberPagination(PageNumberPagination):
    """
    Custom pagination class that allows disabling pagination when 'all=true' is provided.
    
    Usage:
    - Use standard pagination: /api/resource/?page=2
    - Get all records: /api/resource/?all=true
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'results': data
        })
    
    def paginate_queryset(self, queryset, request, view=None):
        if request.query_params.get('all', 'false').lower() == 'true':
            return None  # Return None to disable pagination
        return super().paginate_queryset(queryset, request, view)
