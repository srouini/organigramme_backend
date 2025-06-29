from io import BytesIO
import django_filters
from django.db import models
from django.http import HttpResponse
from django.template.loader import get_template
from num2words import num2words
import math
from xhtml2pdf import pisa  
from rest_framework.pagination import PageNumberPagination
from django.apps import apps 
import sys 
from django.views.decorators.csrf import csrf_exempt
import json
from django.db.models import Q, Exists, OuterRef
from django.db import transaction
from collections import defaultdict
from html2docx import html2docx

def getValue(current_object,item): 

    for attr_name in item["schema"]:
        try:
            current_object = getattr(current_object, attr_name)
        except: 
            current_object = "/"

    return current_object 

def excelGenerator(filtered_queryset, columns): 
    rows = [] 
    for item in filtered_queryset: 
        row = {}
        for col in columns:

            row[col["header"]] = getValue(item, col)
        
        rows.append(row)
    print(rows)
    return rows 

from django.http import JsonResponse

 
def decimalToText(sum): 
    decimal_part , integer_part = math.modf(sum)
    decimal_part = round(decimal_part,2)
    return num2words(int(integer_part), lang='fr') + " Dinar Algerien et " +  num2words(int(decimal_part * 100), lang='fr') + " Centime(s)"

class CustomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 10000


def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html = template.render(context_dict)
    result = BytesIO()

    # Ensure HTML content is UTF-8 encoded
    html_bytes = html.encode("UTF-8")

    # Generate PDF using xhtml2pdf
    pdf = pisa.pisaDocument(BytesIO(html_bytes), result, encoding='UTF-8', pdf_language='ar')

    if not pdf.err:
        # Return PDF response
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return None
 
 
def render_to_pdf_rest(template_src, context_dict={}):
    template = get_template(template_src)
    html = template.render(context_dict)
    result = BytesIO()

    # Ensure HTML content is UTF-8 encoded
    html_bytes = html.encode("UTF-8")

    # Generate PDF using xhtml2pdf
    pdf = pisa.pisaDocument(BytesIO(html_bytes), result, encoding='UTF-8', pdf_language='ar')

    if not pdf.err:
        return result.getvalue()  # Return PDF content as bytes
    return None

from io import BytesIO
from django.template.loader import get_template
from django.http import HttpResponse
# from html2docx import html2docx

# def render_to_word_rest(template_src, context_dict={}):
#     template = get_template(template_src)
#     html_content = template.render(context_dict)  # Render HTML with context

#     # Convert HTML to DOCX bytes
#     docx_bytes = html2docx(html_content)

#     return docx_bytes  # Return DOCX content as bytes

# def generate_word_report(request):
#     context = {"data": "Some Data"}  # Replace with actual context
#     docx_content = render_to_word_rest("your_template.html", context)

#     if docx_content:
#         response = HttpResponse(
#             docx_content, 
#             content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
#         )
#         response["Content-Disposition"] = 'attachment; filename="report.docx"'
#         return response

#     return HttpResponse("Error generating DOCX", status=500)
    
def generate_filter_set(selected_model):

    class DynamicFilterSetMeta(django_filters.filterset.FilterSetMetaclass):
        def __new__(cls, name, bases, attrs, **kwargs):
            new_class = super().__new__(cls, name, bases, attrs, **kwargs)

            # Add methods to handle the "in" lookup for related model ids dynamically
            for field in new_class.base_filters.values():
                if isinstance(field, django_filters.filters.BaseInFilter):
                    related_model = field.field.related_model
                    method_name = f'filter_{related_model.__name__.lower()}_ids'

                    def filter_related_model_ids(queryset, name, value, related_model=related_model):
                        return queryset.filter(**{f'{name}__id__in': value})


                    # Attach the "in" lookup handler to the DynamicFilterSet
                    setattr(new_class, method_name, filter_related_model_ids)

            return new_class
    
    class DynamicFilterSet(django_filters.FilterSet,metaclass=DynamicFilterSetMeta):
        class Meta:
            model = selected_model
            fields = []


    def add_filters(selected_model, prefix='', processed_models=None):
        
        if processed_models is None:
            processed_models = set()

        if selected_model in processed_models:
            return

        processed_models.add(selected_model)

        for field in selected_model._meta.fields:
            filter_name = f'{prefix}{field.name}'
            label_base = field.verbose_name.capitalize() if field.verbose_name else field.name.replace('_', ' ').capitalize()

            if isinstance(field, models.ForeignKey):
                # Recursive call for related fields
                add_filters(field.related_model, f'{filter_name}__',processed_models)
                # Add an "in" lookup for related model ids
                DynamicFilterSet.base_filters[f'{filter_name}__in'] = django_filters.BaseInFilter(
                    field_name=f'{filter_name}__id',
                    lookup_expr='in',
                    label=f"{label_base} (in list)"
                )
            else:
                if isinstance(field, models.CharField):
                    DynamicFilterSet.base_filters[filter_name + '__icontains'] = django_filters.CharFilter(
                        field_name=filter_name, lookup_expr='icontains',
                        label=f"{label_base} (contains, case-insensitive)"
                    )
                    DynamicFilterSet.base_filters[filter_name + '__exact'] = django_filters.CharFilter(
                        field_name=filter_name, lookup_expr='exact',
                        label=f"{label_base} (exact, case-sensitive)"
                    )

                elif isinstance(field, models.FloatField) or isinstance(field, models.DecimalField) or isinstance(field, models.IntegerField):
                    DynamicFilterSet.base_filters[filter_name] = django_filters.NumberFilter(
                        field_name=filter_name, lookup_expr='exact',
                        label=label_base
                    )
                    DynamicFilterSet.base_filters[f'{filter_name}__gt'] = django_filters.NumberFilter(
                        field_name=filter_name, lookup_expr='gt',
                        label=f"{label_base} (greater than)"
                    )
                    DynamicFilterSet.base_filters[f'{filter_name}__lt'] = django_filters.NumberFilter(
                        field_name=filter_name, lookup_expr='lt',
                        label=f"{label_base} (less than)"
                    )
                    DynamicFilterSet.base_filters[f'{filter_name}__gte'] = django_filters.NumberFilter(
                        field_name=filter_name, lookup_expr='gte',
                        label=f"{label_base} (greater than or equal)"
                    )
                    DynamicFilterSet.base_filters[f'{filter_name}__lte'] = django_filters.NumberFilter(
                        field_name=filter_name, lookup_expr='lte',
                        label=f"{label_base} (less than or equal)"
                    )
                elif isinstance(field, models.DateTimeField):
                    DynamicFilterSet.base_filters[f'{filter_name}__date'] = django_filters.DateFilter(
                        field_name=filter_name, lookup_expr='date',
                        label=f"{label_base} (date is)"
                    )
                    DynamicFilterSet.base_filters[f'{filter_name}__date__gt'] = django_filters.DateFilter(
                        field_name=filter_name, lookup_expr='date__gt',
                        label=f"{label_base} (date after)"
                    )
                    DynamicFilterSet.base_filters[f'{filter_name}__date__lt'] = django_filters.DateFilter(
                        field_name=filter_name, lookup_expr='date__lt',
                        label=f"{label_base} (date before)"
                    )
                    DynamicFilterSet.base_filters[f'{filter_name}__date__gte'] = django_filters.DateFilter(
                        field_name=filter_name, lookup_expr='date__gte',
                        label=f"{label_base} (date on or after)"
                    )
                    DynamicFilterSet.base_filters[f'{filter_name}__date__lte'] = django_filters.DateFilter(
                        field_name=filter_name, lookup_expr='date__lte',
                        label=f"{label_base} (date on or before)"
                    )
                elif isinstance(field, models.DateField):
                    DynamicFilterSet.base_filters[filter_name] = django_filters.DateFilter(
                        field_name=filter_name, lookup_expr='exact',
                        label=label_base
                    )
                    DynamicFilterSet.base_filters[f'{filter_name}__gt'] = django_filters.DateFilter(
                        field_name=filter_name, lookup_expr='gt',
                        label=f"{label_base} (after)"
                    )
                    DynamicFilterSet.base_filters[f'{filter_name}__lt'] = django_filters.DateFilter(
                        field_name=filter_name, lookup_expr='lt',
                        label=f"{label_base} (before)"
                    )
                    DynamicFilterSet.base_filters[f'{filter_name}__gte'] = django_filters.DateFilter(
                        field_name=filter_name, lookup_expr='gte',
                        label=f"{label_base} (on or after)"
                    )
                    DynamicFilterSet.base_filters[f'{filter_name}__lte'] = django_filters.DateFilter(
                        field_name=filter_name, lookup_expr='lte',
                        label=f"{label_base} (on or before)"
                    )

                elif isinstance(field, models.BooleanField):
                    DynamicFilterSet.base_filters[filter_name] = django_filters.BooleanFilter(
                        field_name=filter_name,
                        label=label_base
                    )
                else: # Default for other field types, e.g. TextField, EmailField
                    DynamicFilterSet.base_filters[filter_name + '__icontains'] = django_filters.CharFilter(
                        field_name=filter_name, lookup_expr='icontains',
                        label=f"{label_base} (contains, case-insensitive)"
                    )
                    DynamicFilterSet.base_filters[filter_name + '__exact'] = django_filters.CharFilter(
                        field_name=filter_name, lookup_expr='exact',
                        label=f"{label_base} (exact, case-sensitive)"
                    )
  
                if not isinstance(field, models.BooleanField):
                    DynamicFilterSet.base_filters[f'{filter_name}__isnull'] = django_filters.BooleanFilter(
                        field_name=filter_name, lookup_expr='isnull',
                        label=f"{label_base} (is null)"
                    )
                    
        # Check for app-specific custom filters
        try:
            # Determine which app this model belongs to
            app_label = selected_model._meta.app_label
            model_name = selected_model._meta.model_name
            
            # Dynamically import the app's filters module
            try:
                # First attempt with direct app name
                filters_module = __import__(f"{app_label}.filters", fromlist=['*'])
            except ImportError:
                # Try with backend.app_name path
                try:
                    filters_module = __import__(f"backend.{app_label}.filters", fromlist=['*'])
                except ImportError:
                    # No filters module found for this app
                    filters_module = None
            
            # If we found a filters module, look for model-specific custom filters
            if filters_module:
                # Look for a function named register_MODEL_custom_filters
                custom_filters_func = getattr(filters_module, f"register_{model_name}_custom_filters", None)
                
                if custom_filters_func and callable(custom_filters_func):
                    # Call the function, passing the DynamicFilterSet class to allow it to register filters
                    custom_filters_func(DynamicFilterSet)
        except (ImportError, AttributeError) as e:
            # Unable to import app-specific filters, log if needed
            pass
    add_filters(selected_model)

    # Expmale of usage : http://localhost:8000/order/api/note/?category__or=VIANDE,BOISSON,SALADE
    #In this exmple we are trying to request the categories where category is equale to VIANDE OR BOISSON OR SAlADE 
    def filter_title_or(queryset, name, value):
        values = value.split(',')  # Split input into a list of values
        filters = Q()  # Initialize an empty Q object

        for val in values:
            filters |= Q(**{f'status__icontains': val.strip()})

        return queryset.filter(filters)

    # Add the custom filter to DynamicFilterSet
    DynamicFilterSet.base_filters['status__or'] = django_filters.CharFilter(
        method=filter_title_or,
        label='Status (OR, contains, comma-separated)'
    )


    return DynamicFilterSet


def get_filters(model):
    filter_set  = generate_filter_set(model)
    filter_set_instance = filter_set()
    filters = filter_set_instance.base_filters
    return filters


from django.shortcuts import render
from django.http import HttpResponse
from django.template.loader import render_to_string

def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html = template.render(context_dict)
    result = BytesIO()

    # Ensure HTML content is UTF-8 encoded
    html_bytes = html.encode("UTF-8")

    # Generate PDF using xhtml2pdf
    pdf = pisa.pisaDocument(BytesIO(html_bytes), result, encoding='UTF-8', pdf_language='ar')

    if not pdf.err:
        # Return PDF response
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return None

from django.templatetags.static import static



# from reference.models import Client 
# from app.models import Article, Tc, SousArticle

# def client_exist(_raison_sociale): 
#     exist = Client.objects.filter(raison_sociale=_raison_sociale).exists()


# def extract_lines(file_name):
#     result = []
#     with file_name  as opend_file:
#         for line in opend_file :
#             stripped_line = line.strip().decode('latin1')
#             stripped_line = stripped_line[:-1]
#             splited_lien = stripped_line.rsplit("|")
#             splited_lien = [item for item in splited_lien if item!= '']
#             if len(splited_lien) > 0 :     
#                 splited_lien = removeImpurities(splited_lien)          
#                 result.append(splited_lien) 
#     return result


# def extract_tcs(gros, conta, ligne): 
#     """
#     Process articles and TCs, skipping any existing records.
#     If an article, TC, or sous-article already exists, it will be skipped.
    
#     Args:
#         gros: The gros object
#         conta: Container data
#         ligne: Line items data
#     """
#     articles_groupage = []
#     clients_cache = {}

#     # Process in transaction to ensure data consistency
#     with transaction.atomic():
#         for line in ligne:
#             numero_article = str(line[2])
            
#             # Handle groupage articles
#             if len(line[3]) <= 4 and line[3] != 0:
#                 articles_groupage.append(numero_article)
#                 continue

#             # Prepare client data
#             if len(line[3]) > 4:
#                 raison_sociale = line[9]
#                 adress = line[10]
#                 bl = line[3]
#                 designation = line[4]
#                 poids = line[11]
#                 groupage = False
#             else:
#                 raison_sociale = line[10]
#                 adress = line[11]
#                 bl = line[4]
#                 designation = line[5]
#                 poids = line[12]
#                 groupage = True

#             # Get or create client (cached)
#             if raison_sociale not in clients_cache:
#                 client, _ = Client.objects.get_or_create(
#                     raison_sociale=raison_sociale,
#                     defaults={'adress': adress}
#                 )
#                 clients_cache[raison_sociale] = client
            
#             # Try to get existing article or create new one
#             try:
#                 article, created = Article.objects.get_or_create(
#                     numero=numero_article,
#                     gros=gros,
#                     defaults={
#                         'bl': bl,
#                         'groupage': groupage,
#                         'client': clients_cache[raison_sociale],
#                         'designation': designation
#                     }
#                 )
#             except Exception:
#                 # If any error occurs during article creation, skip this article
#                 continue

#             # Process TCs only for non-groupage articles
#             if not groupage:
#                 for conta_line in conta:
#                     if str(conta_line[2]) == numero_article:
#                         tc = conta_line[3]
#                         tar = conta_line[4]
                        
#                         # Try to create TC if it doesn't exist
#                         try:
                            
#                             created_tc = Tc.objects.get_or_create(
#                                 article=article,
#                                 tc=tc,
#                                 defaults={
#                                     'tar': tar,
#                                     'poids': poids
#                                 }
#                             )
                          
#                         except Exception:
#                             # If any error occurs during TC creation, skip this TC
#                             continue

#         # Update groupage articles in bulk
#         if articles_groupage:
#             Article.objects.filter(
#                 numero__in=articles_groupage,
#                 gros=gros
#             ).update(groupage=True)

#     # Process sous-articles if needed
#     if articles_groupage:
#         try:
#             add_sous_article(gros, ligne, list(set(articles_groupage)))
#         except Exception:
#             # If error occurs during sous-article processing, continue
#             pass

# def extract_tcs_update_sous_articles(gros, conta , ligne): 
#     articles_groupage = []
#     for line in ligne:
#         numero_article = line[2]
#         add  = True  
#         if len(line[3]) > 4 : 
#             BL = line[3]
#             designation_marchandise = line[4]
#             raison_sociale_client = line[9]
#             adress_client = line[10]
#             poids = line[11]
#             groupage = False

#         else: 
#             if line[3] != 0: 
#                 add = False
#                 articles_groupage.append(line[2])
#             else: 
#                 numero_sous_article = line[3]
#                 BL = line[4]
#                 designation_marchandise = line[5]
#                 raison_sociale_client = line[10]
#                 adress_client = line[11]
#                 poids = line[12] 
#                 groupage = True  

#         try: 
#             if not (client_exist(raison_sociale_client)): 
#                     client= Client(raison_sociale = raison_sociale_client , adress = adress_client )
#                     client.save()
#         except:
#             pass  
        
#         if add : 
#             if(Article.objects.filter(numero = numero_article, gros = gros).exists()): 
#                 article = Article.objects.get(numero=numero_article, gros=gros)
#             else: 
#                 article = Article.objects.create(numero = numero_article, gros = gros ,bl=BL,groupage = groupage ,client = Client.objects.get(raison_sociale = raison_sociale_client),designation = designation_marchandise)
            
#             if article.groupage : 
#                 pass
#             else : 

#                 for conta_line in conta: 
#                     if article.numero == conta_line[2]:

#                         tc = conta_line[3]
#                         tar = conta_line[4]

#                         if(not Tc.objects.filter(article=article, tc = tc).exists() ):
#                             Tc.objects.filter(article = article,tc=tc)

#     add_sous_article(gros,ligne,list(dict.fromkeys(articles_groupage)))

# def add_sous_article(gros,ligne, groupage_list):   

#     for article in groupage_list: 
#         # one_article = gros.article_set.filter(numero=article)
#         # groupage_tcs = one_article.tc_set.all() 
#         #print(groupage_tcs)
#         tcs = Tc.objects.filter(article__numero = article, article__gros = gros).update(groupage=True)
#         gros.article_set.filter(numero=article).update(groupage=True)
#         current_article = gros.article_set.get(numero=article)
        
#         # Get all TCs for this article
#         article_tcs = {tc.tc: tc for tc in current_article.tc_set.all()}
        
#         for line in ligne:
#             if (line[2] == article) & (len(line[3]) < 4):
#                 description = line[5]
#                 # Find the TC number in the description
#                 matching_tc = None
#                 for tc_number in article_tcs.keys():
#                     if tc_number in description:
#                         matching_tc = article_tcs[tc_number]
#                         break
                
#                 if matching_tc:
#                     try: 
#                         # Get existing client or create new one
#                         client, _ = Client.objects.get_or_create(
#                             raison_sociale=line[10],
#                             defaults={'adress': line[11]}
#                         )
                        
#                         # Check if sous-article already exists
#                         sous_article, created = SousArticle.objects.get_or_create(
#                             numero=line[3],
#                             tc=matching_tc,
#                             defaults={
#                                 'bl': line[4],
#                                 'designation': description,
#                                 'client': client,
#                                 'poids': line[12].replace(',','.')
#                             }
#                         )
#                         if created:
#                             print(f"Created sous-article {line[3]} for TC {matching_tc.tc}")
#                         else:
#                             print(f"Sous-article {line[3]} already exists for TC {matching_tc.tc}")
#                     except Exception as e:
#                         print(f"Error processing sous-article {line[3]}: {str(e)}")
#                 else:
#                     print(f"No matching TC found in description for sous-article {line[3]}: {description}")

# def get_articles_tcs(gros): 
#     articles = gros.article_set.all()
#     i = 0
#     while i < len(articles):
#         articles[i].tcs = Tc.objects.filter(article_id=articles[i].id)
#         i = i + 1


# def remove(string):
#     return "".join(string.split())


# def removeImpurities(array): 
#     array.pop()
#     new_array = []
#     for item in array: 
#         if remove(item) != "0" and remove(item) != "00" and remove(item) != "000" and remove(item) != "0000"  : 
#             new_array.append(item)
#     return new_array