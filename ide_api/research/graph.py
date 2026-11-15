"""Bounded typed provenance with derivation DAG and accessible dependency lists."""
from .contracts import LIMITS
from ide_api import rail_sweeps as rail
TYPES={'question','hypothesis','campaign','proposal','prediction','model','controller','execution','case','finding','report'}
EDGES={'investigates','uses_model','uses_controller','derived_from','measured_by','references','included_in'}

def validate_graph(g):
 rail.exact(g,['version','nodes','edges'])
 if g['version']!=1 or len(g['nodes'])>LIMITS['graph_nodes'] or len(g['edges'])>LIMITS['graph_edges']:raise ValueError('Graph bound/version invalid')
 nodes={n['id']:n for n in g['nodes']}
 if len(nodes)!=len(g['nodes']):raise ValueError('Duplicate graph node')
 for n in nodes.values():
  rail.exact(n,['id','type','label','reference'])
  if n['type'] not in TYPES:raise ValueError('Invalid graph node type')
 adjacency={k:[] for k in nodes};seen=set()
 for e in g['edges']:
  rail.exact(e,['from','to','type']);key=(e['from'],e['to'],e['type'])
  if key in seen or e['from'] not in nodes or e['to'] not in nodes or e['type'] not in EDGES:raise ValueError('Invalid/dangling graph edge')
  seen.add(key)
  a,b=nodes[e['from']]['type'],nodes[e['to']]['type']
  if e['type']=='derived_from':
   if a=='finding' and b!='case' or a=='case' and b!='execution' or a=='proposal' and b not in ('case','proposal'):raise ValueError('Invalid measured/predicted derivation')
   adjacency[e['from']].append(e['to'])
 colors={}
 def visit(k):
  if colors.get(k)==1:raise ValueError('Derivation cycle')
  if colors.get(k)==2:return
  colors[k]=1
  for n in adjacency[k]:visit(n)
  colors[k]=2
 for k in sorted(nodes):visit(k)
 return g

def build(project,campaign,summaries,findings):
 nodes={};edges=[]
 def node(key,kind,label,reference=None):nodes[key]={'id':key,'type':kind,'label':label,'reference':reference}
 def edge(a,b,kind):
  e={'from':a,'to':b,'type':kind}
  if e not in edges:edges.append(e)
 q=project['id'];cid=campaign['id'];node(q,'question',project['question']);node(cid,'campaign',campaign['config']['objective']);edge(cid,q,'investigates')
 for h in project['hypotheses']:
  node(h['id'],'hypothesis',h['content']['statement'])
  if h['id'] in campaign['config']['hypothesis_ids']:edge(cid,h['id'],'investigates')
 model=campaign['config']['experiment_id'];controller=campaign['config']['controller_id'];node(model,'model',model);node(controller,'controller',controller);edge(cid,model,'uses_model');edge(cid,controller,'uses_controller')
 for b in campaign['batches']:
  node(b['id'],'proposal',b['status']+' '+b['strategy']);edge(b['id'],cid,'references')
  for p in b['cases']:
   key=rail.digest({'batch':b['id'],'parameters':p});node(key,'prediction','Analytical proposed point',p);edge(key,b['id'],'references')
 for s in summaries:
  execution=rail.digest({'evidence':s['kind'],'id':s['id']});node(execution,'execution','Saved '+s['status'],{'summary_sha256':s['summary_sha256']});edge(execution,cid,'references')
  for r in s['records']:
   if not r['verified']:continue
   node(r['id'],'case',r['verdict']+' '+r['provenance_kind'],{'result_sha256':r['result_sha256'],'trajectory_sha256':r['trajectory_sha256'],'source_sha256':r['source_sha256'],'source_current':r['source_current']});edge(r['id'],execution,'derived_from')
 for f in findings:
  if f['status']!='VERIFIED':continue
  node(f['id'],'finding',str(f['fact']['value'])+' '+f['fact']['unit'],f['fact']);edge(f['id'],f['fact']['case_id'],'derived_from')
 report=rail.digest({'project':q,'campaign':cid,'kind':'report'});node(report,'report','Deterministic report')
 for f in findings:
  if f['status']=='VERIFIED':edge(f['id'],report,'included_in')
 return validate_graph({'version':1,'nodes':sorted(nodes.values(),key=lambda n:n['id']),'edges':sorted(edges,key=lambda e:(e['from'],e['to'],e['type']))})
