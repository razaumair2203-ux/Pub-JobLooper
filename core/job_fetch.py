"""Bounded, SSRF-resistant extraction of one public job advert URL."""
import html as html_lib
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser


MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MIN_ADVERT_CHARS = 240
BLOCK_SIGNALS = (
    'access denied', 'request blocked', 'verify you are human', 'captcha',
    'enable javascript', 'just a moment', 'security check', 'robot check',
)
GENERIC_TITLES = {
    'careers', 'career opportunities', 'find jobs', 'job opportunities',
    'job search', 'search jobs', 'vacancies',
}
PLATFORM_COMPANIES = {
    'oracle', 'successfactors', 'taleo', 'workday',
}
BLOCK_TAGS = {
    'address', 'article', 'aside', 'blockquote', 'br', 'div', 'footer', 'h1',
    'h2', 'h3', 'h4', 'header', 'li', 'main', 'nav', 'ol', 'p', 'section',
    'table', 'td', 'th', 'tr', 'ul',
}


class FetchError(ValueError):
    pass


def _validate_public_url(value, resolve_dns=True):
    value = str(value or '').strip()
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError as error:
        raise FetchError('The job link is not a valid URL') from error
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise FetchError('The job link must use public HTTP or HTTPS')
    if parsed.username or parsed.password:
        raise FetchError('The job link cannot contain credentials')
    try:
        port = parsed.port
    except ValueError as error:
        raise FetchError('The job link contains an invalid web port') from error
    if port not in {None, 80, 443}:
        raise FetchError('The job link must use a standard web port')
    hostname = parsed.hostname.rstrip('.').casefold()
    if hostname == 'localhost' or hostname.endswith(('.localhost', '.local')):
        raise FetchError('Local and private-network URLs are not permitted')
    if resolve_dns:
        try:
            addresses = {
                row[4][0] for row in socket.getaddrinfo(
                    parsed.hostname, port or (443 if parsed.scheme == 'https' else 80),
                    type=socket.SOCK_STREAM)
            }
        except OSError as error:
            raise FetchError('The job site hostname could not be resolved') from error
        if not addresses:
            raise FetchError('The job site hostname did not resolve to an address')
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if (not ip.is_global or ip.is_private or ip.is_loopback
                    or ip.is_link_local or ip.is_multicast or ip.is_reserved):
                raise FetchError('Local and private-network URLs are not permitted')
    return urllib.parse.urlunsplit(parsed)


def _clean_text(value):
    lines = []
    for raw in str(value or '').replace('\r', '\n').split('\n'):
        line = re.sub(r'[ \t\f\v]+', ' ', html_lib.unescape(raw)).strip()
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    return '\n'.join(lines).strip()


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'li':
            # JSON-LD JobPosting descriptions often encode each requirement as
            # an HTML list item. Preserve that structure so the deterministic
            # JD parser does not have to guess whether an unpunctuated line is
            # a heading or a candidate requirement.
            self.parts.append('\n- ')
        elif tag in BLOCK_TAGS:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in BLOCK_TAGS:
            self.parts.append('\n')

    def handle_data(self, data):
        self.parts.append(data)


def _strip_html(value):
    parser = _TextParser()
    parser.feed(str(value or ''))
    return _clean_text(''.join(parser.parts))


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.json_ld = []
        self._json_parts = None
        self._skip = 0
        self._main = 0
        self._heading = None
        self._heading_parts = []
        self._title = False
        self._title_parts = []
        self.headings = []
        self.all_parts = []
        self.main_parts = []
        self.meta = {}

    def _break(self):
        self.all_parts.append('\n')
        if self._main:
            self.main_parts.append('\n')

    def handle_starttag(self, tag, attrs):
        attrs = {str(key).casefold(): value for key, value in attrs}
        if tag == 'script' and str(attrs.get('type') or '').casefold().split(';')[0] \
                == 'application/ld+json':
            self._json_parts = []
            return
        if tag in {'script', 'style', 'noscript', 'svg'}:
            self._skip += 1
            return
        if tag in {'main', 'article'}:
            self._main += 1
        if tag == 'title':
            self._title = True
        if tag in {'h1', 'h2'}:
            self._heading = tag
            self._heading_parts = []
        if tag == 'meta':
            key = str(attrs.get('property') or attrs.get('name') or '').casefold()
            content = str(attrs.get('content') or '').strip()
            if key and content:
                self.meta[key] = content
        if tag in BLOCK_TAGS:
            self._break()

    def handle_endtag(self, tag):
        if tag == 'script' and self._json_parts is not None:
            value = ''.join(self._json_parts).strip()
            if value:
                self.json_ld.append(value)
            self._json_parts = None
            return
        if tag in {'script', 'style', 'noscript', 'svg'} and self._skip:
            self._skip -= 1
            return
        if tag == 'title':
            self._title = False
        if tag == self._heading:
            heading = _clean_text(' '.join(self._heading_parts))
            if heading:
                self.headings.append((tag, heading))
            self._heading = None
            self._heading_parts = []
        if tag in BLOCK_TAGS:
            self._break()
        if tag in {'main', 'article'} and self._main:
            self._main -= 1

    def handle_data(self, data):
        if self._json_parts is not None:
            self._json_parts.append(data)
            return
        if self._skip:
            return
        self.all_parts.append(data)
        if self._main:
            self.main_parts.append(data)
        if self._heading:
            self._heading_parts.append(data)
        if self._title:
            self._title_parts.append(data)

    @property
    def title(self):
        return _clean_text(' '.join(self._title_parts))


def _job_objects(value):
    if isinstance(value, list):
        for item in value:
            yield from _job_objects(item)
        return
    if not isinstance(value, dict):
        return
    kind = value.get('@type')
    kinds = kind if isinstance(kind, list) else [kind]
    if any(str(item).casefold() == 'jobposting' for item in kinds):
        yield value
    for key in ('@graph', 'mainEntity', 'itemListElement'):
        if key in value:
            yield from _job_objects(value[key])


def _organisation_name(job):
    organisation = job.get('hiringOrganization') or job.get('organization') or {}
    if isinstance(organisation, dict):
        return str(organisation.get('name') or '').strip()
    return str(organisation or '').strip()


def _clean_company(value):
    value = _clean_text(value).split('\n', 1)[0]
    return re.sub(r'\s+(?:careers?|jobs?|recruitment)$', '', value,
                  flags=re.I).strip()


def extract(html, url):
    """Extract verified employer fields from already-fetched HTML."""
    parser = _PageParser()
    parser.feed(str(html or ''))
    jobs = []
    for block in parser.json_ld:
        try:
            jobs.extend(_job_objects(json.loads(block)))
        except (TypeError, ValueError):
            continue
    job = max(jobs, key=lambda row: len(str(row.get('description') or '')), default={})
    title = _clean_text(job.get('title') or job.get('name')).split('\n', 1)[0]
    company = _clean_company(_organisation_name(job))
    description = _strip_html(job.get('description'))
    source = 'json_ld_jobposting' if job else 'visible_page'

    if not title:
        title = next((text for tag, text in parser.headings if tag == 'h1'), '')
        title = title or _clean_text(parser.meta.get('og:title')).split('\n', 1)[0]
    if not company:
        company = _clean_company(
            parser.meta.get('og:site_name') or parser.meta.get('application-name'))
    if not description:
        main = _clean_text(''.join(parser.main_parts))
        description = main if len(main) >= MIN_ADVERT_CHARS else _clean_text(
            ''.join(parser.all_parts))

    combined = ' '.join((parser.title, title, company, description[:1000])).casefold()
    if any(signal in combined for signal in BLOCK_SIGNALS):
        raise FetchError('The job site returned an access, JavaScript or human-verification page')
    if not title:
        raise FetchError('The job title could not be extracted reliably')
    if title.casefold().strip() in GENERIC_TITLES:
        raise FetchError('The page exposed a generic careers heading, not the exact job title')
    if not company:
        raise FetchError('The employer name could not be extracted reliably')
    if company.casefold().strip() in PLATFORM_COMPANIES:
        raise FetchError('The page exposed its recruitment platform, not the employer name')
    if len(description) < MIN_ADVERT_CHARS:
        raise FetchError('The page did not expose a complete job description')
    return {
        'url': url, 'company': company[:200], 'title': title[:300],
        'jd': description[:120000], 'extractor': source,
        'characters': min(len(description), 120000),
    }


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe = _validate_public_url(
            urllib.parse.urljoin(req.full_url, newurl), resolve_dns=True)
        return super().redirect_request(req, fp, code, msg, headers, safe)


def fetch(url, timeout=20):
    """Fetch and extract one public advert without allowing private-network access."""
    safe_url = _validate_public_url(url, resolve_dns=True)
    opener = urllib.request.build_opener(_SafeRedirect())
    request = urllib.request.Request(safe_url, headers={
        'User-Agent': 'Joblooper/1.0 (+local evidence-governed job intake)',
        'Accept': 'text/html,application/xhtml+xml,text/plain;q=0.8',
        'Accept-Encoding': 'identity',
    })
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = _validate_public_url(response.geturl(), resolve_dns=True)
            content_type = str(response.headers.get_content_type() or '').casefold()
            if content_type not in {'text/html', 'application/xhtml+xml', 'text/plain'}:
                raise FetchError(f'The job link returned unsupported content type {content_type}')
            declared = response.headers.get('Content-Length')
            try:
                declared_size = int(declared) if declared else None
            except ValueError as error:
                raise FetchError('The job site returned an invalid response size') from error
            if declared_size is not None and declared_size > MAX_RESPONSE_BYTES:
                raise FetchError('The job page exceeds the 4 MB extraction limit')
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise FetchError('The job page exceeds the 4 MB extraction limit')
            charset = response.headers.get_content_charset() or 'utf-8'
            try:
                page = body.decode(charset, errors='replace')
            except LookupError as error:
                raise FetchError('The job site returned an unsupported text encoding') from error
    except FetchError:
        raise
    except (OSError, ValueError, urllib.error.URLError) as error:
        raise FetchError(f'The job site could not be accessed directly: {error}') from error
    return extract(page, final_url)
