"""Check claim/file/JSON/run consistency; not scientific or execution certification."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path


def read_json(path):
    def invalid(value):
        raise ValueError('Non-finite JSON number: ' + value)
    def check(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Non-finite number after JSON parsing.')
        if isinstance(value, dict):
            for item in value.values():
                check(item)
        if isinstance(value, list):
            for item in value:
                check(item)
    result = json.loads(path.read_text(encoding='utf-8-sig'), parse_constant=invalid)
    check(result)
    return result


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Artifact path escapes the project directory.')
    return path


def pointer_value(data, pointer):
    if not isinstance(pointer, str) or (pointer and not pointer.startswith('/')):
        raise ValueError('Invalid JSON Pointer.')
    if pointer == '':
        return data
    for raw in pointer[1:].split('/'):
        token = raw.replace('~1', '/').replace('~0', '~')
        if isinstance(data, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', token):
                raise ValueError('Invalid array index in JSON Pointer.')
            data = data[int(token)]
        else:
            data = data[token]
    return data


def same_value(a, b):
    if isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool):
        return math.isfinite(a) and math.isfinite(b) and a == b
    return type(a) is type(b) and a == b


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('project', type=Path)
    ap.add_argument('--final', action='store_true', help='Fail if claims are pending or required questions have no verified claim.')
    args = ap.parse_args()
    root = args.project.resolve()
    errors, seen, covered, pending, verified = [], set(), set(), 0, 0
    try:
        claims = read_json(root / 'results' / 'claims.json')['claims']
        if not isinstance(claims, list):
            raise ValueError('claims must be a list.')
        state = read_json(root / 'project_state.json')
        if not isinstance(state, dict):
            raise ValueError('project_state must be an object.')
        for c in claims:
            if not isinstance(c, dict):
                errors.append({'issue': 'Each claim must be an object.'})
                continue
            cid = c.get('id', '<missing>')
            try:
                if not isinstance(cid, str) or cid == '<missing>' or cid in seen:
                    raise ValueError('Missing or duplicate claim id.')
                seen.add(cid)
                if c.get('status') != 'verified':
                    pending += 1
                    continue
                for key in ['question', 'statement', 'unit', 'run_id']:
                    if not isinstance(c.get(key), str) or not c[key].strip():
                        raise ValueError(f'Missing required text field: {key}')
                if not re.fullmatch(r'[A-Za-z0-9_-]+', c['run_id']):
                    raise ValueError('run_id must use letters, digits, underscore or hyphen.')
                artifact = inside(root, c['artifact'])
                expected_hash = c.get('sha256', '')
                if not re.fullmatch('[0-9a-fA-F]{64}', expected_hash):
                    raise ValueError('Missing or invalid SHA256.')
                if hashlib.sha256(artifact.read_bytes()).hexdigest() != expected_hash.lower():
                    raise ValueError('Artifact hash does not match.')
                value = pointer_value(read_json(artifact), c['pointer'])
                if not same_value(value, c['value']):
                    raise ValueError(f'Claim value {c["value"]!r} differs from artifact value {value!r}. Store unrounded values.')
                run_path = inside(root, 'runs/' + c['run_id'] + '.json')
                run = read_json(run_path)
                if not isinstance(run, dict):
                    raise ValueError('Run record must be an object.')
                if run.get('run_id') != c['run_id'] or run.get('status') != 'completed':
                    raise ValueError('Run record does not identify a completed matching run.')
                if not isinstance(run.get('command'), str) or not run['command'].strip():
                    raise ValueError('Run record is missing its command.')
                if not isinstance(run.get('input_hashes'), list):
                    raise ValueError('Run record must include input_hashes (empty only if no data inputs).')
                for item in run['input_hashes']:
                    if not isinstance(item, dict) or not isinstance(item.get('path'), str) or not item['path'] or not re.fullmatch('[0-9a-fA-F]{64}', item.get('sha256', '')):
                        raise ValueError('Each input_hashes entry requires a path and SHA256.')
                code_path = inside(root, run['code_artifact'])
                if hashlib.sha256(code_path.read_bytes()).hexdigest() != run.get('code_sha256'):
                    raise ValueError('Recorded code hash does not match the preserved source.')
                verified += 1
                covered.add(c['question'])
            except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
                errors.append({'claim': cid, 'issue': str(exc)})
        questions = state.get('questions', [])
        if not isinstance(questions, list) or any(not isinstance(q, str) or not q for q in questions):
            raise ValueError('project_state.questions must be a list of nonempty question IDs.')
        if args.final:
            if not questions:
                errors.append({'issue': 'No required questions declared in project_state.json.'})
            if not verified:
                errors.append({'issue': 'No verified numerical claims.'})
            if pending:
                errors.append({'issue': f'{pending} claims remain unverified.'})
            for q in sorted(set(questions) - covered):
                errors.append({'question': q, 'issue': 'No verified claim for this required question.'})
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append({'issue': str(exc)})
    print(json.dumps({'record_consistency': 'issues_found' if errors else 'consistent',
                      'verified_records': verified, 'pending_records': pending, 'errors': errors,
                      'limit': 'Record consistency alone does not prove execution, scientific validity, full task coverage, or submission compliance.'}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == '__main__':
    main()
