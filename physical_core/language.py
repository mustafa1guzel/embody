"""Bounded quantities/control expressions translated to data, never Python execution."""
import ast,hashlib,math
from ide_api.rail_sweeps import digest
DIMS={'1':(0,0,0),'m':(1,0,0),'s':(0,0,1),'kg':(0,1,0),'m/s':(1,0,-1),'N':(1,1,-2),'N*m':(2,1,-2),'N/m':(0,1,-2),'N*s/m':(0,1,-1),'rad':(0,0,0)}
def merge(a,b):
 if a is not None and b is not None and a!=b:raise ValueError('Incompatible expression units')
 return a if a is not None else b

def expression(text,units):
 if not isinstance(text,str) or not 1<=len(text.encode())<=2048:raise ValueError('Bounded expression required')
 try:tree=ast.parse(text,mode='eval').body
 except (ValueError,SyntaxError,RecursionError):raise ValueError('Invalid quantity expression') from None
 if len(list(ast.walk(tree)))>96:raise ValueError('Expression node limit96')
 def visit(n,depth=0):
  if depth>10:raise ValueError('Expression depth limit10')
  if isinstance(n,ast.Constant) and type(n.value) in (float,int) and abs(n.value)<=100 and math.isfinite(n.value):return {'op':'constant','value':float(n.value)},None
  if isinstance(n,ast.Name) and n.id in units:return {'op':'input','name':n.id},DIMS[units[n.id]]
  if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.USub):
   v,u=visit(n.operand,depth+1)
   if u=='bool':raise ValueError('Boolean is not a quantity')
   return {'op':'neg','a':v},u
  if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='abs' and len(n.args)==1 and not n.keywords:
   v,u=visit(n.args[0],depth+1)
   if u=='bool':raise ValueError('abs requires a quantity')
   return {'op':'abs','a':v},u
  if isinstance(n,ast.BinOp) and type(n.op) in (ast.Add,ast.Sub,ast.Mult,ast.Div):
   a,au=visit(n.left,depth+1);b,bu=visit(n.right,depth+1)
   if au=='bool' or bu=='bool':raise ValueError('Boolean arithmetic rejected')
   if isinstance(n.op,(ast.Add,ast.Sub)):u=merge(au,bu)
   else:
    x,y=au or DIMS['1'],bu or DIMS['1'];u=tuple(v+(w if isinstance(n.op,ast.Mult) else -w) for v,w in zip(x,y))
    if au is None and bu is None:u=None
    if isinstance(n.op,ast.Div) and b=={'op':'constant','value':0.}:raise ValueError('Zero divisor')
   return {'op':{ast.Add:'add',ast.Sub:'sub',ast.Mult:'mul',ast.Div:'div'}[type(n.op)],'a':a,'b':b},u
  if isinstance(n,ast.Compare) and len(n.ops)==1 and type(n.ops[0]) in (ast.Lt,ast.LtE,ast.Gt,ast.GtE):
   a,au=visit(n.left,depth+1);b,bu=visit(n.comparators[0],depth+1)
   if au=='bool' or bu=='bool':raise ValueError('Invalid comparison')
   merge(au,bu);return {'op':{ast.Lt:'lt',ast.LtE:'le',ast.Gt:'gt',ast.GtE:'ge'}[type(n.ops[0])],'a':a,'b':b},'bool'
  if isinstance(n,ast.BoolOp) and type(n.op) in (ast.And,ast.Or):
   v=[visit(x,depth+1) for x in n.values]
   if any(u!='bool' for _,u in v):raise ValueError('and/or require conditions')
   return {'op':'and' if isinstance(n.op,ast.And) else 'or','args':[a for a,_ in v]},'bool'
  if isinstance(n,ast.IfExp):
   c,cu=visit(n.test,depth+1);a,au=visit(n.body,depth+1);b,bu=visit(n.orelse,depth+1)
   if cu!='bool' or au=='bool' or bu=='bool':raise ValueError('Invalid conditional quantity')
   return {'op':'if','condition':c,'a':a,'b':b},merge(au,bu)
  raise ValueError('Unsupported syntax; no Python imports/attributes/calls/loops/indexing/execution')
 return visit(tree)

def evaluate(n,state):
 op=n['op']
 if op=='constant':return n['value']
 if op=='input':return state[n['name']]
 if op=='if':return evaluate(n['a'] if evaluate(n['condition'],state) else n['b'],state)
 if op in ('and','or'):
  v=[evaluate(x,state) for x in n['args']];return all(v) if op=='and' else any(v)
 a=evaluate(n['a'],state)
 if op in ('neg','abs'):return -a if op=='neg' else abs(a)
 b=evaluate(n['b'],state)
 if op in ('lt','le','gt','ge'):return {'lt':a<b,'le':a<=b,'gt':a>b,'ge':a>=b}[op]
 if op=='div' and abs(b)<1e-15:raise ValueError('Runtime zero divisor')
 v={'add':lambda:a+b,'sub':lambda:a-b,'mul':lambda:a*b,'div':lambda:a/b}[op]()
 if not math.isfinite(v) or abs(v)>1e12:raise ValueError('Finite arithmetic envelope exceeded')
 return v

def compile_source(source,contract):
 if not isinstance(source,str) or not 1<=len(source.encode())<=8192:raise ValueError('Controller source maximum8KiB')
 lines=[x.strip() for x in source.splitlines() if x.strip()]
 if not lines or lines[0]!='physical_controller 1':raise ValueError('Expected physical_controller 1 header')
 actions={}
 for line in lines[1:]:
  if '=' not in line:raise ValueError('Expected action = expression')
  name,formula=line.split('=',1);name=name.strip()
  if name not in contract['actuators'] or name in actions:raise ValueError('Unknown/duplicate actuator identity')
  tree,unit=expression(formula.strip(),contract['observations'])
  if unit=='bool' or unit is not None and unit!=DIMS[contract['actuators'][name]['unit']]:raise ValueError('Actuator expression unit mismatch')
  actions[name]=tree
 if set(actions)!=set(contract['actuators']):raise ValueError('Every actuator requires exactly one expression')
 artifact={'language':'PHYSICAL_CONTROLLER_V1','contract_sha256':digest(contract),'actions':actions}
 return {'source':source,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'artifact':artifact,'artifact_sha256':digest(artifact)}
