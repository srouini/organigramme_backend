"""
Utility functions for handling API query parameters
"""

def is_expanded(request, field_name):
    """
    Check if a specific field should be expanded based on request parameters
    
    Usage examples:
    - ?expand=field1,field2  (expands specific fields)
    - ?expand=all            (expands all possible fields)
    
    Args:
        request: The HTTP request object
        field_name: Name of the field to check
        
    Returns:
        Boolean indicating whether the field should be expanded
    """
    if not request or not hasattr(request, 'query_params'):
        return False
        
    expand_param = request.query_params.get('expand', '')
    
    if expand_param == 'all':
        return True
        
    expanded_fields = [field.strip() for field in expand_param.split(',') if field.strip()]
    return field_name in expanded_fields
