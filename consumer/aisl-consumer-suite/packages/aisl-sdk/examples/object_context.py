import argparse
import json
from aisl_sdk import AislClient

p = argparse.ArgumentParser()
p.add_argument("--api-url", required=True)
p.add_argument("--system-id", required=True)
p.add_argument("--revision-id")
p.add_argument("--object-id", required=True)
a = p.parse_args()

with AislClient(a.api_url) as client:
    revision = client.revision(a.system_id, a.revision_id) if a.revision_id else client.active_revision(a.system_id)
    print(json.dumps(revision.get_data_model_object_context(a.object_id), ensure_ascii=False, indent=2))
