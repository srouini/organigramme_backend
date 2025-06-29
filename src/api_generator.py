from django.urls import path, include
from rest_framework.routers import DefaultRouter
import graphene
from .dynamic_api import (
    generate_filter_set,
    generate_dynamic_viewset,
    generate_mutations,
    generate_query_fields
)

def register_model_api(model_class, router=None, schema=None):
    """
    Registers both REST and GraphQL APIs for a given model
    
    Args:
        model_class: The Django model class
        router: Optional REST framework router
        schema: Optional GraphQL schema to extend
    """
    # Generate filter set
    filter_class = generate_filter_set(model_class)
    
    # REST API setup
    if router:
        viewset = generate_dynamic_viewset(model_class, filter_class)
        router.register(
            model_class.__name__.lower(),
            viewset,
            basename=model_class.__name__.lower()
        )
    
    # GraphQL setup
    if schema:
        # Generate query fields
        query_fields, resolvers = generate_query_fields(model_class, filter_class)
        
        # Generate mutations
        mutations = generate_mutations(model_class)
        
        # Create Query type
        query_type = type(
            f'{model_class.__name__}Query',
            (graphene.ObjectType,),
            {**query_fields, **resolvers}
        )
        
        # Create Mutation type
        mutation_type = type(
            f'{model_class.__name__}Mutation',
            (graphene.ObjectType,),
            mutations
        )
        
        # Extend schema
        schema.query = type(
            'Query',
            (query_type, schema.query) if schema.query else (query_type, graphene.ObjectType),
            {}
        )
        
        schema.mutation = type(
            'Mutation',
            (mutation_type, schema.mutation) if schema.mutation else (mutation_type, graphene.ObjectType),
            {}
        )
