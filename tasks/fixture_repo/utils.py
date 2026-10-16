"""Small helpers used across the shop app."""
import os
import json


def add_tag(item, tags=[]):
    """Add a tag for this item to the list and return the list."""
    tags.append(item)
    return tags


def to_json(data):
    """Turn data into a JSON string."""
    return json.dumps(data)
