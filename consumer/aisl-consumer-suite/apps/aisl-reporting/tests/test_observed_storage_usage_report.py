from types import SimpleNamespace
from aisl_reporting.contracts import ReportRequest
from aisl_reporting.profiles.observed_storage_usage_report.v1.builder import build_dataset

class Client:
    def get_json(self, path, *, params=None):
        if path.endswith('/accesses'):
            return {'items':[{'repo_id':'repo','access_kind':'read','storage_access_id':'a1'}], 'summary':{'access_count':1,'read_count':1,'write_count':0,'gap_count':1}}
        return {'items':[{'repo_id':'repo','gap_code':'unresolved'}]}

def test_observed_storage_dataset_uses_api_projection():
    source=SimpleNamespace(system_id='demo', revision_id='rev-1', client=Client(), revision={'execution':{'scope_kind':'repository'}}, selected_artifact={'artifact_id':'storage'}, capabilities=('common.observed-storage-usage',))
    request=ReportRequest(report_type='observed-storage-usage-report', report_version='v1', api_url='http://api', system_id='demo', knowledge_source=source)
    dataset=build_dataset(request)
    assert dataset['coverage']['read_count']==1
    assert dataset['sections']['reads'][0]['storage_access_id']=='a1'
    assert dataset['sections']['gaps'][0]['gap_code']=='unresolved'
