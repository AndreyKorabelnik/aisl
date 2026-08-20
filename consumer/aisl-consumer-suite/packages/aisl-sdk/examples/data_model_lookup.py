import argparse
import json
from aisl_sdk import AislClient

p = argparse.ArgumentParser()
p.add_argument("--api-url", required=True)
p.add_argument("--system-id", required=True)
p.add_argument("--revision-id")
p.add_argument("--search", required=True)
a = p.parse_args()

with AislClient(a.api_url) as client:
    revision = client.revision(a.system_id, a.revision_id) if a.revision_id else client.active_revision(a.system_id)
    items = revision.search_declared_data_objects(search=a.search, include_fields=True)
    print(json.dumps(items, ensure_ascii=False, indent=2))
