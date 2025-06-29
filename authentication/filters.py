from .models import *
from .serializers import *
from src.utils import generate_filter_set

ProfileFilter = generate_filter_set(Profile)
