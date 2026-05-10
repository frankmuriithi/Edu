# validators.py
from django.core.exceptions import ValidationError

def min_4_chars(value):
    if not value or len(value.strip()) < 4:
        raise ValidationError("Must be at least 4 characters long.")