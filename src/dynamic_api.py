from typing import Type, Dict, Any, Tuple
from django.db import models
from django.db.models import Q, QuerySet
from rest_framework import viewsets, serializers, filters, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django_filters import rest_framework as drf_filters
import django_filters
import graphene
from graphene_django import DjangoObjectType
from graphql import GraphQLError
from polymorphic.models import PolymorphicModel
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from graphene_file_upload.scalars import Upload

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000

def generate_dynamic_serializer(model_class: Type[models.Model], expand_fields=None):
    """
    Dynamically generates a ModelSerializer for the given model class
    """
    # Get all properties from the model
    properties = {}
    for name in dir(model_class):
        if isinstance(getattr(model_class, name), property):
            properties[name] = serializers.CharField(read_only=True)

    # Get all foreign key fields
    foreign_key_fields = {
        field.name: field for field in model_class._meta.fields 
        if isinstance(field, models.ForeignKey)
    }

    # Create nested serializers for expanded fields
    nested_serializers = {}
    if expand_fields:
        for field_path in expand_fields:
            parts = field_path.split('.')
            field_name = parts[0]
            
            if field_name in foreign_key_fields:
                related_model = foreign_key_fields[field_name].related_model
                # If this is a nested expansion (e.g., mrn.navire), pass the remaining path
                nested_expand = ['.'.join(parts[1:])] if len(parts) > 1 else None
                nested_serializer = generate_dynamic_serializer(related_model, nested_expand)
                nested_serializers[field_name] = nested_serializer(read_only=True)

    meta_attrs = {
        'model': model_class,
        'fields': '__all__'
    }

    # Create the serializer class
    return type(
        f'{model_class.__name__}Serializer',
        (serializers.ModelSerializer,),
        {
            'Meta': type('Meta', (), meta_attrs),
            **properties,
            **nested_serializers
        }
    )

def generate_filter_set(model_class: Type[models.Model]):
    """
    Generates a FilterSet for the model with support for nested filtering
    """
    class DynamicFilterSet(django_filters.FilterSet):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Add year filters for date fields
            for field_name in list(self.filters.keys()):  # Create a list to avoid modification during iteration
                if '__' in field_name:  # Skip already processed lookups
                    continue
                    
                try:
                    field = self._meta.model._meta.get_field(field_name)
                    if isinstance(field, (models.DateField, models.DateTimeField)):
                        self.filters[f'{field_name}__year'] = django_filters.NumberFilter(field_name=field_name, lookup_expr='year')
                        self.filters[f'{field_name}__year__gt'] = django_filters.NumberFilter(field_name=field_name, lookup_expr='year__gt')
                        self.filters[f'{field_name}__year__lt'] = django_filters.NumberFilter(field_name=field_name, lookup_expr='year__lt')
                        self.filters[f'{field_name}__year__gte'] = django_filters.NumberFilter(field_name=field_name, lookup_expr='year__gte')
                        self.filters[f'{field_name}__year__lte'] = django_filters.NumberFilter(field_name=field_name, lookup_expr='year__lte')
                except django_filters.exceptions.FieldLookupError:
                    continue
                except models.FieldDoesNotExist:
                    continue

    filter_fields = {}
    
    def add_field_filters(field, prefix='', depth=0, max_depth=3):
        if depth > max_depth:
            return
            
        field_name = f"{prefix}{field.name}" if prefix else field.name
        
        if isinstance(field, models.CharField) or isinstance(field, models.TextField):
            filter_fields[field_name] = ['exact', 'icontains', 'isnull']
        elif isinstance(field, models.DateTimeField):
            filter_fields[field_name] = ['exact', 'gt', 'lt', 'gte', 'lte', 'isnull', 'date']
        elif isinstance(field, models.DateField):
            filter_fields[field_name] = ['exact', 'gt', 'lt', 'gte', 'lte', 'isnull']
        elif isinstance(field, (models.IntegerField, models.FloatField, models.DecimalField)):
            filter_fields[field_name] = ['exact', 'gt', 'lt', 'gte', 'lte', 'isnull']
        elif isinstance(field, models.BooleanField):
            filter_fields[field_name] = ['exact']
        elif isinstance(field, models.ForeignKey) and depth < max_depth:
            filter_fields[field_name] = ['exact', 'isnull']
            related_model = field.related_model
            for related_field in related_model._meta.fields:
                add_field_filters(related_field, f"{field_name}__", depth + 1)

    # Add filters for all fields
    for field in model_class._meta.fields:
        add_field_filters(field)

    # Create the FilterSet class
    meta_attrs = {
        'model': model_class,
        'fields': filter_fields
    }

    return type(
        f'{model_class.__name__}FilterSet',
        (DynamicFilterSet,),
        {'Meta': type('Meta', (), meta_attrs)}
    )

def generate_dynamic_viewset(model_class: Type[models.Model]):
    """
    Dynamically generates a ModelViewSet for the given model class with filtering
    """
    def get_all_foreign_key_paths(model, prefix='', max_depth=3, current_depth=0, processed_models=None):
        if processed_models is None:
            processed_models = set()
            
        if current_depth >= max_depth or model in processed_models:
            return []
            
        processed_models.add(model)
        paths = []
        
        for field in model._meta.fields:
            if isinstance(field, models.ForeignKey):
                current_path = f"{prefix}{field.name}" if prefix else field.name
                paths.append(current_path)
                
                # Recursively get paths for related model
                nested_paths = get_all_foreign_key_paths(
                    field.related_model,
                    f"{current_path}.",
                    max_depth,
                    current_depth + 1,
                    processed_models
                )
                paths.extend(nested_paths)
                
        processed_models.remove(model)
        return paths
    
    # Get all possible foreign key paths
    foreign_key_paths = get_all_foreign_key_paths(model_class)
    
    class DynamicViewSet(viewsets.ModelViewSet):
        queryset = model_class.objects.all()
        pagination_class = StandardResultsSetPagination
        filter_backends = [
            django_filters.rest_framework.DjangoFilterBackend,
            filters.SearchFilter,
            filters.OrderingFilter
        ]
        filterset_class = generate_filter_set(model_class)
        search_fields = [
            f.name for f in model_class._meta.fields 
            if isinstance(f, (models.CharField, models.TextField))
        ]
        ordering_fields = '__all__'

        def get_serializer_class(self):
            expand = self.request.query_params.get('expand', '').split(',')
            # Filter out empty strings and validate paths
            expand_fields = [
                field for field in expand 
                if field and field in foreign_key_paths
            ]
            return generate_dynamic_serializer(model_class, expand_fields)

        def get_queryset(self):
            queryset = super().get_queryset()
            expand = self.request.query_params.get('expand', '').split(',')
            # Filter out empty strings and validate paths
            expand_fields = [
                field for field in expand 
                if field and field in foreign_key_paths
            ]
            
            if expand_fields:
                # Convert dot notation to django's double-underscore notation for select_related
                select_related_fields = [field.replace('.', '__') for field in expand_fields]
                queryset = queryset.select_related(*select_related_fields)
            
            return queryset

        def paginate_queryset(self, queryset):
            """
            Return a single page of results, or `None` if pagination is disabled.
            """
            if self.request.query_params.get('all', '').lower() == 'true':
                return None
            return super().paginate_queryset(queryset)

        def list(self, request, *args, **kwargs):
            try:
                queryset = self.filter_queryset(self.get_queryset())
                
                # Check if pagination is disabled
                if request.query_params.get('all', '').lower() == 'true':
                    serializer = self.get_serializer(queryset, many=True)
                    return Response({
                        'status': 'success',
                        'count': queryset.count(),
                        'results': serializer.data
                    })
                
                # Use pagination
                page = self.paginate_queryset(queryset)
                if page is not None:
                    serializer = self.get_serializer(page, many=True)
                    response_data = self.get_paginated_response(serializer.data)
                    return Response({
                        'status': 'success',
                        'next': response_data.data.get('next'),
                        'previous': response_data.data.get('previous'),
                        'count': response_data.data.get('count'),
                        'results': response_data.data.get('results', [])
                    })

                serializer = self.get_serializer(queryset, many=True)
                return Response({
                    'status': 'success',
                    'count': queryset.count(),
                    'results': serializer.data
                })
            except Exception as e:
                return Response({
                    'status': 'error',
                    'message': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)

        def create(self, request, *args, **kwargs):
            try:
                response = super().create(request, *args, **kwargs)
                return Response({
                    'status': 'success',
                    'message': f'{model_class.__name__} created successfully',
                    'data': response.data
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({
                    'status': 'error',
                    'message': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)

        def update(self, request, *args, **kwargs):
            try:
                response = super().update(request, *args, **kwargs)
                return Response({
                    'status': 'success',
                    'message': f'{model_class.__name__} updated successfully',
                    'data': response.data
                })
            except Exception as e:
                return Response({
                    'status': 'error',
                    'message': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)

        def partial_update(self, request, *args, **kwargs):
            try:
                response = super().partial_update(request, *args, **kwargs)
                return Response({
                    'status': 'success',
                    'message': f'{model_class.__name__} partially updated successfully',
                    'data': response.data
                })
            except Exception as e:
                return Response({
                    'status': 'error',
                    'message': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)

        def destroy(self, request, *args, **kwargs):
            try:
                instance = self.get_object()
                instance_id = instance.id
                self.perform_destroy(instance)
                return Response({
                    'status': 'success',
                    'message': f'{model_class.__name__} with id {instance_id} deleted successfully'
                })
            except Exception as e:
                return Response({
                    'status': 'error',
                    'message': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)

        def retrieve(self, request, *args, **kwargs):
            try:
                response = super().retrieve(request, *args, **kwargs)
                return Response({
                    'status': 'success',
                    'data': response.data
                })
            except Exception as e:
                return Response({
                    'status': 'error',
                    'message': str(e)
                }, status=status.HTTP_404_NOT_FOUND)
    
    return DynamicViewSet

def generate_input_type(model_class: Type[models.Model], input_name: str) -> Type[graphene.InputObjectType]:
    """
    Generates an Input type for GraphQL mutations based on the model fields
    """
    meta_attrs = {'model': model_class}
    type_attrs = {}
    
    for field in model_class._meta.fields:
        # Skip auto-generated fields
        if field.name in ['id', 'created_at', 'updated_at']:
            continue
            
        # Map Django field types to Graphene types
        if isinstance(field, models.CharField) or isinstance(field, models.TextField):
            field_type = graphene.String
        elif isinstance(field, models.IntegerField):
            field_type = graphene.Int
        elif isinstance(field, models.FloatField):
            field_type = graphene.Float
        elif isinstance(field, models.BooleanField):
            field_type = graphene.Boolean
        elif isinstance(field, models.DateTimeField):
            field_type = graphene.DateTime
        elif isinstance(field, models.DateField):
            field_type = graphene.Date
        elif isinstance(field, models.ForeignKey):
            field_type = graphene.ID
        elif isinstance(field, models.FileField):  # Handles FileField and ImageField
            field_type = Upload
        else:
            # Default to String type for unknown field types
            field_type = graphene.String
            
        # Make the field optional for updates
        if input_name.startswith('Update'):
            type_attrs[field.name] = field_type(required=False)
        else:
            # For create operations, make the field required if it's required in the model
            type_attrs[field.name] = field_type(required=not field.null and not field.blank)
    
    # Create the Input type dynamically
    return type(input_name, (graphene.InputObjectType,), type_attrs)

# Cache to store created GraphQL types
_type_cache = {}
# Track types currently being generated to handle circular references
_generating_types = set()

def is_polymorphic_model(model_class):
    """Helper to check if a model is polymorphic"""
    return issubclass(model_class, PolymorphicModel)

# Special model handlers for polymorphic models that need custom relation handling
# Format: {'ModelName': (custom_fields_function, custom_resolvers_function)}
_special_model_handlers = {}

def register_special_model_handler(model_name, fields_func, resolvers_func):
    """
    Register a special handler for a model that needs custom field and resolver processing
    """
    _special_model_handlers[model_name] = (fields_func, resolvers_func)

# Special handler for FactureBase
def facture_base_fields():
    return ['id', 'numero', 'date', 'client', 'ht', 'tva', 'ttc', 'remise', 'debours', 'timber', 'status', 'paiements', 'lignes']

def facture_base_resolvers(properties, resolvers):
    from billing.models import PaiementFacture, LigneFacture
    
    # Add resolver for paiements
    def resolve_paiements(self, info):
        instance = self.get_real_instance() if hasattr(self, 'get_real_instance') else self
        concrete_class = instance.__class__.__name__
        
        # Different handling based on concrete class
        if concrete_class == 'Facture':
            from billing.models import PaiementFacture
            return PaiementFacture.objects.filter(facture=instance)
        elif concrete_class == 'FactureGroupage':
            from billing.models import PaiementFactureGroupage
            return PaiementFactureGroupage.objects.filter(facture_groupage=instance)
        elif concrete_class == 'FactureComplementaire':
            from billing.models import PaiementFactureComplementaire
            return PaiementFactureComplementaire.objects.filter(facture_complementaire=instance)
        elif concrete_class == 'FactureComplementaireGroupage':
            from billing.models import PaiementFactureComplementaireGroupage
            return PaiementFactureComplementaireGroupage.objects.filter(facture_complementaire_groupage=instance)
        elif concrete_class == 'FactureAvoire':
            # Add if there's a payment model for FactureAvoire
            pass
        
        return []
        
    resolvers['resolve_paiements'] = resolve_paiements
    
    # Need to return a generic PaiementBase type for polymorphic behavior
    def get_paiement_type():
        from billing.models import PaiementBase
        return generate_graphql_type(PaiementBase)
        
    properties['paiements'] = graphene.List(get_paiement_type)
    
    # Add resolver for lignes facture
    def resolve_lignes(self, info):
        instance = self.get_real_instance() if hasattr(self, 'get_real_instance') else self
        concrete_class = instance.__class__.__name__
        
        # Different handling based on concrete class
        if concrete_class == 'Facture':
            from billing.models import LigneFacture
            return LigneFacture.objects.filter(facture=instance)
        elif concrete_class == 'FactureGroupage':
            from billing.models import LigneFactureGroupage
            return LigneFactureGroupage.objects.filter(facture_groupage=instance)
        elif concrete_class == 'FactureAvoireGroupage':
            from billing.models import LigneFactureAvoireGroupage
            return LigneFactureAvoireGroupage.objects.filter(facture_avoire_groupage=instance)
        elif concrete_class == 'FactureComplementaireGroupage':
            from billing.models import LigneFactureComplementaireGroupage
            return LigneFactureComplementaireGroupage.objects.filter(facture_complementaire_groupage=instance)
        
        return []
        
    resolvers['resolve_lignes'] = resolve_lignes
    
    # Need to return a generic LigneFactureBase type for polymorphic behavior
    def get_ligne_type():
        from billing.models import LigneFactureBase
        return generate_graphql_type(LigneFactureBase)
        
    properties['lignes'] = graphene.List(get_ligne_type)

# Register the FactureBase handler
register_special_model_handler('FactureBase', facture_base_fields, facture_base_resolvers)

def generate_filter_schema(model_class: Type[models.Model]) -> Type[graphene.InputObjectType]:
    """
    Generates an input type for filtering. This is similar to a Django Q object, but
    in GraphQL format.
    """
    model_name = model_class.__name__
    attrs = {}
    
    # Add standard ID filters that should be available for all models
    attrs['id'] = graphene.ID(description=f"Filter by exact {model_name} ID")
    attrs['id_in'] = graphene.List(graphene.ID, description=f"Filter by multiple {model_name} IDs")

    # For polymorphic models, add polymorphicType filters
    if is_polymorphic_model(model_class):
        # Get all concrete subclasses
        concrete_types = [cls.__name__ for cls in model_class.__subclasses__()]
        
        # Add a field to filter by polymorphic type (exact match)
        attrs['polymorphicType'] = graphene.String(
            description=f"Filter by concrete type. Options: {', '.join(concrete_types)}"
        )
        
        # Add a field to filter by a list of polymorphic types
        attrs['polymorphicType_in'] = graphene.List(
            graphene.String, 
            description=f"Filter by multiple concrete types. Options: {', '.join(concrete_types)}"
        )

    # Add filters for all fields
    for field in model_class._meta.fields:
        field_name = field.name
        
        # Skip if it's a primary key
        if field.primary_key and field_name == 'id':
            attrs['id'] = graphene.ID()
            attrs['id_in'] = graphene.List(graphene.ID)
            continue
        
        # Skip hidden polymorphic model-specific fields 
        if field_name in ['polymorphic_ctype']:
            continue
            
        # Handle different field types
        if isinstance(field, models.CharField) or isinstance(field, models.TextField):
            attrs[field_name] = graphene.String()
            attrs[f'{field_name}_contains'] = graphene.String()
            attrs[f'{field_name}_icontains'] = graphene.String()
            attrs[f'{field_name}_in'] = graphene.List(graphene.String)
            attrs[f'{field_name}_startswith'] = graphene.String()
            attrs[f'{field_name}_istartswith'] = graphene.String()
            attrs[f'{field_name}_endswith'] = graphene.String()
            attrs[f'{field_name}_iendswith'] = graphene.String()
        elif isinstance(field, models.BooleanField):
            attrs[field_name] = graphene.Boolean()
        elif isinstance(field, models.DateField) or isinstance(field, models.DateTimeField):
            attrs[field_name] = graphene.String()
            attrs[f'{field_name}_gt'] = graphene.String()
            attrs[f'{field_name}_lt'] = graphene.String()
            attrs[f'{field_name}_gte'] = graphene.String()
            attrs[f'{field_name}_lte'] = graphene.String()
            attrs[f'{field_name}_year'] = graphene.Int()
            attrs[f'{field_name}_month'] = graphene.Int()
            attrs[f'{field_name}_day'] = graphene.Int()
            attrs[f'{field_name}_year__gt'] = graphene.Int()
            attrs[f'{field_name}_year__lt'] = graphene.Int()
            attrs[f'{field_name}_year__gte'] = graphene.Int()
            attrs[f'{field_name}_year__lte'] = graphene.Int()
        elif isinstance(field, (models.IntegerField, models.FloatField, models.DecimalField)):
            attrs[field_name] = graphene.Float()
            attrs[f'{field_name}_gt'] = graphene.Float()
            attrs[f'{field_name}_lt'] = graphene.Float()
            attrs[f'{field_name}_gte'] = graphene.Float()
            attrs[f'{field_name}_lte'] = graphene.Float()
        elif isinstance(field, models.ForeignKey):
            attrs[field_name] = graphene.ID()
            attrs[f'{field_name}_id'] = graphene.ID()
            attrs[f'{field_name}_id_in'] = graphene.List(graphene.ID)

            # Add nested relation filters (up to 3 levels deep)
            related_model = field.related_model
            
            # Level 1 nested filters (direct relation)
            for related_field in related_model._meta.fields:
                if related_field.primary_key and related_field.name == 'id':
                    # Skip primary key as we already have _id filter
                    continue
                
                # Skip hidden polymorphic model-specific fields
                if related_field.name in ['polymorphic_ctype']:
                    continue
                
                # Use snake_case naming for nested filters (e.g., article_numero)
                nested_field_name = f"{field_name}_{related_field.name}"
                
                # Add appropriate filters based on field type
                if isinstance(related_field, models.CharField) or isinstance(related_field, models.TextField):
                    attrs[nested_field_name] = graphene.String()
                    attrs[f'{nested_field_name}_contains'] = graphene.String()
                    attrs[f'{nested_field_name}_icontains'] = graphene.String()
                elif isinstance(related_field, models.BooleanField):
                    attrs[nested_field_name] = graphene.Boolean()
                elif isinstance(related_field, models.DateField) or isinstance(related_field, models.DateTimeField):
                    attrs[nested_field_name] = graphene.String()
                    attrs[f'{nested_field_name}_gt'] = graphene.String()
                    attrs[f'{nested_field_name}_lt'] = graphene.String()
                elif isinstance(related_field, (models.IntegerField, models.FloatField, models.DecimalField)):
                    attrs[nested_field_name] = graphene.Float()
                    attrs[f'{nested_field_name}_gt'] = graphene.Float()
                    attrs[f'{nested_field_name}_lt'] = graphene.Float()
                elif isinstance(related_field, models.ForeignKey):
                    # Level 2 nested filters (relation of relation)
                    second_related_model = related_field.related_model
                    # Filter by ID (e.g., article_mrn_id)
                    attrs[f"{nested_field_name}_id"] = graphene.ID()
                    attrs[f"{nested_field_name}_id_in"] = graphene.List(graphene.ID)
                    
                    # Add second level nested fields (e.g., article_mrn_numero)
                    for second_related_field in second_related_model._meta.fields:
                        if second_related_field.primary_key and second_related_field.name == 'id':
                            # Skip primary key
                            continue
                        
                        # Skip hidden polymorphic model-specific fields
                        if second_related_field.name in ['polymorphic_ctype']:
                            continue
                        
                        # Use snake_case naming (e.g., article_mrn_numero)
                        second_nested_field_name = f"{nested_field_name}_{second_related_field.name}"
                        
                        # Add appropriate filters based on field type
                        if isinstance(second_related_field, models.CharField) or isinstance(second_related_field, models.TextField):
                            attrs[second_nested_field_name] = graphene.String()
                            attrs[f'{second_nested_field_name}_contains'] = graphene.String()
                            attrs[f'{second_nested_field_name}_icontains'] = graphene.String()
                        elif isinstance(second_related_field, models.BooleanField):
                            attrs[second_nested_field_name] = graphene.Boolean()
                        elif isinstance(second_related_field, models.DateField) or isinstance(second_related_field, models.DateTimeField):
                            attrs[second_nested_field_name] = graphene.String()
                            attrs[f'{second_nested_field_name}_gt'] = graphene.String()
                            attrs[f'{second_nested_field_name}_lt'] = graphene.String()
                        elif isinstance(second_related_field, (models.IntegerField, models.FloatField, models.DecimalField)):
                            attrs[second_nested_field_name] = graphene.Float()
                            attrs[f'{second_nested_field_name}_gt'] = graphene.Float()
                            attrs[f'{second_nested_field_name}_lt'] = graphene.Float()
                        elif isinstance(second_related_field, models.ForeignKey):
                            # Level 3 nested filters (relation of relation of relation)
                            third_related_model = second_related_field.related_model
                            
                            # Limit to ID only to avoid explosion of filters
                            # This allows filtering like article_mrn_regime_id
                            third_nested_field_name = f"{second_nested_field_name}_id"
                            attrs[third_nested_field_name] = graphene.ID()
                            attrs[f"{third_nested_field_name}_in"] = graphene.List(graphene.ID)

    # Add logical operators
    attrs['AND'] = graphene.List(
        lambda: filter_type, 
        description="Logical AND on all given filters."
    )
    attrs['OR'] = graphene.List(
        lambda: filter_type, 
        description="Logical OR on all given filters."
    )
    attrs['NOT'] = graphene.InputField(
        lambda: filter_type,
        description="Logical NOT on all given filters combined."
    )

    filter_type = type(
        f'{model_name}Filter',
        (graphene.InputObjectType,),
        attrs
    )
    
    return filter_type

def apply_filters(model_class: Type[models.Model], filters: Dict, queryset: QuerySet) -> QuerySet:
    """
    Apply a GraphQL filter object to a queryset
    """
    if not filters:
        return queryset
    
    filter_q = build_q_filter(model_class, filters)
    return queryset.filter(filter_q)

def build_q_filter(model_class: Type[models.Model], filters: Dict) -> Q:
    """
    Recursively build a Q object from a GraphQL filter object
    """
    q = Q()
    
    for key, value in filters.items():
        if key == 'AND' and value:
            # Logical AND
            for filter_obj in value:
                q &= build_q_filter(model_class, filter_obj)
        elif key == 'OR' and value:
            # Logical OR
            or_q = Q()
            for filter_obj in value:
                or_q |= build_q_filter(model_class, filter_obj)
            q &= or_q
        elif key == 'NOT' and value:
            # Logical NOT
            q &= ~build_q_filter(model_class, value)
        elif key == 'polymorphicType' and value and is_polymorphic_model(model_class):
            # Handle polymorphicType filter
            # This will filter to only include objects of the specified concrete type
            concrete_models = {cls.__name__: cls for cls in model_class.__subclasses__()}
            
            if value in concrete_models:
                content_type = ContentType.objects.get_for_model(concrete_models[value])
                q &= Q(polymorphic_ctype=content_type)
        
        elif key == 'polymorphicType_in' and value and is_polymorphic_model(model_class):
            # Handle polymorphicType_in filter for multiple concrete types
            concrete_models = {cls.__name__: cls for cls in model_class.__subclasses__()}
            valid_models = [concrete_models[name] for name in value if name in concrete_models]
            
            if valid_models:
                content_types = [ContentType.objects.get_for_model(model) for model in valid_models]
                q &= Q(polymorphic_ctype__in=content_types)
        
        elif key not in ['AND', 'OR', 'NOT', 'polymorphicType', 'polymorphicType_in']:
            # Regular field filter
            django_key = key
            
            # Handle comparison operators (_gt, _lt, _gte, _lte, etc.)
            lookup_expr = 'exact'  # Default lookup
            
            # Check for common filter suffixes
            filter_suffixes = ['_gt', '_lt', '_gte', '_lte', '_in', '_contains', '_icontains', 
                              '_startswith', '_istartswith', '_endswith', '_iendswith', '_year', '_month', '_day']
            
            for suffix in filter_suffixes:
                if django_key.endswith(suffix):
                    field_name_part = django_key[:-len(suffix)]
                    lookup_expr = suffix[1:]  # Remove the leading underscore
                    django_key = f"{field_name_part}__{lookup_expr}"
                    break
            
            # Handle nested relations (convert underscores to double underscores for Django ORM)
            if '_' in django_key and not any(django_key.endswith(f'__{suffix}') for suffix in filter_suffixes) and lookup_expr == 'exact':
                # This check handles cases like 'article_mrn_id'
                # It checks if there's an underscore and it's not already part of a lookup expression like '_gt'
                parts = django_key.split('_')
                
                # Try to intelligently convert underscores to double underscores for relations
                # We need to check if each part corresponds to a valid FK relationship
                current_model = model_class
                possible_django_key = parts[0]
                valid_relation = False
                for i in range(len(parts) - 1):
                    part = parts[i]
                    next_part = parts[i+1]
                    try:
                        field = current_model._meta.get_field(part)
                        if isinstance(field, models.ForeignKey):
                            # It's a valid relation part
                            possible_django_key += f'__{next_part}'
                            current_model = field.related_model
                            if i == len(parts) - 2: # Reached the end of parts, successful conversion
                                valid_relation = True
                        else:
                            # Not a ForeignKey, stop processing as a relation
                            break 
                    except models.FieldDoesNotExist:
                        # Not a field, stop processing as a relation
                        break
                
                if valid_relation:
                    django_key = possible_django_key

            # Special handling for _id fields if not already handled by nested logic
            if django_key.endswith('_id') and lookup_expr == 'exact' and '__' not in django_key:
                # Convert _id fields to Django format only if it's not already part of a lookup
                # or a nested relation processed above
                django_key = django_key[:-3]  # Remove _id suffix
            
            q &= Q(**{django_key: value})
    
    return q

def generate_graphql_type(model_class: Type[models.Model], filter_class=None) -> Type[DjangoObjectType]:
    """
    Dynamically generates a GraphQL type for the given model class
    """
    # Check if we already have a type for this model to avoid duplicates
    model_name = model_class.__name__
    if model_name in _type_cache:
        return _type_cache[model_name]
    
    # If this type is currently being generated elsewhere in the stack,
    # return a placeholder that will be filled later to break circular dependencies
    if model_name in _generating_types:
        # Create a placeholder type that only has the name
        placeholder_type = type(
            f'{model_name}Type',
            (graphene.ObjectType,),
            {'Meta': type('Meta', (), {'name': f'{model_name}Type'})}
        )
        # Cache it so we can reference it
        _type_cache[model_name] = placeholder_type
        return placeholder_type
    
    # Mark this type as currently being generated
    _generating_types.add(model_name)
    
    # Get all properties from the model
    properties = {}
    for name in dir(model_class):
        if isinstance(getattr(model_class, name), property):
            properties[name] = graphene.String()
    
    # Create resolvers for properties
    resolvers = {}
    for name in properties:
        def create_resolver(prop_name):
            def resolver(self, info):
                value = getattr(self, prop_name)
                return str(value) if value is not None else None
            return resolver
        resolvers[f'resolve_{name}'] = create_resolver(name)
    
    # Special handling for polymorphic models
    if is_polymorphic_model(model_class):
        def resolve_polymorphic_type(self, info):
            return self.get_real_instance_class().__name__
            
        resolvers['resolve_polymorphic_type'] = resolve_polymorphic_type
        properties['polymorphic_type'] = graphene.String()
    
    # Define Meta class with model and fields
    # Check if this model has a special handler
    if model_name in _special_model_handlers:
        fields_func, resolvers_func = _special_model_handlers[model_name]
        # Get custom fields
        fields = fields_func()
        meta_attrs = {
            'model': model_class,
            'fields': fields,
            'use_connection': False  # Disable Relay connections by default
        }
        # Add custom resolvers and properties
        resolvers_func(properties, resolvers)
    else:
        # Default Meta for other models
        meta_attrs = {
            'model': model_class,
            'fields': '__all__',
            'use_connection': False  # Disable Relay connections by default
        }
    
    # Defer adding reverse relation fields until after the type is created
    deferred_relations = []
    
    # Capture reverse relation information for later processing
    for related_object in model_class._meta.get_fields(include_hidden=True):
        # Check if it's a relation field coming from another model
        if hasattr(related_object, 'field') and hasattr(related_object, 'related_model'):
            rel_info = None
            # IMPORTANT: Check for OneToOneRel *before* ManyToOneRel, as OneToOneRel inherits from ManyToOneRel
            if isinstance(related_object, models.OneToOneRel):
                rel_info = {
                    'type': 'one-to-one',
                    'related_model': related_object.related_model,
                    'field_name': related_object.field.name,
                    'accessor_name': related_object.get_accessor_name()
                }
            elif isinstance(related_object, models.ManyToOneRel):
                # This will catch standard ForeignKeys from other models
                rel_info = {
                    'type': 'many-to-one',
                    'related_model': related_object.related_model,
                    'field_name': related_object.field.name,
                    'accessor_name': related_object.get_accessor_name()
                }
            # We might also need to handle ManyToManyRel explicitly if needed later
            # elif isinstance(related_object, models.ManyToManyRel):
            #     pass 
                
            if rel_info:
                deferred_relations.append(rel_info)
    
    # Create the type dynamically with properties and resolvers
    attrs = {
        'Meta': type('Meta', (), meta_attrs),
        **properties,
        **resolvers
    }
    
    # Create the type class
    type_class = type(
        f'{model_class.__name__}Type',
        (DjangoObjectType,),
        attrs
    )
    
    # Add the is_type_of method needed for polymorphic models
    if is_polymorphic_model(model_class):
        def is_type_of(cls, obj, info):
            # Handle concrete subclasses properly
            if isinstance(obj, cls._meta.model):
                return True
            return False
            
        type_class.is_type_of = classmethod(is_type_of)
    
    # Cache the created type
    _type_cache[model_name] = type_class
    
    # Remove from generating set as we're done with initial creation
    _generating_types.remove(model_name)
    
    # Process deferred relations now that the type is created
    for relation_info in deferred_relations:
        # Skip for models with special handlers
        if model_name in _special_model_handlers:
            continue
            
        related_model = relation_info['related_model']
        field_name = relation_info['field_name']
        accessor_name = relation_info['accessor_name']
        relation_type = relation_info['type']

        # Create a safe thunk for the field type
        def make_type_thunk(rel_model_name):
            def get_type():
                # Since this is called at runtime during field resolution,
                # the type should be fully created by then
                cached_type = _type_cache.get(f'{rel_model_name}Type')
                if cached_type is None:
                    # Attempt to generate if missing (should be rare)
                    generate_graphql_type(rel_model_name)
                    cached_type = _type_cache.get(f'{rel_model_name}Type')
                return cached_type
            return get_type

        # Add field and resolver based on relation type
        if relation_type == 'many-to-one':
            # Create a resolver for this relation with proper closure binding
            def make_many_resolver(acc_name):
                def resolver(self, info):
                    # Get concrete instance for polymorphic model
                    instance = self.get_real_instance() if hasattr(self, 'get_real_instance') else self
                    # Use the reverse manager directly
                    manager = getattr(instance, acc_name)
                    return manager.all()
                return resolver
            
            # Add resolver
            resolver_name = f'resolve_{accessor_name}'
            resolver = make_many_resolver(accessor_name)
            setattr(type_class, resolver_name, resolver)
            
            # Add field - using List's ability to handle thunks
            rel_field = graphene.List(make_type_thunk(related_model.__name__))
            setattr(type_class, accessor_name, rel_field)

        elif relation_type == 'one-to-one':
            # Create a resolver for the OneToOne relation
            def make_one_resolver(acc_name):
                def resolver(self, info):
                    instance = self.get_real_instance() if hasattr(self, 'get_real_instance') else self
                    try:
                        # Access the related object directly
                        return getattr(instance, acc_name)
                    except models.ObjectDoesNotExist:
                        return None
                return resolver
            
            # Add resolver
            resolver_name = f'resolve_{accessor_name}'
            resolver = make_one_resolver(accessor_name)
            setattr(type_class, resolver_name, resolver)
            
            # Add field - using Field's ability to handle thunks
            rel_field = graphene.Field(make_type_thunk(related_model.__name__))
            setattr(type_class, accessor_name, rel_field)

    # For polymorphic models, recursively create types for all child models
    if is_polymorphic_model(model_class):
        for subclass in model_class.__subclasses__():
            # Generate GraphQL type for the subclass
            generate_graphql_type(subclass, filter_class)
    
    return type_class

def generate_query_fields(model_class: Type[models.Model], filter_class=None, processed_models=None, current_depth=0, max_depth=3) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Generates query fields for listing and retrieving individual items
    """
    if processed_models is None:
        processed_models = set()

    if model_class in processed_models or current_depth > max_depth:
        return {}, {}

    processed_models.add(model_class)
    
    model_name = model_class.__name__.lower()
    type_class = generate_graphql_type(model_class)

    # Create OrderEnum for sorting direction
    OrderEnum = graphene.Enum(
        f'{model_class.__name__}OrderEnum',
        [('ASC', 'asc'), ('DESC', 'desc')]
    )

    # Create OrderByInput type for sorting
    class OrderByInput(graphene.InputObjectType):
        class Meta:
            name = f'{model_class.__name__}OrderByInput'

        field = graphene.String(required=True)
        direction = OrderEnum(default_value='ASC')

    # Create PageInfo type
    class PageInfo(graphene.ObjectType):
        has_next_page = graphene.Boolean(required=True)
        has_previous_page = graphene.Boolean(required=True)
        total_count = graphene.Int(required=True)
        page_size = graphene.Int(required=True)
        current_page = graphene.Int(required=True)
        total_pages = graphene.Int(required=True)

    # Create Connection type
    class ListType(graphene.ObjectType):
        class Meta:
            name = f'{model_class.__name__}ListType'

        page_info = graphene.Field(PageInfo, required=True)
        results = graphene.List(type_class, required=True)

    # Generate filter arguments based on model fields
    filter_args = {}
    
    def add_field_filters(field, prefix='', depth=0):
        field_name = f"{prefix}{field.name}" if prefix else field.name
        
        if isinstance(field, models.CharField) or isinstance(field, models.TextField):
            filter_args[field_name] = graphene.String()
            filter_args[f'{field_name}_contains'] = graphene.String()
            filter_args[f'{field_name}_icontains'] = graphene.String()
            filter_args[f'{field_name}_in'] = graphene.List(graphene.String)
            filter_args[f'{field_name}_startswith'] = graphene.String()
            filter_args[f'{field_name}_istartswith'] = graphene.String()
            filter_args[f'{field_name}_endswith'] = graphene.String()
            filter_args[f'{field_name}_iendswith'] = graphene.String()
        elif isinstance(field, models.BooleanField):
            filter_args[field_name] = graphene.Boolean()
        elif isinstance(field, models.DateField) or isinstance(field, models.DateTimeField):
            filter_args[field_name] = graphene.DateTime()
            filter_args[f'{field_name}_gt'] = graphene.DateTime()
            filter_args[f'{field_name}_lt'] = graphene.DateTime()
            filter_args[f'{field_name}_gte'] = graphene.DateTime()
            filter_args[f'{field_name}_lte'] = graphene.DateTime()
            filter_args[f'{field_name}_isnull'] = graphene.Boolean()
            filter_args[f'{field_name}_date'] = graphene.Date()
            filter_args[f'{field_name}_year'] = graphene.Int()
            filter_args[f'{field_name}_year__gt'] = graphene.Int()
            filter_args[f'{field_name}_year__lt'] = graphene.Int()
            filter_args[f'{field_name}_year__gte'] = graphene.Int()
            filter_args[f'{field_name}_year__lte'] = graphene.Int()
        elif isinstance(field, (models.IntegerField, models.FloatField, models.DecimalField)):
            filter_args[field_name] = graphene.Float()
            filter_args[f'{field_name}_gt'] = graphene.Float()
            filter_args[f'{field_name}_lt'] = graphene.Float()
            filter_args[f'{field_name}_gte'] = graphene.Float()
            filter_args[f'{field_name}_lte'] = graphene.Float()
            filter_args[f'{field_name}_isnull'] = graphene.Boolean()
        elif isinstance(field, models.ForeignKey) and depth < max_depth:
            filter_args[field_name] = graphene.ID()
            filter_args[f'{field_name}_id'] = graphene.ID()
            filter_args[f'{field_name}_id_in'] = graphene.List(graphene.ID)
            
            # Add filters for related model fields
            related_model = field.related_model
            if related_model not in processed_models:
                processed_models.add(related_model)
                for related_field in related_model._meta.fields:
                    # Recursively add filters for the related model's fields
                    add_field_filters(related_field, f"{field_name}__", depth + 1)
                processed_models.remove(related_model)

    # Add filters for all fields
    for field in model_class._meta.fields:
        add_field_filters(field)

    # Get sortable fields
    sortable_fields = []
    for field in model_class._meta.fields:
        sortable_fields.append(field.name)
        if isinstance(field, models.ForeignKey):
            # Add related model fields for sorting
            related_model = field.related_model
            for related_field in related_model._meta.fields:
                sortable_fields.append(f"{field.name}__{related_field.name}")

    # Create filter type if not provided
    if not filter_class:
        filter_class = generate_filter_schema(model_class)

    # Add pagination and ordering arguments only to the graphene.Field below
    # (not adding them here to avoid duplication)
    
    # For polymorphic types, add a field to filter by specific type
    if is_polymorphic_model(model_class):
        # Add field to filter by polymorphic type
        polymorphic_types = [cls.__name__ for cls in model_class.__subclasses__()]
        filter_args['polymorphic_type'] = graphene.String(
            description=f"Filter by polymorphic type. Available types: {', '.join(polymorphic_types)}"
        )
    
    # Resolver for list
    def resolve_list(parent, info, **kwargs):
        # Create queryset starting with all objects
        qs = model_class.objects.all()

        # Apply search term if provided
        search_term = kwargs.get('search')
        if search_term:
            searchable_fields = [
                f.name for f in model_class._meta.fields 
                if isinstance(f, (models.CharField, models.TextField))
            ]
            if searchable_fields:
                q_objects = Q()
                for field_name in searchable_fields:
                    q_objects |= Q(**{f"{field_name}__icontains": search_term})
                # Apply the filter if q_objects is not empty (i.e., if searchable fields exist and search term was provided)
                if q_objects: 
                    qs = qs.filter(q_objects)
                    
        # Handle direct ID filtering efficiently
        id_value = kwargs.get('id')
        if id_value is not None:
            qs = qs.filter(id=id_value)
            
        # Handle ID list filtering with 'in' operator
        id_in_values = kwargs.get('id_in')
        if id_in_values is not None:
            qs = qs.filter(id__in=id_in_values)
            
        # Handle foreign key attribute filtering
        # Iterate through all kwargs to find those matching foreign key patterns
        for key, value in list(kwargs.items()):
            # Skip processed keys and standard pagination/filter arguments
            if key in ['id', 'id_in', 'page', 'page_size', 'all', 'order_by', 'filter', 'search'] or value is None:
                continue
                
            # Check if the filter is for a foreign key relationship
            if '__' in key and not key.endswith('__in'):
                parts = key.split('__')
                if len(parts) >= 2:
                    try:
                        # Try to build a path to check if this is a valid relationship
                        current_model = model_class
                        for i in range(len(parts) - 1):
                            field = current_model._meta.get_field(parts[i])
                            if isinstance(field, models.ForeignKey):
                                current_model = field.related_model
                            else:
                                break
                        # If we made it here, it's a valid foreign key path, apply the filter
                        qs = qs.filter(**{key: value})
                        # Remove this key from the kwargs so it's not processed again
                        kwargs.pop(key, None)
                    except (models.FieldDoesNotExist, AttributeError):
                        # Not a valid foreign key path, let it be processed normally
                        pass
                        
            # Handle foreign key ID list filtering with 'in' operator
            elif key.endswith('__in'):
                base_field = key.replace('__in', '')
                
                # Handle both direct foreign keys and nested ones (article_client_id__in or article__client_id__in)
                if '__' in base_field:
                    # This could be a nested relationship with IN operator (e.g., article__client_id__in)
                    parts = base_field.split('__')
                    
                    try:
                        # Validate the relationship path
                        current_model = model_class
                        valid_path = True
                        
                        for i in range(len(parts)):
                            field_name = parts[i]
                            try:
                                field = current_model._meta.get_field(field_name)
                                
                                # If it's a foreign key and not the last part, follow the relation
                                if isinstance(field, models.ForeignKey) and i < len(parts) - 1:
                                    current_model = field.related_model
                                # Last part should be 'id' or a valid field of the final model
                                elif i == len(parts) - 1:
                                    if field_name != 'id' and not hasattr(current_model, field_name):
                                        valid_path = False
                                else:
                                    valid_path = False
                                    break
                            except models.FieldDoesNotExist:
                                valid_path = False
                                break
                        
                        if valid_path and isinstance(value, list):
                            # Path is valid, apply the filter
                            django_filter_key = key.replace('_', '__')
                            # For keys like article_client_id__in, convert to article__client__id__in
                            if '_id__in' in django_filter_key and django_filter_key.count('__') == 1:
                                parts = django_filter_key.split('_id__in')
                                django_filter_key = f"{parts[0]}__id__in"
                            
                            qs = qs.filter(**{django_filter_key: value})
                            # Remove this key from kwargs
                            kwargs.pop(key, None)
                    except (models.FieldDoesNotExist, AttributeError) as e:
                        # Not a valid relationship path
                        pass
                else:
                    # Standard foreign key case (e.g., article_id__in)
                    try:
                        field = model_class._meta.get_field(base_field)
                        if isinstance(field, models.ForeignKey) and isinstance(value, list):
                            qs = qs.filter(**{key: value})
                            # Remove this key from kwargs
                            kwargs.pop(key, None)
                    except (models.FieldDoesNotExist, AttributeError):
                        # Not a valid field
                        pass
        
        # Extract and process filter arguments
        filter_dict = {}
        
        # Process all filter arguments
        for key, value in kwargs.items():
            if key not in ['page', 'page_size', 'all', 'order_by', 'filter', 'search'] and value is not None:
                filter_dict[key] = value
        
        # Apply the new filter system if filter parameter is provided
        if 'filter' in kwargs and kwargs['filter']:
            # Special handling for polymorphic filters without needing special fields
            if is_polymorphic_model(model_class) and hasattr(model_class, 'get_real_concrete_instance_class'):
                # Check if we're filtering by polymorphic type
                filter_data = kwargs['filter']
                
                # If filtering by polymorphic type directly, use Django's ORM
                if 'polymorphicType' in filter_data:
                    concrete_type = filter_data.pop('polymorphicType')
                    concrete_models = {cls.__name__: cls for cls in model_class.__subclasses__()}
                    
                    if concrete_type in concrete_models:
                        # Replace the queryset with one for the specific model type
                        content_type = ContentType.objects.get_for_model(concrete_models[concrete_type])
                        qs = qs.filter(polymorphic_ctype=content_type)
                
                # If filtering by multiple polymorphic types, use Django's ORM with __in
                if 'polymorphicType_in' in filter_data:
                    type_list = filter_data.pop('polymorphicType_in')
                    concrete_models = {cls.__name__: cls for cls in model_class.__subclasses__()}
                    valid_models = [concrete_models[name] for name in type_list if name in concrete_models]
                    
                    if valid_models:
                        content_types = [ContentType.objects.get_for_model(model) for model in valid_models]
                        qs = qs.filter(polymorphic_ctype__in=content_types)
            
            # Now apply the remaining filters
            qs = apply_filters(model_class, kwargs['filter'], qs)
        # Also apply any legacy filters
        elif filter_dict:
            qs = qs.filter(**filter_dict)

        # For polymorphic models, we need to get real instances before applying order or pagination
        all_results = []
        if is_polymorphic_model(model_class):
            # If this is the base polymorphic class, get all real instances
            for obj in qs:
                if hasattr(obj, 'get_real_instance'):
                    # Get the actual subclass instance
                    real_obj = obj.get_real_instance()
                    all_results.append(real_obj)
                else:
                    all_results.append(obj)
        else:
            all_results = list(qs)
        
        # Get total count before pagination
        total_count = len(all_results)
        
        # Handle ordering
        order_by = kwargs.get('order_by', None)
        if order_by and all_results:
    
            for sort_item in order_by:
                field = sort_item.field
                direction_value = sort_item.direction
                
                # Handle all possible direction value formats
                if hasattr(direction_value, 'name'):  # GraphQL enum object
                    direction_str = direction_value.name
                elif hasattr(direction_value, 'value'):  # Custom enum object
                    direction_str = direction_value.value
                else:
                    direction_str = str(direction_value)
                
                is_descending = direction_str.upper() == 'DESC'
                
                # Try to get some field values to determine if it's numeric
                try:
                    sample_values = []
                    for obj in all_results[:5]:
                        val = getattr(obj, field, None)
                        sample_values.append(val)
                    
                    # Check if field appears to be numeric
                    is_numeric = any(isinstance(val, (int, float, complex)) or 
                                     (hasattr(val, 'to_decimal') or hasattr(val, 'real')) 
                                     for val in sample_values if val is not None)
                    
                    if is_numeric:                        
                        # Specialized sorting for numeric fields
                        def numeric_key(obj):
                            val = getattr(obj, field, None)
                            if val is None:
                                # Handle None values
                                return float('-inf') if is_descending else float('inf')
                            try:
                                # Try to convert to float
                                return float(val)
                            except (TypeError, ValueError):
                                # Fall back to string comparison if not convertible
                                return str(val)
                        
                        all_results.sort(key=numeric_key, reverse=is_descending)
                    else:
                        # Regular sorting for non-numeric fields
                        all_results.sort(key=lambda obj: getattr(obj, field, None), reverse=is_descending)
                        
                except Exception as e:
                    # Default sorting as fallback
                    all_results.sort(key=lambda obj: str(getattr(obj, field, '')), reverse=is_descending)
                
        
        # Handle pagination
        page = kwargs.get('page', 1)
        all_records = kwargs.get('all', False)
        
        if not all_records:
            page_size = kwargs.get('page_size', 10)
            total_pages = -(-total_count // page_size)  # Ceiling division
            
            start = (page - 1) * page_size
            end = start + page_size
            
            page_info = PageInfo(
                has_next_page=end < total_count,
                has_previous_page=start > 0,
                total_count=total_count,
                page_size=page_size,
                current_page=page,
                total_pages=total_pages
            )
            
            # Apply pagination to the results
            results = all_results[start:end]
        else:
            page_info = PageInfo(
                has_next_page=False,
                has_previous_page=False,
                total_count=total_count,
                page_size=total_count,
                current_page=1,
                total_pages=1
            )
            results = all_results
        
        return ListType(
            page_info=page_info,
            results=results
        )

    # Resolver for single item
    def resolve_single(parent, info, id):
        try:
            # For polymorphic models, we need to get the most specific instance
            if is_polymorphic_model(model_class):
                base_instance = model_class.objects.get(pk=id)
                real_class = base_instance.get_real_instance_class()
                instance = real_class.objects.get(pk=id)
                return instance
            else:
                return model_class.objects.get(pk=id)
        except model_class.DoesNotExist:
            return None

    # Fields for queries
    fields = {
        f'{model_name}List': graphene.Field(
            ListType,
            filter=filter_class(required=False),
            page=graphene.Int(required=False, default_value=1),
            page_size=graphene.Int(required=False, default_value=10),
            all=graphene.Boolean(required=False, default_value=False),
            order_by=graphene.List(OrderByInput, required=False),
            search=graphene.String(description="Search term for text fields (case-insensitive, contains)"),
            description=f'List and filter {model_class.__name__} objects'
        ),
        model_name: graphene.Field(
            type_class,
            id=graphene.ID(required=True),
            description=f'Get a single {model_class.__name__} by ID'
        )
    }

    # Resolvers dictionary
    resolvers = {
        f'resolve_{model_name}List': resolve_list,
        f'resolve_{model_name}': resolve_single
    }

    processed_models.remove(model_class)
    return fields, resolvers

def generate_polymorphic_union(base_model: Type[PolymorphicModel]) -> graphene.Union:
    """
    Creates a GraphQL Union type for a polymorphic model and its subclasses
    """
    # Generate types for all subclasses
    subclass_types = [generate_graphql_type(subclass) for subclass in base_model.__subclasses__()]
    if not subclass_types:
        # If there are no subclasses, just use the base type
        return generate_graphql_type(base_model)
    
    # Create a Union type with all subclasses
    union_name = f"{base_model.__name__}Union"
    
    def resolve_type(instance, info):
        """Resolve the object type from instance to GraphQL type"""
        return _type_cache.get(instance.__class__.__name__)
        
    return type(
        union_name,
        (graphene.Union,),
        {
            'Meta': type('Meta', (), {'types': subclass_types}),
            'resolve_type': resolve_type
        }
    )

def generate_mutations(model_class: Type[models.Model]) -> Dict[str, Any]:
    """
    Generates Create, Update, and Delete mutations for the given model
    """
    model_name = model_class.__name__
    create_input = generate_input_type(model_class, f'Create{model_name}Input')
    update_input = generate_input_type(model_class, f'Update{model_name}Input')
    
    # Generate the model type with proper name
    model_type = generate_graphql_type(model_class)
    
    # Define a class for bulk create output with proper naming
    bulk_create_output_name = f'BulkCreate{model_name}Output'
    BulkCreateOutput = type(bulk_create_output_name, (graphene.ObjectType,), {
        'success': graphene.Boolean(description="Whether the bulk create operation was successful"),
        'count': graphene.Int(description="Number of records created"),
        'instances': graphene.List(model_type, description=f"List of created {model_class.__name__} instances")
    })
    
    class BulkCreateMutation(graphene.Mutation):
        class Arguments:
            inputs = graphene.List(create_input, required=True)
        
        Output = BulkCreateOutput
        
        def mutate(self, info, inputs):
            if is_polymorphic_model(model_class):
                if model_class._meta.abstract or model_class._meta.proxy:
                    raise GraphQLError(f"Cannot create abstract polymorphic model {model_class.__name__}")
            
            instances = []
            
            with transaction.atomic():
                for input_data in inputs:
                    instance = model_class()
                    for key, value in input_data.items():
                        field = model_class._meta.get_field(key)
                        if isinstance(field, models.ForeignKey):
                            related_model = field.related_model
                            if value is not None:
                                try:
                                    if issubclass(related_model, PolymorphicModel):
                                        base_instance = related_model.objects.get(pk=value)
                                        real_class = base_instance.get_real_instance_class()
                                        related_instance = real_class.objects.get(pk=value)
                                    else:
                                        related_instance = related_model.objects.get(pk=value)
                                    setattr(instance, key, related_instance)
                                except related_model.DoesNotExist:
                                    raise GraphQLError(f"{related_model.__name__} with id {value} does not exist")
                        else:
                            setattr(instance, key, value)
                    instance.save()
                    instances.append(instance)
            
            return {'success': True, 'instances': instances, 'count': len(instances)}
    
    # Define a class for bulk delete output with proper naming
    bulk_delete_output_name = f'BulkDelete{model_name}Output'
    BulkDeleteOutput = type(bulk_delete_output_name, (graphene.ObjectType,), {
        'success': graphene.Boolean(description="Whether the bulk delete operation was successful"),
        'count': graphene.Int(description="Number of records deleted"),
    })
    
    class BulkDeleteMutation(graphene.Mutation):
        class Arguments:
            ids = graphene.List(graphene.ID, required=True)
        
        Output = BulkDeleteOutput
        
        def mutate(self, info, ids):
            count = 0
            
            with transaction.atomic():
                for id in ids:
                    try:
                        if is_polymorphic_model(model_class):
                            base_instance = model_class.objects.get(pk=id)
                            real_class = base_instance.get_real_instance_class()
                            instance = real_class.objects.get(pk=id)
                        else:
                            instance = model_class.objects.get(pk=id)
                        instance.delete()
                        count += 1
                    except model_class.DoesNotExist:
                        # Skip if instance doesn't exist
                        pass
            
            return {'success': True, 'count': count}
    
    # Define a class for bulk update output with proper naming
    bulk_update_output_name = f'BulkUpdate{model_name}Output'
    BulkUpdateOutput = type(bulk_update_output_name, (graphene.ObjectType,), {
        'success': graphene.Boolean(description="Whether the bulk update operation was successful"),
        'count': graphene.Int(description="Number of records updated"),
        'instances': graphene.List(model_type, description=f"List of updated {model_class.__name__} instances")
    })
    
    # Define a unique input type for bulk update operations
    bulk_update_input_name = f'BulkUpdate{model_name}Input'
    BulkUpdateInput = type(bulk_update_input_name, (graphene.InputObjectType,), {
        'id': graphene.ID(required=True, description="ID of the record to update"),
        'input': update_input(required=True, description="Fields to update")
    })
    
    class BulkUpdateMutation(graphene.Mutation):
        class Arguments:
            inputs = graphene.List(BulkUpdateInput, required=True)
        
        Output = BulkUpdateOutput
        
        def mutate(self, info, inputs):
            instances = []
            count = 0
            
            with transaction.atomic():
                for item in inputs:
                    id = item.get('id')
                    input_data = item.get('input')
                    
                    try:
                        # For polymorphic models, ensure we get the most specific instance
                        if is_polymorphic_model(model_class):
                            base_instance = model_class.objects.get(pk=id)
                            real_class = base_instance.get_real_instance_class()
                            instance = real_class.objects.get(pk=id)
                        else:
                            instance = model_class.objects.get(pk=id)
                            
                        for key, value in input_data.items():
                            field = model_class._meta.get_field(key)
                            if isinstance(field, models.ForeignKey):
                                # Get the related model class
                                related_model = field.related_model
                                # Get the instance of the related model using the provided ID
                                if value is not None:
                                    try:
                                        # Handle polymorphic foreign keys
                                        if issubclass(related_model, PolymorphicModel):
                                            base_instance = related_model.objects.get(pk=value)
                                            real_class = base_instance.get_real_instance_class()
                                            related_instance = real_class.objects.get(pk=value)
                                        else:
                                            related_instance = related_model.objects.get(pk=value)
                                        setattr(instance, key, related_instance)
                                    except related_model.DoesNotExist:
                                        raise GraphQLError(f"{related_model.__name__} with id {value} does not exist")
                                else:
                                    setattr(instance, key, None)
                            else:
                                setattr(instance, key, value)
                        instance.save()
                        instances.append(instance)
                        count += 1
                    
                    except model_class.DoesNotExist:
                        # Skip if instance doesn't exist instead of failing
                        continue
            
            return {'success': True, 'instances': instances, 'count': count}
    
    class CreateMutation(graphene.Mutation):
        class Arguments:
            input = create_input(required=True)
            
        Output = model_type
        
        def mutate(self, info, input):
            # For polymorphic models, ensure we're creating the correct concrete class
            if is_polymorphic_model(model_class):
                # For polymorphic base models, we can't create them directly
                if model_class._meta.abstract or model_class._meta.proxy:
                    raise GraphQLError(f"Cannot create abstract polymorphic model {model_class.__name__}")
                
            instance = model_class()
            for key, value in input.items():
                field = model_class._meta.get_field(key)
                if isinstance(field, models.ForeignKey):
                    # Get the related model class
                    related_model = field.related_model
                    # Get the instance of the related model using the provided ID
                    if value is not None:
                        try:
                            # Handle polymorphic foreign keys
                            if issubclass(related_model, PolymorphicModel):
                                base_instance = related_model.objects.get(pk=value)
                                real_class = base_instance.get_real_instance_class()
                                related_instance = real_class.objects.get(pk=value)
                            else:
                                related_instance = related_model.objects.get(pk=value)
                            setattr(instance, key, related_instance)
                        except related_model.DoesNotExist:
                            raise GraphQLError(f"{related_model.__name__} with id {value} does not exist")
                else:
                    setattr(instance, key, value)
            instance.save()
            return instance
    
    class UpdateMutation(graphene.Mutation):
        class Arguments:
            id = graphene.ID(required=True)
            input = update_input(required=True)
            
        Output = model_type
        
        def mutate(self, info, id, input):
            try:
                # For polymorphic models, ensure we get the most specific instance
                if is_polymorphic_model(model_class):
                    base_instance = model_class.objects.get(pk=id)
                    real_class = base_instance.get_real_instance_class()
                    instance = real_class.objects.get(pk=id)
                else:
                    instance = model_class.objects.get(pk=id)
                    
                for key, value in input.items():
                    field = model_class._meta.get_field(key)
                    if isinstance(field, models.ForeignKey):
                        # Get the related model class
                        related_model = field.related_model
                        # Get the instance of the related model using the provided ID
                        if value is not None:
                            try:
                                # Handle polymorphic foreign keys
                                if issubclass(related_model, PolymorphicModel):
                                    base_instance = related_model.objects.get(pk=value)
                                    real_class = base_instance.get_real_instance_class()
                                    related_instance = real_class.objects.get(pk=value)
                                else:
                                    related_instance = related_model.objects.get(pk=value)
                                setattr(instance, key, related_instance)
                            except related_model.DoesNotExist:
                                raise GraphQLError(f"{related_model.__name__} with id {value} does not exist")
                        else:
                            setattr(instance, key, None)
                    else:
                        setattr(instance, key, value)
                instance.save()
                return instance
            except model_class.DoesNotExist:
                raise GraphQLError(f"{model_name} with id {id} does not exist")

    class DeleteMutation(graphene.Mutation):
        class Arguments:
            id = graphene.ID(required=True)
            hard = graphene.Boolean(default_value=False)
            
        success = graphene.Boolean()
        
        def mutate(self, info, id, hard=False):
            try:
                # For polymorphic models, ensure we get the most specific instance
                if is_polymorphic_model(model_class):
                    base_instance = model_class.objects.get(pk=id)
                    real_class = base_instance.get_real_instance_class()
                    instance = real_class.objects.get(pk=id)
                else:
                    instance = model_class.objects.get(pk=id)
                
                # Check if model supports soft delete
                if hasattr(instance, 'is_deleted') and not hard:
                    instance.delete(hard=False)
                else:
                    instance.delete()
                    
                return DeleteMutation(success=True)
            except model_class.DoesNotExist:
                raise GraphQLError(f"{model_name} with id {id} does not exist")
    
    # Add all mutations
    return {
        f'create_{model_name.lower()}': CreateMutation.Field(),
        f'update_{model_name.lower()}': UpdateMutation.Field(),
        f'delete_{model_name.lower()}': DeleteMutation.Field(),
        f'bulk_create_{model_name.lower()}': BulkCreateMutation.Field(),
        f'bulk_delete_{model_name.lower()}': BulkDeleteMutation.Field(),
        f'bulk_update_{model_name.lower()}': BulkUpdateMutation.Field()
    }

# Custom action registry for model-specific actions
# Format: {'ModelName': {'action_name': action_function}}
_custom_actions = {}

def register_custom_action(model_name: str, action_name: str, action_function, input_fields=None, output_fields=None):
    """
    Register a custom action for a specific model
    
    Args:
        model_name (str): Name of the model class (e.g., 'Facture')
        action_name (str): Name of the action (e.g., 'print', 'approve', 'cancel')
        action_function: Function that performs the action, should accept (root, info, id, **kwargs)
        input_fields (dict, optional): GraphQL input fields for the action
        output_fields (dict, optional): GraphQL output fields for the action result
    """
    if model_name not in _custom_actions:
        _custom_actions[model_name] = {}
    
    _custom_actions[model_name][action_name] = (action_function, input_fields or {}, output_fields or {})


def generate_custom_action_mutations(model_class: Type[models.Model]) -> Dict[str, Any]:
    """
    Generate GraphQL mutations for all custom actions registered for a model
    
    Returns a dictionary of {mutation_name: mutation_field}
    """
    import graphene
    mutations = {}
    model_name = model_class.__name__
    
    # Get custom actions for this model
    model_actions = _custom_actions.get(model_name, {})
    
    for action_name, action_data in model_actions.items():
        # Get the action function, input fields, and output fields from the tuple
        # The tuple format is (action_function, input_fields, output_fields)
        action_function, input_fields, output_fields = action_data
        
        # Generate camelCase mutation name: modelActionName
        camel_name = f"{model_name[0].lower()}{model_name[1:]}{action_name[0].upper()}{action_name[1:]}"
        
        
        # Create a specific resolver for this action
        def create_resolver(func):
            def resolver(parent, info, **kwargs):
                id_value = kwargs.pop('id')  # Extract and remove id from kwargs
                # Call the action function
                result = func(parent, info, id_value, **kwargs)
                return result
            return resolver
        
        # Create a simple mutation class definition
        class ActionMutation(graphene.Mutation):
            # Define output fields
            class Meta:
                name = f"{model_name}{action_name.capitalize()}"
                description = f"Perform {action_name} action on a {model_name}"
            
            # Define Arguments inner class
            class Arguments:
                id = graphene.ID(required=True, description=f"ID of the {model_name}")
            
            # Add the mutate method
            mutate = create_resolver(action_function)
        
        # Add the output fields to the mutation class
        for field_name, field_type in output_fields.items():
            setattr(ActionMutation, field_name, field_type)
        
        # Add the input fields to the Arguments class
        for field_name, field_type in input_fields.items():
            setattr(ActionMutation.Arguments, field_name, field_type)
        
        # Create an actual mutation class with a unique name
        MutationClass = type(
            f"{model_name}{action_name.capitalize()}Mutation",
            (ActionMutation,),
            {}
        )
        
        # Register the mutation
        mutations[camel_name] = MutationClass.Field(
            description=f"Perform {action_name} action on a {model_name}"
        )
        
    
    return mutations

def discover_app_custom_actions():
    """
    Discover and import custom_actions modules from all Django apps
    
    Looks for a file named custom_actions.py in each app directory
    """
    from django.apps import apps
    from importlib import import_module
    from django.conf import settings
    
    for app_config in apps.get_app_configs():
        app_name = app_config.name
        # Only process our own apps, not Django system apps
        if app_name.startswith('django.') or app_name.startswith('rest_framework'):
            continue
                
        # Some apps are referenced by their full path, others by short name
        # Try both formats for maximum compatibility
        module_paths_to_try = [
            f"{app_name}.custom_actions",  # Full path (e.g., "billing.custom_actions")
            f"custom_actions"  # Relative path within the app
        ]
        
        for module_path in module_paths_to_try:
            try:
                # Try to import the custom_actions module
                module = import_module(module_path, package=app_name)
                
                # After import, print what's in the registry for this app's models
                app_models = {model.__name__: model for model in app_config.get_models()}
                for model_name in app_models:
                    actions = _custom_actions.get(model_name, {})

                break  # Found it, no need to try other paths
            except ImportError as e:
                pass