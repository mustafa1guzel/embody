"""Rail DSL v1: parse to bounded data, never eval/exec/compile user Python."""
import ast,hashlib,math
from ide_api.rail_sweeps import digest
VERSION='EMBODY_RAIL_DSL_V1'
UNITS={'clearance_m':'m','stopping_distance_m':'m','speed_mps':'m/s','time_s':'s','mass_kg':'kg','force_limit_n':'N'}
INITIAL='rail_controller 1\nwhen clearance_m <= 0.25\nthen brake\nelse coast\n'
REPAIR='rail_controller 1\nwhen clearance_m <= stopping_distance_m + 0.10 or speed_mps < 0.03\nthen brake\nelse coast\n'

def compile_source(source):
 if not isinstance(source,str) or not 1<=len(source.encode())<=4096:raise ValueError('Controller source must be1–4096 UTF-8 bytes')
 lines=[v.strip() for v in source.splitlines() if v.strip()]
 if len(lines)!=4 or lines[0]!='rail_controller 1' or not lines[1].startswith('when '):raise ValueError('Expected four DSL lines: rail_controller 1 / when condition / then action / else action')
 actions=[]
 for prefix,line in zip(('then ','else '),lines[2:]):
  if not line.startswith(prefix) or line[len(prefix):] not in ('brake','coast'):raise ValueError('Only brake and coast actions are supported')
  actions.append(line[len(prefix):])
 try:tree=ast.parse(lines[1][5:],mode='eval').body
 except (SyntaxError,RecursionError,ValueError):raise ValueError('Invalid bounded DSL condition') from None
 if len(list(ast.walk(tree)))>64:raise ValueError('Condition exceeds64 AST nodes')
 def expression(n,depth=0):
  if depth>8:raise ValueError('Condition nesting exceeds8')
  if isinstance(n,ast.Constant) and type(n.value) in (float,int) and abs(n.value)<=100 and math.isfinite(n.value):return {'op':'literal','value':float(n.value)},None
  if isinstance(n,ast.Name) and n.id in UNITS:return {'op':'input','name':n.id},UNITS[n.id]
  if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.USub) and isinstance(n.operand,ast.Constant) and type(n.operand.value) in (int,float):return expression(ast.Constant(-n.operand.value),depth+1)
  if isinstance(n,ast.BinOp) and type(n.op) in (ast.Add,ast.Sub,ast.Mult):
   a,au=expression(n.left,depth+1);b,bu=expression(n.right,depth+1)
   if au=='bool' or bu=='bool':raise ValueError('Booleans are not numeric source expressions')
   if isinstance(n.op,ast.Mult):
    if au and bu:raise ValueError('Multiplication supports a scalar literal expression and one physical quantity only')
   elif au and bu and au!=bu:raise ValueError('Incompatible units in condition')
   return {'op':{ast.Add:'add',ast.Sub:'sub',ast.Mult:'mul'}[type(n.op)],'a':a,'b':b},au or bu
  if isinstance(n,ast.Compare) and len(n.ops)==1 and type(n.ops[0]) in (ast.Lt,ast.LtE,ast.Gt,ast.GtE):
   a,au=expression(n.left,depth+1);b,bu=expression(n.comparators[0],depth+1)
   if au=='bool' or bu=='bool' or au and bu and au!=bu:raise ValueError('Comparison requires compatible physical units')
   return {'op':{ast.Lt:'lt',ast.LtE:'le',ast.Gt:'gt',ast.GtE:'ge'}[type(n.ops[0])],'a':a,'b':b},'bool'
  if isinstance(n,ast.BoolOp) and type(n.op) in (ast.And,ast.Or):
   args=[expression(v,depth+1) for v in n.values]
   if any(u!='bool' for _,u in args):raise ValueError('and/or require comparison conditions')
   return {'op':'and' if isinstance(n.op,ast.And) else 'or','args':[v for v,_ in args]},'bool'
  raise ValueError('Unsupported DSL construct; no imports, calls, attributes, subscripts, loops, strings or Python execution')
 condition,unit=expression(tree)
 if unit!='bool':raise ValueError('when requires a comparison condition')
 artifact={'language':VERSION,'condition':condition,'then':actions[0],'else':actions[1]}
 return {'source':source,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'artifact':artifact,'artifact_sha256':digest(artifact),'language':VERSION,'validation':'VALIDATED_NOT_PHYSICALLY_VERIFIED'}

def evaluate(node,state):
 op=node['op']
 if op=='literal':return node['value']
 if op=='input':return state[node['name']]
 if op in ('and','or'):
  values=[evaluate(v,state) for v in node['args']];return all(values) if op=='and' else any(values)
 a=evaluate(node['a'],state);b=evaluate(node['b'],state)
 if op in ('lt','le','gt','ge'):return {'lt':a<b,'le':a<=b,'gt':a>b,'ge':a>=b}[op]
 value={'add':lambda:a+b,'sub':lambda:a-b,'mul':lambda:a*b}[op]()
 if not math.isfinite(value) or abs(value)>1e12:raise ValueError('DSL arithmetic outside finite resource envelope')
 return value

def inputs(sample,p):
 return {'clearance_m':sample['wall_clearance'],'stopping_distance_m':p['mass_kg']*sample['velocity']**2/(2*p['force_n']),'speed_mps':abs(sample['velocity']),'time_s':sample['time'],'mass_kg':p['mass_kg'],'force_limit_n':p['force_n']}

def command(program,sample,p):
 action=program['then'] if evaluate(program['condition'],inputs(sample,p)) else program['else']
 return min(p['force_n'],max(-p['force_n'],-p['mass_kg']*sample['velocity']/.005)) if action=='brake' else 0.
