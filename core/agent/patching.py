"""Source policy validation and isolated proposal storage. Never executes proposals."""
from __future__ import annotations
import ast
import difflib
import hashlib
import math
import os
from pathlib import Path, PurePosixPath
import stat
from uuid import uuid4

from core.simulation import write_json

TARGET = 'robot/controller.py'
READ_ALLOWLIST = frozenset({TARGET, 'robot/rail_carriage.xml', 'core/simulation.py',
                           'core/diagnostics.py', 'core/bodybase.py', 'core/worldbase.py',
                           'configs/bodybase.json', 'configs/worldbase.json', 'configs/scenarios.json'})
MAX_SOURCE_BYTES = 100_000

# These tables drive both validation and discovery. They describe source shape,
# not an execution sandbox or a controller implementation.
FORBIDDEN_CALLS = frozenset({'exec', 'eval', 'open', 'compile', '__import__', 'getattr',
                           'setattr', 'delattr', 'globals', 'locals', 'vars', 'input', 'breakpoint'})
ALLOWED_METHODS = {'math': frozenset({'isfinite', 'isclose', 'sqrt', 'copysign', 'hypot'}),
                   'model': frozenset({'actuator', 'joint', 'body', 'geom'}),
                   'data': frozenset({'joint'})}
RULES = {
    'python_syntax': ('Invalid Python source', 'Submit a complete syntactically valid Python module.'),
    'imports_unchanged': ('Imports must remain unchanged; no filesystem/network/runtime imports are allowed',
                          'Keep the original top-level import ASTs in their original order.'),
    'single_entrypoint': ('Preserve the one existing faulty_braking_controller entry point',
                          'Exactly one top-level FunctionDef with the original name; additional top-level helpers are forbidden. Keep helper logic within the permitted controller structure.'),
    'entrypoint_signature': ('Controller signature, annotations and lack of decorators must be preserved',
                             'Preserve arguments, defaults, annotations and return annotation exactly; no decorators.'),
    'module_structure': ('Module scope may contain only original imports, numeric constants, a docstring and the controller',
                         'Besides original imports and the one controller, only standalone string expressions and plain assignments to uppercase names of finite int/float literals (not bool) are supported. No annotated module assignments, classes or executable module statements.'),
    'nested_effects': ('Nested imports and global/nonlocal/deletion effects are unsupported',
                       'No imports, global, nonlocal or delete statements below module scope.'),
    'public_attributes': ('Private/introspection attributes are forbidden',
                          'No attribute whose name begins with an underscore.'),
    'runtime_call': ('Forbidden runtime operation', 'Do not call any forbidden bare-name runtime operation.'),
    'method_call': ('Unsupported method call; candidates may read model/state and write data.ctrl only',
                    'Attribute calls require a simple named receiver and a listed allowed method. Other bare-name calls are not generally prohibited by this rule.'),
    'state_writes': ('Only actuator command data.ctrl[...] may be written; model/state changes are forbidden',
                     'Assignment, annotated assignment, augmented assignment and named-expression attribute/subscript stores are restricted to data.ctrl[...]. Local name stores remain supported.'),
    'original_hash': ('Original source hash mismatch; re-read the current file', 'Use the current exact original SHA-256.'),
    'source_size': ('Proposed source exceeds the size limit', 'Respect the UTF-8 source byte limit.'),
    'source_changed': ('Proposal contains no source changes', 'Submit an actual modification.'),
    'patch_target': ('Only the authorized controller target may be proposed',
                     'Use the exact allowlisted relative target; physics, tests, safety and configuration files are protected. Absolute paths, traversal and symlinks are rejected.'),
}


def violation(rule_id, node=None, *, detail=None):
    message, explanation = RULES[rule_id]
    return {'rule_id': rule_id, 'message': message + (f': {detail}' if detail else ''),
            'explanation': explanation,
            'location': ({'line': node.lineno, 'column': node.col_offset + 1,
                          'end_line': getattr(node, 'end_lineno', None)}
                         if node is not None and hasattr(node, 'lineno') else None)}


def source_policy(original: str, target=TARGET):
    """Machine-readable contract from the same rule tables and original AST."""
    tree = ast.parse(original)
    entry = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    return {'policy_version': 1, 'authorized_target': target,
            'other_files_modifiable': False, 'original_overwritten': False,
            'expected_source_format': 'Complete UTF-8 Python module; not a diff, markdown fence or partial function',
            'maximum_source_bytes': MAX_SOURCE_BYTES,
            'original_sha256': hashlib.sha256(original.encode()).hexdigest(),
            'entrypoint': {'name': entry.name, 'arguments': ast.unparse(entry.args),
                           'return_annotation': ast.unparse(entry.returns), 'decorators': []},
            'top_level_function_count': 1, 'additional_top_level_helpers_allowed': False,
            'required_imports_in_order': [ast.unparse(n) for n in tree.body
                                          if isinstance(n, (ast.Import, ast.ImportFrom))],
            'forbidden_bare_name_calls': sorted(FORBIDDEN_CALLS),
            'allowed_attribute_calls': {name: sorted(methods) for name, methods in ALLOWED_METHODS.items()},
            'rules': {key: {'message': value[0], 'explanation': value[1]} for key, value in RULES.items()},
            'execution_boundary': 'Validation does not authorize execution. Only a qualified VM backend and independent host-authoritative '
                                  + ('A/B/C' if target==TARGET else 'declared robot-family scenario')
                                  + ' verification can establish candidate safety.'}


def read_project_file(root: Path, path: str, allowlist=READ_ALLOWLIST):
    if (not isinstance(path, str) or not path or '\\' in path or '\x00' in path
            or PurePosixPath(path).is_absolute() or any(p in ('', '.', '..') for p in path.split('/'))
            or path not in allowlist):
        raise ValueError('Path must be an allowlisted relative project file; traversal is forbidden')
    # Walk using directory FDs and O_NOFOLLOW, so a symlink swap cannot escape.
    fd = os.open(Path(root).resolve(), os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = path.split('/')
        for index, part in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if index < len(parts) - 1:
                flags |= os.O_DIRECTORY
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE_BYTES:
            raise ValueError('Source must be a regular file within the size limit')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError('Source exceeds the size limit')
    except OSError as exc:
        raise ValueError('File unavailable or a symlink was rejected') from exc
    finally:
        os.close(fd)
    return {'path': path, 'content': raw.decode('utf-8'), 'sha256': hashlib.sha256(raw).hexdigest()}


def source_violations(original: str, proposed: str):
    """Checks supported source shape and obvious scope violations, NOT a sandbox."""
    errors = []
    try:
        baseline, tree = ast.parse(original), ast.parse(proposed)
        compile(tree, '<candidate-validation-only>', 'exec')  # compile != execute
    except (SyntaxError, ValueError, RecursionError) as exc:
        item = violation('python_syntax', detail=str(exc))
        if isinstance(exc, SyntaxError) and exc.lineno is not None:
            item['location'] = {'line': exc.lineno, 'column': exc.offset, 'end_line': exc.end_lineno}
        return [item]
    imports = [ast.dump(n) for n in baseline.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    actual_imports = [ast.dump(n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    if actual_imports != imports:
        errors.append(violation('imports_unchanged'))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    original_function = next(n for n in baseline.body if isinstance(n, ast.FunctionDef))
    if len(functions) != 1 or functions[0].name != original_function.name:
        errors.append(violation('single_entrypoint', next((n for n in functions if n.name != original_function.name), functions[0] if functions else None)))
    elif (ast.dump(functions[0].args) != ast.dump(original_function.args)
          or (ast.dump(functions[0].returns) if functions[0].returns is not None else None)
             != ast.dump(original_function.returns)
          or functions[0].decorator_list):
        errors.append(violation('entrypoint_signature', functions[0]))
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError()
                continue
            except (ValueError, TypeError, OverflowError):
                pass
        errors.append(violation('module_structure', node))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Global, ast.Nonlocal, ast.Delete, ast.Import, ast.ImportFrom)) and node not in tree.body:
            errors.append(violation('nested_effects', node))
        if isinstance(node, ast.Attribute) and node.attr.startswith('_'):
            errors.append(violation('public_attributes', node))
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                errors.append(violation('runtime_call', node, detail=node.func.id))
            if isinstance(node.func, ast.Attribute):
                method = node.func.attr
                allowed = (isinstance(node.func.value, ast.Name) and
                           method in ALLOWED_METHODS.get(node.func.value.id, ()))
                if not allowed:
                    errors.append(violation('method_call', node))
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for item in ast.walk(target):
                    if isinstance(item, (ast.Attribute, ast.Subscript)) and isinstance(item.ctx, ast.Store):
                        valid = (isinstance(item, ast.Subscript) and isinstance(item.value, ast.Attribute)
                                 and isinstance(item.value.value, ast.Name) and item.value.value.id == 'data'
                                 and item.value.attr == 'ctrl')
                        if not valid:
                            errors.append(violation('state_writes', item))
    return errors


def source_errors(original: str, proposed: str):
    # Compatibility API: identical acceptance and legacy messages.
    return sorted({item['message'] for item in source_violations(original, proposed)})


class CandidateStore:
    def __init__(self, root: Path, output: Path, *, target=TARGET):
        if target not in (TARGET, 'robot/arm_controller.py'):
            raise ValueError('Unknown family patch target')
        self.root, self.output = Path(root), Path(output)
        self.target = target
        self.records = {}

    def propose(self, *, target_path, expected_original_sha256, proposed_source, explanation):
        original = read_project_file(self.root, target_path, {self.target})
        violations = []
        if expected_original_sha256 != original['sha256']:
            violations.append(violation('original_hash'))
        if len(proposed_source.encode()) > MAX_SOURCE_BYTES:
            violations.append(violation('source_size'))
        elif proposed_source == original['content']:
            violations.append(violation('source_changed'))
        else:
            violations.extend(source_violations(original['content'], proposed_source))
        errors = list(dict.fromkeys(v['message'] for v in violations))
        proposed_hash = hashlib.sha256(proposed_source.encode()).hexdigest()
        diff = ''.join(difflib.unified_diff(original['content'].splitlines(True), proposed_source.splitlines(True),
                                           fromfile=target_path, tofile=f'candidate/{target_path}'))
        record = {'validation_status': 'REJECTED' if errors else 'VALID', 'target_path': target_path,
                  'original_sha256': original['sha256'], 'proposed_sha256': proposed_hash,
                  'unified_diff': diff, 'candidate_id': None, 'validation_errors': errors,
                  'explanation': explanation, 'execution_authorized': False,
                  'validation_scope': 'Syntax/interface/source policy only; not isolation or physical safety proof'}
        if violations:
            record.update(violations=violations, source_policy=source_policy(original['content'],self.target),
                          revision_request='Submit a compliant complete-source revision addressing these rule IDs. Preserve the original entrypoint and exactly one top-level function; do not alter protected files. No execution occurred.')
        attempt = uuid4().hex
        folder = self.output / attempt
        folder.mkdir(parents=True, exist_ok=False)
        if not errors:
            record['candidate_id'] = 'candidate_' + attempt
            (folder / 'controller.py').write_text(proposed_source)
            self.records[record['candidate_id']] = {**record, 'source_path': folder / 'controller.py'}
        write_json(folder / 'validation.json', record)
        (folder / 'proposal.diff').write_text(diff)
        return record

    def get(self, candidate_id):
        if candidate_id not in self.records:
            raise ValueError('Candidate identifier was not validated in this session')
        record = self.records[candidate_id]
        raw = record['source_path'].read_bytes()
        if hashlib.sha256(raw).hexdigest() != record['proposed_sha256']:
            raise ValueError('Candidate source hash changed after validation')
        current = read_project_file(self.root, self.target, {self.target})
        if current['sha256'] != record['original_sha256']:
            raise ValueError('Original source changed after proposal validation')
        return record.copy()
