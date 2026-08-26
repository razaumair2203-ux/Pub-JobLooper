"""Protected inventories cannot disappear behind section or page caps."""
import copy
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import build, gates, match, store, vec


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-inventory-') as data:
        shutil.copytree(os.path.join(ROOT, 'examples', 'starter'), data,
                        dirs_exist_ok=True)
        store.configure(data); vec.reset_caches()
        path = store.p('truth', 'anchors.jsonl')
        rows = store.read_jsonl(path)
        additions = []
        for typ, source_id, new_id, old, new in (
                ('publication', 'PUB-001', 'PUB-002', 'Fictional', 'Additional Fictional'),
                ('education', 'EDU-001', 'EDU-002', 'Electrical', 'Electronic'),
                ('credential', 'CRED-001', 'CRED-002', 'Project Leader', 'Programme Leader')):
            source = next(row for row in rows if row['id'] == source_id)
            clone = copy.deepcopy(source); clone['id'] = new_id
            clone['fact'] = clone['fact'].replace(old, new)
            clone['bullet'] = {key: value.replace(old, new)
                               for key, value in clone['bullet'].items()}
            for ref in clone.get('evidence_refs') or []:
                ref['locator'] = new_id
            additions.append(clone)
        store.write_jsonl(path, rows + additions)
        section_path = store.p('truth', 'sections.json')
        sections = store.read_json(section_path)
        for section in sections['sections']:
            if section['id'] in {'research', 'education', 'certifications'}:
                section['max'] = 1
        for lane in sections.get('lanes', {}).values():
            lane.setdefault('caps', {})['research'] = 1
            lane['caps']['certifications'] = 1
        store.write_json(section_path, sections); store.reset_context_cache()

        slug = store.list_jobs()[0]
        jd = store.read_json(os.path.join(store.job_dir(slug), 'jd.json'))
        jd['_slug'] = slug
        identity = match.pick_identity(jd)
        mapping = match.match_jd(jd, identity)
        cv = build.assemble(jd, mapping, target_pages=2)
        selected = set(cv['_selection']['selected_ids'])
        checks.append(('publication overflow survives a lower lane cap',
                       {'PUB-001', 'PUB-002'} <= selected))
        checks.append(('every verified degree survives a lower section cap',
                       {'EDU-001', 'EDU-002'} <= selected))
        checks.append(('every professional credential survives a lower section cap',
                       {'CRED-001', 'CRED-002'} <= selected))
        level, _, details = gates.g8_document(cv)
        checks.append(('document gate sees no protected-inventory omission',
                       not any('protected candidate inventory omitted' in row
                               for row in details)))

        removed = copy.deepcopy(cv)
        credential_section = next(section for section in removed['sections']
                                  if section['name'] == 'CERTIFICATIONS')
        credential_section['items'] = [item for item in credential_section['items']
                                       if item.get('anchor') != 'CRED-002']
        for row in removed['_selection']['omitted']:
            if row['id'] == 'CRED-002':
                row['protected'] = True
        removed['_selection']['selected_ids'].remove('CRED-002')
        level, _, details = gates.g8_document(removed)
        checks.append(('forced protected omission blocks the document',
                       level == gates.BLOCK and any(
                           'protected candidate inventory omitted' in row for row in details)))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} protected-inventory invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
