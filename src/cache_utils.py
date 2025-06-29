from django.core.cache import cache
from functools import wraps
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

def cache_list_view(timeout=60):
    """
    Decorator to cache list view responses for specified timeout (in seconds)
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(view_instance, request, *args, **kwargs):
            # Don't cache for authenticated requests that are not GET
            if request.method != 'GET':
                return view_func(view_instance, request, *args, **kwargs)
            
            # Generate a unique cache key based on the URL and query params
            cache_key = f"view_cache_{request.path}_{hash(frozenset(request.GET.items()))}"
            
            # Try to get the result from cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Get the actual result
            result = view_func(view_instance, request, *args, **kwargs)
            
            # Cache the result
            cache.set(cache_key, result, timeout)
            
            return result
        return _wrapped_view
    return decorator

def cacheable_viewset(timeout=60):
    """
    Class decorator for ViewSets to apply caching to list and retrieve actions
    """
    def decorator(viewset_class):
        # Apply cache to list method
        original_list = viewset_class.list
        
        @method_decorator(cache_page(timeout))
        def cached_list(self, request, *args, **kwargs):
            return original_list(self, request, *args, **kwargs)
        
        viewset_class.list = cached_list
        
        # Add methods to clear cache on write operations
        original_create = viewset_class.create if hasattr(viewset_class, 'create') else None
        def create_and_invalidate_cache(self, request, *args, **kwargs):
            response = original_create(self, request, *args, **kwargs)
            # Simply clear the entire cache for now
            # This is not as efficient but works with all cache backends
            cache.clear()
            return response
        
        if original_create:
            viewset_class.create = create_and_invalidate_cache
            
        # Same for update
        original_update = viewset_class.update if hasattr(viewset_class, 'update') else None
        if original_update:
            def update_and_invalidate_cache(self, request, *args, **kwargs):
                response = original_update(self, request, *args, **kwargs)
                cache.clear()
                return response
            viewset_class.update = update_and_invalidate_cache
            
        # Same for destroy
        original_destroy = viewset_class.destroy if hasattr(viewset_class, 'destroy') else None
        if original_destroy:
            def destroy_and_invalidate_cache(self, request, *args, **kwargs):
                response = original_destroy(self, request, *args, **kwargs)
                cache.clear()
                return response
            viewset_class.destroy = destroy_and_invalidate_cache
        
        # Apply cache to retrieve method
        if hasattr(viewset_class, 'retrieve'):
            original_retrieve = viewset_class.retrieve
            
            @method_decorator(cache_page(timeout))
            def cached_retrieve(self, request, *args, **kwargs):
                return original_retrieve(self, request, *args, **kwargs)
            
            viewset_class.retrieve = cached_retrieve
        
        return viewset_class
    
    return decorator
