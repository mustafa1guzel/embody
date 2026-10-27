"""GET-only shared workspace read model. No model, simulation, apply or migration.

Historical evidence is read through pinned seals, never re-authorized against
current sources. Native trajectories retain their own original input identities.
"""
from pathlib import Path
from hashlib import sha256
import json
from core.simulation import ROOT
from engineering.project import identity
from engineering.store import Store
from physics.contracts import digest
from workspace.data import bounded_read,decode_json

SEAL='artifacts/phase18e_7/20261026/integrity_index.json'
SEAL_SHA256='6b1620f3a90ef859ff1e86ab8264e4f5906f7d455a88bd73d27f19be30f06a70'
ROVER_HEAD='artifacts/phase18e_6/20261026/live_project'

class SealedEvidence:
    def __init__(self,root=ROOT):
        self.root=Path(root);raw=bounded_read(self.root,SEAL)
        if sha256(raw).hexdigest()!=SEAL_SHA256:raise ValueError('Historical workspace seal mismatch')
        self.index=decode_json(raw)
    def read(self,name):
        if name not in self.index:raise ValueError('Evidence is not in the pinned historical inventory')
        raw=bounded_read(self.root,name)
        if sha256(raw).hexdigest()!=self.index[name]:raise ValueError('Historical evidence bytes differ: '+name)
        return decode_json(raw)
    def project_head(self,folder):
        pointer=self.read(folder+'/head.json');p=self.read(folder+'/projects/'+pointer['sha256']+'.json')
        if identity(p)!=pointer['sha256']:raise ValueError('Historical project hash mismatch')
        if 'commit_sha256' in pointer:
            commit=self.read(folder+'/commits/'+pointer['commit_sha256']+'.json')
            if digest(commit)!=pointer['commit_sha256'] or commit['result_sha256']!=pointer['sha256']:raise ValueError('Historical head commit mismatch')
        return p

def _run(key,title,q,n,feedback,provenance):
    r=n['result'];p=q['proposed_project']
    if identity(p)!=q['resulting_project_sha256'] or n['proposal_id']!=q['proposal_id'] or n['proposed_project_sha256']!=identity(p) or r['world']!=p['world']:
        raise ValueError('Saved workspace proposal/native identity mismatch')
    if digest(r['samples'])!=r['trajectory_sha256'] or sha256(r['model_xml'].encode()).hexdigest()!=r['contract']['model_sha256']:
        raise ValueError('Saved native trajectory/model mismatch')
    if not r['samples'] or r['independent_verification']['status']!='PASS':raise ValueError('Saved replay is missing or failed')
    return {'id':key,'title':title,'kind':'SAVED_SIMULATION','proposal':q,'native':n,
        'verification':feedback,'provenance':provenance,'source_status':'HISTORICAL_SOURCE_BOUND; read-only, not current execution or application authority',
        'application_status':'PROPOSED_NOT_APPLIED','input_project_sha256':q['resulting_project_sha256']}

def rover_snapshot(root=ROOT):
    sealed=SealedEvidence(root);head=sealed.project_head(ROVER_HEAD)
    if head['revision']!=0 or head.get('shape_specs') or len(head['world']['objects'])!=1:raise ValueError('Historical rover EMPTY r0 head changed')
    base='artifacts/phase18e_4/20261025/live_execution/'
    repair='artifacts/phase18e_6/20261026/live_execution/'
    original=sealed.read(base+'protocol_result.json');q=original['proposal'];n=sealed.read(base+'native_verification.json')
    direction=sealed.read(base+'forward_verification.json');receipt=sealed.read(base+'api_cost_ledger.json')
    original_fb={'status':'FAIL','signed_forward_displacement_m':direction['signed_forward_displacement_m'],'required_signed_displacement_m':direction['contract']['minimum_signed_displacement_m'],
        'checks':{**n['observations']['checks'],'signed_forward_displacement':direction['checks']['signed_forward_displacement']},
        'failure_reasons':['Signed forward displacement is below +0.005 m; measured travel is backwards.'],
        'initial_forward_axis_world':direction['initial_forward_axis_world']}
    initial=_run('phase18e5','Original GPT rover · Phase 18E.5',q,n,original_fb,
        {'origin':'GENUINE_PROVIDER_RESPONSE','phase':'18E.5','authorship':'Original complete construction and revised plan were model-authored. Historical failed experiment; not applied.',
         'api_cost_usd':receipt['measured_cost_usd'],'request_count':len(receipt['requests']),'provider_response_ids':[x['response_id'] for x in receipt['requests']],
         'evidence_path':base,'new_requests_on_open':0})
    protocol=sealed.read(repair+'protocol_result.json');q2=protocol['proposal'];n2=sealed.read(repair+'native.json');fb=sealed.read(repair+'physical_feedback.json');receipt2=sealed.read(repair+'api_cost_ledger.json');review=sealed.read(repair+'review.json')
    repaired_fb={'status':'PASS' if fb['status']=='PHYSICAL_PASS' else 'FAIL','signed_forward_displacement_m':fb['measured_signed_forward_displacement_m'],
        'required_signed_displacement_m':fb['required_direction']['minimum_signed_displacement_m'],'checks':fb['checks'],'failure_reasons':fb['failed_checks'],
        'initial_forward_axis_world':fb['forward_axis_world'],'wheels':fb['wheels']}
    repaired=_run('phase18e7','GPT physical repair · Phase 18E.7',q2,n2,repaired_fb,
        {'origin':'GENUINE_PROVIDER_RESPONSE','phase':'18E.7','authorship':review['provenance']['authorship'],
         'baseline_origin':review['provenance']['baseline_origin'],'operations':protocol['attempts'][1]['arguments']['operations'],
         'explanation':protocol['attempts'][1]['arguments']['explanation'],'api_cost_usd':receipt2['measured_cost_usd'],'request_count':len(receipt2['requests']),
         'provider_response_ids':[x['response_id'] for x in receipt2['requests']],'evidence_path':repair,'new_requests_on_open':0})
    for run in (initial,repaired):
        if run['proposal']['base_project_sha256']!=identity(head) or run['proposal']['base_revision']!=head['revision']:raise ValueError('Historical proposal targets a different head')
        samples=run['native']['result']['samples'];body=run['proposal']['structural']['root_body']
        pos=lambda s:next(p['position_m'] for p in s['poses'] if p['id']==body)
        signed=sum((a-b)*axis for a,b,axis in zip(pos(samples[-1]),pos(samples[0]),run['verification']['initial_forward_axis_world']))
        if abs(signed-run['verification']['signed_forward_displacement_m'])>1e-12:raise ValueError('Saved signed displacement differs')
    if original_fb['status']!='FAIL' or original_fb['checks']['signed_forward_displacement'] is not False:raise ValueError('Historical FAIL must remain a failure')
    return {'key':'rover','title':'Rover repair review · saved evidence','project':head,'project_sha256':identity(head),
        'historical':True,'editable':False,'runs':[initial,repaired],'proposals':[],
        'shape_parts':[],'catalog':{},'electrical':None,'action_contracts':{},
        'context':'Original failure and later repair are separate genuine experiments. Authoritative head EMPTY r0; both populated devices are unapplied proposals.',
        'circuit_binding':'UNBOUND_REFERENCE_DATA; this circuit does not power or control the rover MuJoCo actuators.',
        'firmware_status':'REFERENCE_ONLY; no rover firmware execution; expired VM qualification blocks untrusted source execution.'}

def current_snapshot(ide):
    service=ide.engineering;b=service.bootstrap();p=b['project'];runs=[];unavailable=[]
    for ref in p.get('evidence_refs',[]):
        if ref.get('kind')!='world':continue
        try:
            value=service.load_evidence(ref['sha256']);r=value['result']
            # Device-bound samples have a different contract; do not invent transforms.
            if 'poses' not in r['samples'][0]:continue
            runs.append({'id':ref['sha256'],'title':'Saved World run · '+ref['sha256'][:10],'kind':'SAVED_SIMULATION','proposal':None,
                'native':{'result':r},'input_project_sha256':ref['base_project_sha256'],
                'verification':{'status':'REPLAY_'+r['independent_verification']['status'],'checks':{'fresh_replay':r['independent_verification']['status']=='PASS'},'failure_reasons':[],'summary':'Saved native replay only; no device-specific physical acceptance verdict.'},
                'provenance':{'origin':'RECORDED_PROJECT_RUN','authorship':'Saved trusted numeric World simulation; no new model call.','api_cost_usd':'0','evidence_path':ref['sha256']},'application_status':'SAVED_INPUT; may differ from current head'})
        except (ValueError,OSError,KeyError,IndexError) as exc:unavailable.append('Saved record '+ref['sha256'][:12]+' is missing or invalid; no replacement result.')
    proposals=[]
    # A bounded read of the existing review store, never reconstruction/apply.
    if (service.root/'assembly_live_review.json').exists():
        try:
            pointer=decode_json(bounded_read(service.root,'assembly_live_review.json'));record=Store(service.root/'assembly_reviews').get(pointer['sha256'])
            if record.get('proposal_id'):
                q={**Store(service.root/'assembly_proposals').get(record['proposal_id']),'proposal_id':record['proposal_id']}
                if q['base_project_sha256']!=identity(p) or q['base_revision']!=p['revision']:raise ValueError('Saved proposal targets a different head')
                proposals.append({'id':q['proposal_id'],'proposal':q,'provenance':{'origin':record['origin'],'authorship':record.get('provenance',{}).get('authorship',q['action_authorship'])},'source_status':'SAVED_PROPOSAL; existing source/precondition checks required before any separate decision'})
        except (ValueError,OSError,KeyError):unavailable.append('The saved assembly review is unavailable or invalid; no replacement proposal.')
    return {'key':'current','title':p['id'],'project':p,'project_sha256':identity(p),'historical':False,'editable':True,
        'shape_parts':b.get('shapebase',{}).get('parts',[]),'catalog':b['catalog'],'electrical':b['electrical'],
        'action_contracts':b['action_contracts'],'runs':runs,'proposals':proposals,'unavailable':unavailable,
        'context':'Current backend-selected engineering project. Proposals and saved simulation inputs remain separate from its authoritative head.',
        'circuit_binding':'BOUND_GENERATED_DEVICE' if p.get('creation',{}).get('state')=='BUILT' else 'UNBOUND_REFERENCE_DATA; circuit and mechanics have no verified functional binding.',
        'firmware_status':'Controller source identity only; untrusted source execution unavailable without valid separately approved isolation.'}

def bootstrap(ide,key='current'):
    if key not in ('current','rover'):raise ValueError('Unknown workspace project; arbitrary paths are not accepted')
    snapshot=current_snapshot(ide) if key=='current' else rover_snapshot()
    return {'snapshot':snapshot,'projects':[{'key':'current','title':'Current engineering project'},{'key':'rover','title':'Rover repair review · saved'}],
        'policy':{'new_api_calls':0,'native_runs_on_open':0,'application':False,'historical_review_only':True,
            'security':'Untrusted firmware/controller execution requires valid containment and separate explicit approval. Saved trusted numeric states remain inspectable.'}}
