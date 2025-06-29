from itertools import chain
import math
from num2words import num2words


from django.db.models import  Sum

def ListToQuerySet(queryseys_list,model): 
    result = model.objects.none() 
    for item in queryseys_list: 
        result =  result | item
   
    return result 


def calculate_remise(ht,remise):
    if remise > 100: 
        return (ht - remise),remise
    else : 
        remise = ht * remise / 100
        return (ht - remise),remise
    

def calculate_timber(sum): 
    if sum <= 20 : 
        timber = 0  
    else: 
        timber = sum / 100
        if timber <= 4: 
            timber = 5
        if timber >= 2500: 
            timber = 2500
    sum += timber
    return sum,timber 

def calculate_tva(ht): 
    if ht > 0: 
        return (ht * 19 / 100)
    else: 
        return 0 

def serialize(records): 
    filterd_records = []    
    for record in records:
        filterd_records.append(record) 
    
    return filterd_records 

def get_sum_hors_taxes(records): 
    total = 0 
    for item in records: 
        total += item.HT 

    return total 

def get_sum_prix(records): 
    total = 0 
    for item in records: 
        total += item.prix

    return total 


def decimalToText(sum): 
    decimal_part , integer_part = math.modf(sum)
    decimal_part = round(decimal_part,2)
    return num2words(int(integer_part), lang='fr') + " Dinar Algerien et " +  num2words(int(decimal_part * 100), lang='fr') + " Centime(s)"





def ratio(last_value, new_value): 
    if last_value == 0 : 
        return 100
    else: 
        return round((new_value * 100) / last_value - 100,0) 


def calculate_timber(sum):
    print(f"------------------------- sum ----------------------------: {sum}") 
    if sum <= 20 : 
        timber = 0  
    else: 
        timber = sum / 100
        if timber <= 4: 
            timber = 5
        if timber >= 2500: 
            timber = 2500
    sum += timber
    return sum,timber 

def calculate_tva(ht): 
    if ht > 0: 
        return (ht * 19 / 100)
    else: 
        return 0 