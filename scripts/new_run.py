"""Create a non-destructive modeling workspace, never fabricated results."""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--title', required=True)
    ap.add_argument('--mode', choices=['practice', 'competition'], default='practice')
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()
    root = args.out.resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        ap.error('Output must be a new or empty directory; existing work is never overwritten.')
    root.mkdir(parents=True, exist_ok=True)
    for name in ['src', 'results', 'figures', 'runs', 'paper', 'review']:
        (root / name).mkdir()
    state = {
        'title': args.title, 'mode': args.mode,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'stage': 'intake', 'edition': None, 'deadline': None,
        'deadline_timezone': None, 'rules_status': 'unverified',
        'seed': args.seed, 'questions': [], 'open_issues': [],
        'next_action': 'Read the actual problem and map every required output.'
    }
    (root / 'project_state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    (root / 'results' / 'claims.json').write_text('{"claims": []}\n', encoding='utf-8')
    tables = {
        'problem_map.csv': ['question', 'required_output', 'input_source', 'unknown_or_decision', 'hard_constraint', 'validation', 'depends_on', 'source_locator'],
        'sources.csv': ['source_id', 'title_or_file', 'locator', 'version_or_access_date', 'status', 'supports_claim'],
        'experiments.csv': ['experiment_id', 'question', 'hypothesis', 'baseline', 'model', 'split', 'metric', 'seed', 'budget', 'status', 'run_id'],
    }
    for name, fields in tables.items():
        with (root / name).open('w', encoding='utf-8-sig', newline='') as f:
            csv.writer(f).writerow(fields)
    template = Path(__file__).resolve().parents[1] / 'assets' / 'paper-outline.md'
    (root / 'paper' / 'manuscript.md').write_text(template.read_text(encoding='utf-8'), encoding='utf-8')
    model_template = template.parent / 'model-contract.md'
    (root / 'model_contract.md').write_text(model_template.read_text(encoding='utf-8'), encoding='utf-8')
    print(json.dumps({'created': str(root), 'stage': 'intake', 'results_computed': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
