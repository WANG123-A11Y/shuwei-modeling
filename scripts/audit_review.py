"""Check ordered three-stage review records and exact candidate hashes.

Usage:
  python audit_review.py PROJECT --fingerprint SKILL.md references/playbook.md
  python audit_review.py PROJECT --review review/review.json

Review JSON: candidate_files [{path, sha256}], scope (text), rounds [{round,
candidate_hash, checks [{stage: facts|logic|unverified, status:
PASS|FAIL|BLOCKED|NOT_RUN, note, evidence: [{locator, finding}], findings: []}]}],
unverified [{id, disposition: labeled|excluded|blocked, affects_final: false, reason}].
Final approval requires all three stages to PASS for the unchanged candidate.
This checks records, not scientific truth or the quality of reviewer reasoning.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

STAGES = ['facts', 'logic', 'unverified']
STATES = {'PASS', 'FAIL', 'BLOCKED', 'NOT_RUN'}


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def local(root, name):
    p = (root / name).resolve()
    if not p.is_relative_to(root):
        raise ValueError('Path escapes project: ' + str(name))
    return p


def fingerprint(root, names):
    items, seen = [], set()
    for name in names:
        p = local(root, name)
        relative = p.relative_to(root).as_posix()
        if relative.casefold() in seen:
            raise ValueError('Duplicate candidate file: ' + relative)
        seen.add(relative.casefold())
        items.append({'path': relative, 'sha256': sha256(p)})
    if not items:
        raise ValueError('Candidate file list is empty.')
    items.sort(key=lambda r: r['path'])
    digest = hashlib.sha256(json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    return items, digest


def audit(root, data):
    if not isinstance(data, dict):
        raise ValueError('Review record must be an object.')
    if not isinstance(data.get('scope'), str) or not data['scope'].strip():
        raise ValueError('An explicit review scope is required.')
    declared = data.get('candidate_files')
    if not isinstance(declared, list) or any(not isinstance(x, dict) for x in declared):
        raise ValueError('candidate_files must be a list of file objects.')
    actual, digest = fingerprint(root, [x['path'] for x in declared])
    expected = {x['path']: x['sha256'] for x in actual}
    for item in declared:
        key = local(root, item['path']).relative_to(root).as_posix()
        if item.get('sha256') != expected[key]:
            raise ValueError('Candidate changed after review: ' + key)
    rounds = data.get('rounds')
    if not isinstance(rounds, list) or not rounds:
        raise ValueError('No review rounds recorded.')
    previous = 0
    for n, rnd in enumerate(rounds):
        if not isinstance(rnd, dict) or type(rnd.get('round')) is not int or rnd['round'] <= previous:
            raise ValueError('Review round numbers must strictly increase.')
        previous = rnd['round']
        if not re.fullmatch('[0-9a-f]{64}', rnd.get('candidate_hash', '')):
            raise ValueError('Every round requires a candidate hash.')
        checks = rnd.get('checks')
        if not isinstance(checks, list) or not checks or len(checks) > 3:
            raise ValueError('Each round needs one to three ordered stage checks.')
        stopped = False
        for idx, check in enumerate(checks):
            if not isinstance(check, dict) or check.get('stage') != STAGES[idx]:
                raise ValueError('Stage order must be facts, logic, unverified.')
            status = check.get('status')
            if status not in STATES:
                raise ValueError('Unknown stage status.')
            if stopped and status != 'NOT_RUN':
                raise ValueError('A failed/blocked stage cannot be followed by another executed stage in the same round.')
            if status == 'NOT_RUN':
                stopped = True
                continue
            if not isinstance(check.get('note'), str) or not check['note'].strip():
                raise ValueError('Executed stages need concrete review notes.')
            evidence = check.get('evidence')
            if not isinstance(evidence, list) or not evidence:
                raise ValueError('Executed stages need located evidence.')
            if any(not isinstance(e, dict) or not isinstance(e.get('locator'), str) or not e['locator'].strip()
                   or not isinstance(e.get('finding'), str) or not e['finding'].strip() for e in evidence):
                raise ValueError('Evidence needs a locator and a concrete finding.')
            findings = check.get('findings')
            if not isinstance(findings, list):
                raise ValueError('Each executed stage needs a findings list.')
            if status == 'PASS' and findings:
                raise ValueError('A passed stage cannot contain unresolved findings.')
            if status in {'FAIL', 'BLOCKED'}:
                if not findings:
                    raise ValueError('Failed/blocked stages need specific findings.')
                stopped = True
        if n == len(rounds) - 1:
            if rnd['candidate_hash'] != digest:
                raise ValueError('Final review is for a different candidate.')
            if len(checks) != 3 or any(c['status'] != 'PASS' for c in checks):
                raise ValueError('Final candidate has not passed all three stages.')
    unverified = data.get('unverified', [])
    if not isinstance(unverified, list):
        raise ValueError('unverified must be a list.')
    for item in unverified:
        if not isinstance(item, dict) or item.get('disposition') not in {'labeled', 'excluded', 'blocked'}:
            raise ValueError('Unverified information needs an explicit disposition.')
        if item.get('affects_final') is not False or not item.get('reason') or not item.get('id'):
            raise ValueError('Unverified information cannot support final factual conclusions.')
    return {'record_consistency': 'consistent', 'candidate_hash': digest,
            'candidate_files': len(actual), 'rounds': len(rounds),
            'limit': 'Record checks do not prove source support, actual review, mathematical correctness, or full-paper coverage.'}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project', type=Path)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--fingerprint', nargs='+', metavar='FILE')
    mode.add_argument('--review', type=str)
    args = ap.parse_args()
    root = args.project.resolve()
    try:
        if args.fingerprint:
            files, digest = fingerprint(root, args.fingerprint)
            result = {'candidate_files': files, 'candidate_hash': digest}
        else:
            data = json.loads(local(root, args.review).read_text(encoding='utf-8-sig'))
            result = audit(root, data)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'record_consistency': 'issues_found', 'issue': str(exc)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
