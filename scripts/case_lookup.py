"""Search curated local ShuWei cases and optionally read original PDF pages."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--query', default='')
    ap.add_argument('--year', choices=['2023', '2024', '2025'])
    ap.add_argument('--filename')
    ap.add_argument('--pages', help='One-based PDF page numbers, e.g. 7,26 (not printed page labels).')
    ap.add_argument('--source-root', type=Path, action='append', default=[])
    args = ap.parse_args()
    if args.pages and not args.filename:
        ap.error('--pages requires --filename to identify one source.')
    index = Path(__file__).resolve().parents[1] / 'references' / 'corpus-index.json'
    records = json.loads(index.read_text(encoding='utf-8'))['sources']
    terms = args.query.casefold().split()
    matched = [r for r in records if (not args.year or r['year'] == args.year)
               and (not args.filename or r['filename'] == args.filename)
               and all(t in json.dumps({k:v for k,v in r.items() if k != 'path'}, ensure_ascii=False).casefold() for t in terms)]
    if args.pages:
        if len(matched) != 1:
            ap.error(f'Expected one source, found {len(matched)}.')
        r = matched[0]
        source = Path(r['path'])
        if not source.is_file():
            candidates = [p for root in args.source_root for p in root.rglob(r['filename']) if p.is_file()]
            if len(candidates) != 1:
                ap.error('Original source unavailable or ambiguous. Use --source-root; curated notes are not a fresh source read.')
            source = candidates[0]
        try:
            from pypdf import PdfReader
        except ImportError:
            ap.error('PDF extraction requires pypdf; the curated index works without it.')
        try:
            requested = [int(n) for n in args.pages.split(',')]
        except ValueError:
            ap.error('--pages must be comma-separated integers.')
        reader = PdfReader(source)
        if any(n < 1 or n > len(reader.pages) for n in requested):
            ap.error(f'Page out of range: valid PDF pages are 1..{len(reader.pages)}.')
        actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        print(json.dumps({'source': str(source), 'hash_matches_index': actual_hash == r['sha256'],
                          'warning': 'Text extraction may corrupt equations; visually inspect critical formulas.'}, ensure_ascii=False))
        for n in requested:
            extracted = (reader.pages[n-1].extract_text() or '').encode('utf-16', 'surrogatepass').decode('utf-16', 'replace')
            print(f'\n--- PDF page {n} ---\n{extracted}')
    else:
        for r in matched:
            print(json.dumps({k: r[k] for k in ['filename', 'year', 'kind', 'topic', 'methods', 'review_level', 'reviewed_pdf_pages']}, ensure_ascii=False))
        if not matched:
            print('No matching curated source. Search another keyword or inspect the new problem independently.')


if __name__ == '__main__':
    main()
