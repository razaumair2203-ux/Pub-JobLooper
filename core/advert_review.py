"""Explicit confirmation of the exact advert before fit analysis begins."""
import os

from . import store


RECEIPT_NAME = 'advert-review.json'


def subject(slug, jd=None):
    jd = jd or store.read_json(os.path.join(store.job_dir(slug), 'jd.json'), {}) or {}
    raw = store.read_text(os.path.join(store.job_dir(slug), 'jd.raw.md'))
    value = {
        'app_id': slug, 'raw_sha256': store.sha256_text(raw),
        'company': str(jd.get('company') or '').strip(),
        'title': str(jd.get('title') or '').strip(),
        'url': str(jd.get('url') or '').strip() or None,
    }
    return {**value, 'sha256': store.sha256_text(store.canonical_json(value))}


def state(slug):
    jd = store.read_json(os.path.join(store.job_dir(slug), 'jd.json'), {}) or {}
    current = subject(slug, jd)
    receipt = store.read_json(
        os.path.join(store.job_dir(slug), RECEIPT_NAME), {}) or {}
    confirmed = (receipt.get('status') == 'CONFIRMED'
                 and receipt.get('subject_sha256') == current['sha256'])
    return {
        'status': 'CONFIRMED' if confirmed else 'REVIEW_REQUIRED',
        'confirmed': confirmed, 'subject': current, 'receipt': receipt,
        'raw': store.read_text(os.path.join(store.job_dir(slug), 'jd.raw.md')),
    }


def initialize(slug):
    current = subject(slug)
    receipt = {
        '_schema': 'joblooper.advert-review.v1', 'app_id': slug,
        'status': 'REVIEW_REQUIRED', 'subject_sha256': current['sha256'],
        'captured_at': store.now(),
    }
    store.write_json(os.path.join(store.job_dir(slug), RECEIPT_NAME), receipt)
    return receipt


def confirm(slug, company, title, reviewer='dashboard-user'):
    directory = store.job_dir(slug)
    jd = store.read_json(os.path.join(directory, 'jd.json'), {}) or {}
    if not jd:
        raise ValueError('Captured advert record is missing')
    company = str(company or '').strip()
    title = str(title or '').strip()
    reviewer = str(reviewer or '').strip()
    if not company or not title:
        raise ValueError('Confirm the exact company and job title')
    if len(company) > 200 or len(title) > 300 or not reviewer:
        raise ValueError('Advert confirmation fields are incomplete or too long')
    jd['company'] = company
    jd['title'] = title
    store.write_json(os.path.join(directory, 'jd.json'), jd)
    current = subject(slug, jd)
    receipt = {
        '_schema': 'joblooper.advert-review.v1', 'app_id': slug,
        'status': 'CONFIRMED', 'subject_sha256': current['sha256'],
        'raw_sha256': current['raw_sha256'], 'company': company, 'title': title,
        'url': current['url'], 'reviewer': reviewer, 'confirmed_at': store.now(),
        'confirmation': ('I reviewed the complete captured advert, company and title '
                         'before fit analysis.'),
    }
    store.write_json(os.path.join(directory, RECEIPT_NAME), receipt)
    store.append_application_event({
        'event': 'ADVERT_CONFIRMED', 'app_id': slug,
        'subject_sha256': current['sha256'], 'company': company, 'role': title,
        'reviewer': reviewer,
    })
    return receipt


def require(slug):
    result = state(slug)
    if not result['confirmed']:
        raise ValueError('Review and confirm the complete captured advert before preflight')
    return result['receipt']
