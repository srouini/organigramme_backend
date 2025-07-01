from .models import *
from .serializers import *
from src.utils import generate_filter_set
from django.db.models import Exists, OuterRef
import django_filters
from .models import Organigram,OrganigramEdge, Grade, Position, Task, Mission, Competence

# Register custom filters for the Conteneur model

# Generate filter sets for all models
OrganigramFilter = generate_filter_set(Organigram)
OrganigramEdgeFilter = generate_filter_set(OrganigramEdge)
GradeFilter = generate_filter_set(Grade)
PositionFilter = generate_filter_set(Position)
TaskFilter = generate_filter_set(Task)
MissionFilter = generate_filter_set(Mission)
CompetenceFilter = generate_filter_set(Competence)
