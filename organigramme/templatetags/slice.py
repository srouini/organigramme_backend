from django import template

register = template.Library() 

@register.filter(name='sliceText') 
def slice_text(text):
    new_text = (text[:45] + '...')  if len(text) > 45 else text
    return new_text


