"""Inspect local inputs without modifying them; large data stay streamed/metadata-only."""
import argparse
import collections
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def annotation_info(path, labels_by_path=None):
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    info = {'path': str(path), 'kind': type(data).__name__, 'records': len(data) if isinstance(data, (list, dict)) else None}
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return info
    info['keys'] = list(data[0])
    if not {'image_id', 'disease_class'} <= set(data[0]):
        return info
    images_dir = path.parent / 'images'
    names = {p.name.casefold() for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS} if images_dir.is_dir() else set()
    labels, matched_labels, seen, missing, invalid = collections.Counter(), collections.Counter(), collections.Counter(), [], 0
    for row in data:
        if not isinstance(row, dict) or 'image_id' not in row or 'disease_class' not in row:
            invalid += 1
            continue
        label = str(row['disease_class'])
        name = str(row['image_id']).replace('\\', '/').rsplit('/', 1)[-1].casefold()
        labels[label] += 1
        seen[name] += 1
        if name in names:
            matched_labels[label] += 1
            if labels_by_path is not None:
                labels_by_path.setdefault(str((images_dir / name).resolve()).casefold(), set()).add(label)
        else:
            missing.append(name)
    info.update(images_on_disk=len(names), classes_in_annotations=len(labels), class_counts=dict(labels),
                annotation_records_matching_files=sum(matched_labels.values()), matched_class_counts=dict(matched_labels),
                missing_annotation_image_records=len(missing), missing_examples=missing[:5], invalid_records=invalid,
                repeated_image_id_records=sum(n - 1 for n in seen.values() if n > 1), image_decoding_checked=False)
    return info


def list_info(path, labels_by_path=None):
    images_dir = path.parent / 'images'
    names = {p.name.casefold() for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS} if images_dir.is_dir() else set()
    classes, matched, ids = collections.Counter(), collections.Counter(), collections.Counter()
    missing, invalid, records = [], 0, 0
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        records += 1
        parts = line.rsplit(None, 1)
        if len(parts) != 2:
            invalid += 1
            continue
        rel, label = parts
        name = rel.replace('\\', '/').rsplit('/', 1)[-1].casefold()
        classes[label] += 1
        ids[name] += 1
        if name in names:
            matched[label] += 1
            if labels_by_path is not None:
                labels_by_path.setdefault(str((images_dir / name).resolve()).casefold(), set()).add(label)
        else:
            missing.append(name)
    return {'path': str(path), 'records': records, 'classes': len(classes), 'class_counts': dict(classes),
            'records_matching_files': sum(matched.values()), 'matched_class_counts': dict(matched),
            'missing_file_records': len(missing), 'missing_examples': missing[:5], 'invalid_records': invalid,
            'repeated_basename_records': sum(n - 1 for n in ids.values() if n > 1),
            'mapping_basis': 'basename within the sibling images directory; verify actual loader paths', 'image_decoding_checked': False}


def csv_info(path):
    last_error = None
    for encoding in ['utf-8-sig', 'gb18030']:
        try:
            with path.open('r', encoding=encoding, newline='') as f:
                sample = f.read(4096)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=',\t;|')
                except csv.Error:
                    dialect = csv.excel_tab if path.suffix.lower() == '.tsv' else csv.excel
                f.seek(0)
                rows = csv.reader(f, dialect)
                first = next(rows, [])
            return {'path': str(path), 'encoding': encoding, 'first_row': first, 'row_count': 'not scanned', 'header_status': 'candidate; confirm from source'}
        except UnicodeError as e:
            last_error = str(e)
    return {'path': str(path), 'error': last_error}


def xlsx_info(path):
    try:
        import openpyxl
    except ImportError:
        return {'path': str(path), 'status': 'not inspected; openpyxl unavailable'}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=False)
    try:
        sheets = [{'name': s.title, 'declared_rows': s.max_row, 'declared_columns': s.max_column,
                   'first_rows': list(s.iter_rows(max_row=4, max_col=8, values_only=True))} for s in wb]
        return {'path': str(path), 'sheets': sheets, 'note': 'dimensions may include formatting; rows are not confirmed observations'}
    finally:
        wb.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('root', type=Path)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--hash-images', action='store_true', help='Read image bytes for exact duplicate hashes; no perceptual check.')
    args = ap.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        ap.error('Input root is not a directory.')
    files = sorted(p for p in root.rglob('*') if p.is_file())
    report = {'root': str(root), 'generated_at': datetime.now(timezone.utc).isoformat(),
              'files': len(files), 'bytes': sum(p.stat().st_size for p in files),
              'extensions': dict(collections.Counter(p.suffix.lower() for p in files)),
              'annotations': [], 'image_lists': [], 'tables': [], 'warnings': [],
              'exact_image_duplicates_checked': args.hash_images, 'perceptual_duplicates_checked': False,
              'image_decoding_checked': False}
    labels_by_path = {}
    for path in files:
        ext = path.suffix.lower()
        try:
            if ext == '.json' and path.stat().st_size <= 20 * 1024 * 1024:
                report['annotations'].append(annotation_info(path, labels_by_path))
            elif path.name.lower() in {'train_list.txt', 'test_list.txt', 'ttest_list.txt', 'val_list.txt'}:
                report['image_lists'].append(list_info(path, labels_by_path))
            elif ext in {'.csv', '.tsv'}:
                report['tables'].append(csv_info(path))
            elif ext == '.xlsx':
                report['tables'].append(xlsx_info(path))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            report['warnings'].append({'path': str(path), 'error': str(exc)})
    if args.hash_images:
        groups = collections.defaultdict(list)
        for path in files:
            if path.suffix.lower() in IMAGE_EXTS:
                try:
                    groups[digest(path)].append(str(path))
                except OSError as exc:
                    report['warnings'].append({'path': str(path), 'error': str(exc)})
        report['exact_duplicate_groups'] = [v for v in groups.values() if len(v) > 1]
        report['exact_duplicate_details'] = []
        for sha, paths in groups.items():
            if len(paths) <= 1:
                continue
            labels = set().union(*(labels_by_path.get(p.casefold(), set()) for p in paths))
            report['exact_duplicate_details'].append({
                'sha256': sha, 'files': [{'path': p, 'directly_matched_labels': sorted(labels_by_path.get(p.casefold(), set()))} for p in paths],
                'multiple_image_directories': len({str(Path(p).parent).casefold() for p in paths}) > 1,
                'direct_label_conflict': len(labels) > 1,
                'note': 'Multiple directories indicate possible split leakage; inspect split definitions. Labels are annotation/list matches, not semantic truth.'})
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str, allow_nan=False)
    if args.out:
        out = args.out.resolve()
        if out in files:
            ap.error('Output must not overwrite an existing input file.')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding='utf-8')
        print(json.dumps({'report': str(out), 'files': len(files), 'warnings': len(report['warnings'])}, ensure_ascii=False))
    else:
        print(text)


if __name__ == '__main__':
    main()
