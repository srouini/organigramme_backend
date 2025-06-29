import graphene
from .dynamic_api import (
    generate_graphql_type, 
    generate_query_fields, 
    generate_mutations,
    generate_custom_action_mutations,
    discover_app_custom_actions
)
from django.apps import apps

# Discover and load custom actions from all apps
# This MUST happen before schema initialization
discover_app_custom_actions()

def register_apps_models_query(app_name, namespace):
    app = apps.get_app_config(app_name)
    all_fields = {}
    all_resolvers = {}
   
    for model in app.get_models():
        model_fields, model_resolvers = generate_query_fields(model)
        all_fields.update(model_fields)
        all_resolvers.update(model_resolvers)
    
    # Update the provided namespace with all fields and resolvers
    namespace.update(all_fields)
    namespace.update(all_resolvers)
    return all_fields, all_resolvers

def register_apps_models_mutations(app_name, namespace):
    app = apps.get_app_config(app_name)
    all_mutations = {}
    
    for model in app.get_models():
        # Add standard CRUD mutations
        model_mutations = generate_mutations(model)
        all_mutations.update(model_mutations)
        
        # Add any custom action mutations
        custom_mutations = generate_custom_action_mutations(model)
        all_mutations.update(custom_mutations)
    
    # Update the provided namespace with all mutations
    namespace.update(all_mutations)
    return all_mutations

class Query(graphene.ObjectType):
    # Generate fields for each model
    organigramme_fields, data_resolvers = register_apps_models_query("organigramme", locals())
    # data_fields, data_resolvers = register_apps_models_query("data", locals())
    # reference_fields, reference_resolvers = register_apps_models_query("reference", locals())
    # bareme_fields, bareme_resolvers = register_apps_models_query("bareme", locals())
    # billing_fields, billing_resolvers = register_apps_models_query("billing", locals())
    # operation_fields, operation_resolvers = register_apps_models_query("operation", locals())

class Mutation(graphene.ObjectType):
    # Generate mutations for each model
    organigramme_mutations = register_apps_models_mutations("organigramme", locals())
    # data_mutations = register_apps_models_mutations("data", locals())
    
    # Individual model mutations for models from other apps
    # reference_mutations = register_apps_models_mutations("reference", locals())
    # bareme_mutations = register_apps_models_mutations("bareme", locals())
    # billing_mutations = register_apps_models_mutations("billing", locals())
    # operation_mutations = register_apps_models_mutations("operation", locals())
    # auditlog_mutations = register_apps_models_mutations("auditlog", locals())


# Create the schema
schema = graphene.Schema(query=Query, mutation=Mutation)

# Add dynamic polymorphic relation handling
from .dynamic_api import _type_cache
from django.apps import apps
import graphene
import re

def get_base_model_from_concrete(concrete_model):
    """Get the polymorphic base model from a concrete model"""
    for base in concrete_model.__mro__:
        if hasattr(base, '_meta') and getattr(base._meta, 'abstract', False) == False:
            if base.__name__.endswith('Base') and base.__name__ != concrete_model.__name__:
                return base
    return None

def find_related_models(base_model_name):
    """Find all concrete models that have foreign keys to concrete instances of a base model"""
    related_models = {}
    
    # Get base model class
    base_model = None
    for app_config in apps.get_app_configs():
        for model in app_config.get_models():
            if model.__name__ == base_model_name:
                base_model = model
                break
        if base_model:
            break
    
    if not base_model:
        return related_models
    
    # Find all concrete subclasses
    concrete_subclasses = base_model.__subclasses__()
    
    # Find all models that have foreign keys to these concrete subclasses
    for app_config in apps.get_app_configs():
        for model in app_config.get_models():
            # Find all foreign keys in this model
            for field in model._meta.fields:
                if hasattr(field, 'related_model'):
                    # Check if this foreign key points to one of our concrete subclasses
                    if field.related_model in concrete_subclasses:
                        # Get base model of this related model
                        related_base = get_base_model_from_concrete(model)
                        if related_base:
                            # Group by base model name
                            base_name = related_base.__name__
                            if base_name not in related_models:
                                related_models[base_name] = []
                            
                            # Store info about this relationship
                            related_models[base_name].append({
                                'concrete_model': field.related_model.__name__,
                                'related_model': model.__name__,
                                'field_name': field.name
                            })
    
    return related_models

def add_polymorphic_relations_to_type(type_name, base_model_name):
    """Add polymorphic relations to a GraphQL type"""
    if type_name not in _type_cache:
        return
    
    graphql_type = _type_cache[type_name]
    
    # Find all models related to concrete instances of this base model
    related_models = find_related_models(base_model_name)
    
    # For each base related model, add a field and resolver
    for related_base, relations in related_models.items():
        # Create field name from base model name
        # Example: PaiementBase -> paiements
        field_name = re.sub(r'Base$', '', related_base).lower() + 's'
        
        # Make sure we don't override existing fields
        if hasattr(graphql_type, field_name):
            continue
        
        # Create resolver that handles all concrete types
        def make_resolver(rel_models):
            def resolver(self, info):
                # Get concrete instance
                instance = self.get_real_instance() if hasattr(self, 'get_real_instance') else self
                concrete_class = instance.__class__.__name__
                
                # Find the matching relation for this concrete type
                results = []
                for rel in rel_models:
                    if rel['concrete_model'] == concrete_class:
                        # Import the model
                        model = None
                        for app_config in apps.get_app_configs():
                            for m in app_config.get_models():
                                if m.__name__ == rel['related_model']:
                                    model = m
                                    break
                            if model:
                                break
                        
                        if model:
                            # Get related objects
                            filter_kwargs = {rel['field_name']: instance}
                            results = list(model.objects.filter(**filter_kwargs))
                            break
                
                return results
            
            return resolver
        
        # Create resolver for this relation
        resolver = make_resolver(relations)
        resolver_name = f'resolve_{field_name}'
        setattr(graphql_type, resolver_name, resolver)
        
        # Get or create type for the related base model
        related_type_name = f'{related_base}Type'
        if related_type_name not in _type_cache:
            # Find the related base model
            related_base_model = None
            for app_config in apps.get_app_configs():
                for model in app_config.get_models():
                    if model.__name__ == related_base:
                        related_base_model = model
                        break
                if related_base_model:
                    break
            
            if related_base_model:
                from .dynamic_api import generate_graphql_type
                related_type = generate_graphql_type(related_base_model)
            else:
                continue
        else:
            related_type = _type_cache[related_type_name]
        
        # Add field to the GraphQL type
        field = graphene.List(related_type)
        setattr(graphql_type, field_name, field)
        
        # Update Meta to include the new field
        old_meta = getattr(graphql_type, 'Meta')
        
        # Determine the model
        model = getattr(old_meta, 'model', None)
        if not model:
            continue
        
        # Get existing fields
        if hasattr(old_meta, 'fields') and old_meta.fields != '__all__':
            fields = list(old_meta.fields)
            if field_name not in fields:
                fields.append(field_name)
        else:
            fields = [f.name for f in model._meta.fields]
            fields.append(field_name)
        
        # Create new Meta
        new_meta = type('Meta', (), {
            'model': model,
            'fields': fields,
            'interfaces': getattr(old_meta, 'interfaces', ()),
            'use_connection': False
        })
        
        # Replace Meta
        setattr(graphql_type, 'Meta', new_meta)

# Process all polymorphic base models
for app_config in apps.get_app_configs():
    for model in app_config.get_models():
        # Only process polymorphic base models
        if model.__name__.endswith('Base') and not getattr(model._meta, 'abstract', False):
            type_name = f'{model.__name__}Type'
            # Add dynamic polymorphic relations
            add_polymorphic_relations_to_type(type_name, model.__name__)