"""cv.json -> DOCX / Markdown / ATS plain-text / PDF.

The DOCX is written as raw OOXML rather than through python-docx. That is a
deliberate trade: zero dependencies, byte-level control, and an ATS-safe result
by construction -- single column, real Word styles, real list numbering, no
tables, no text boxes, no floating anything, no content in headers or footers.
Those are exactly the constructs that break CV parsers.
"""
import os, re, zipfile, subprocess, html, shutil, tempfile
from pathlib import Path
from . import store

# ---------------------------------------------------------------- style

DEFAULT_STYLE = {
    "font": "Arial",
    "size_body": 20,        # half-points -> 10.0pt
    "size_name": 32,        # 16pt
    "size_headline": 18,    # 9pt
    "size_section": 22,     # 11pt
    "page_w": 12240, "page_h": 15840,          # US Letter, twips
    "margin": 720,                              # 0.5 inch
    "space_after_body": 40,
    "space_before_section": 160,
    # Word's value for full justification. Applied to prose and evidence
    # bullets; headings, dates and compact inventory lines remain left aligned.
    "body_alignment": "both",
}

def style():
    s = dict(DEFAULT_STYLE)
    s.update(store.read_json(store.p('templates', 'style.json'), {}) or {})
    return s


def _display_link(label, url):
    clean = re.sub(r'^https?://', '', str(url or '')).rstrip('/')
    known = {
        'linkedin': 'LinkedIn', 'github': 'GitHub',
        'google_scholar': 'Google Scholar',
    }
    display = known.get(str(label).lower(), label.replace('_', ' ').title())
    return f"{display}: {clean}"

# Codepoints XML 1.0 cannot represent at all. Left in place they do not degrade
# the document -- they make it unparseable by every reader including Word.
_XML_ILLEGAL = re.compile(r'[^\x09\x0A\x0D\x20-퟿-�\U00010000-\U0010ffff]')


def esc(t, attr=False):
    """Escape for XML.

    `attr=True` is REQUIRED for anything landing inside an attribute value --
    hyperlink Target URLs especially. Element text may legally contain a bare
    quote; an attribute value may not, and a single unescaped quote in a URL
    produced a relationships part no parser could read.
    """
    s = _XML_ILLEGAL.sub('', str(t or ''))
    s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    if attr:
        s = s.replace('"', '&quot;').replace("'", '&apos;')
    return s

def _runs(text, sz, bold=False, italic=False, caps=False, color=None, font=None):
    rpr = f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>' if font else ''
    rpr += '<w:b/>' if bold else ''
    rpr += '<w:i/>' if italic else ''
    rpr += '<w:caps/>' if caps else ''
    rpr += f'<w:color w:val="{color}"/>' if color else ''
    rpr += f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
    return f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{esc(text)}</w:t></w:r>'

def _p(inner, style_id=None, space_before=0, space_after=0, jc=None,
       ind_left=0, ind_hang=0, numid=None, border_bottom=False, keep_next=False):
    ppr = ''
    if style_id:
        ppr += f'<w:pStyle w:val="{style_id}"/>'
    if numid:
        ppr += f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{numid}"/></w:numPr>'
    if ind_left or ind_hang:
        ppr += f'<w:ind w:left="{ind_left}" w:hanging="{ind_hang}"/>'
    if border_bottom:
        ppr += ('<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" '
                'w:color="404040"/></w:pBdr>')
    if keep_next:
        ppr += '<w:keepNext/>'
    ppr += f'<w:spacing w:before="{space_before}" w:after="{space_after}" w:line="240" w:lineRule="auto"/>'
    if jc:
        ppr += f'<w:jc w:val="{jc}"/>'
    return f'<w:p><w:pPr>{ppr}</w:pPr>{inner}</w:p>'


# ---------------------------------------------------------------- parts

def _content_types():
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
            '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '</Types>')

def _root_rels():
    R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{R}/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '</Relationships>')

def _doc_rels(links):
    R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    rels = [f'<Relationship Id="rId1" Type="{R}/styles" Target="styles.xml"/>',
            f'<Relationship Id="rId2" Type="{R}/numbering" Target="numbering.xml"/>',
            f'<Relationship Id="rId3" Type="{R}/settings" Target="settings.xml"/>']
    for rid, url in links:
        rels.append(f'<Relationship Id="{rid}" Type="{R}/hyperlink" '
                    f'Target="{esc(url, attr=True)}" TargetMode="External"/>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + ''.join(rels) + '</Relationships>')

def _styles(s, language='en-US'):
    f, b = s['font'], s['size_body']
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:docDefaults><w:rPrDefault><w:rPr>'
            f'<w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:eastAsia="{f}" w:cs="{f}"/>'
            f'<w:sz w:val="{b}"/><w:szCs w:val="{b}"/><w:lang w:val="{esc(language, attr=True)}"/>'
            '</w:rPr></w:rPrDefault>'
            '<w:pPrDefault><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
            '</w:pPr></w:pPrDefault></w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
            '<w:name w:val="Normal"/></w:style>'
            '<w:style w:type="paragraph" w:styleId="CVSection">'
            '<w:name w:val="CV Section"/><w:basedOn w:val="Normal"/>'
            f'<w:rPr><w:b/><w:sz w:val="{s["size_section"]}"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="CVBullet">'
            '<w:name w:val="CV Bullet"/><w:basedOn w:val="Normal"/></w:style>'
            '<w:style w:type="numbering" w:styleId="CVList">'
            '<w:name w:val="CV List"/></w:style>'
            '</w:styles>')

def _numbering():
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>'
            '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/>'
            '<w:lvlText w:val="•"/><w:lvlJc w:val="left"/>'
            '<w:pPr><w:ind w:left="288" w:hanging="288"/></w:pPr>'
            '<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:hint="default"/></w:rPr>'
            '</w:lvl></w:abstractNum>'
            '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
            '</w:numbering>')

def _settings():
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:compat><w:compatSetting w:name="compatibilityMode" '
            'w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat>'
            '</w:settings>')

def _core(cv):
    kind = cv.get('document_kind', 'CV')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:title>{esc(cv.get("header",{}).get("name",""))} - {esc(kind)}</dc:title>'
            f'<dc:creator>{esc(cv.get("header",{}).get("name",""))}</dc:creator>'
            '</cp:coreProperties>')


# ---------------------------------------------------------------- document

def _build_document(cv, s):
    h = cv.get('header', {})
    body, links = [], []

    body.append(_p(_runs(h.get('name', ''), s['size_name'], bold=True),
                   jc='center', space_after=20))
    if h.get('headline'):
        body.append(_p(_runs(h['headline'], s['size_headline'], color='333333'),
                       jc='center', space_after=20))

    contact = ' | '.join(x for x in h.get('contact', []) if x)
    live = [(k, v) for k, v in (h.get('links') or {}).items() if v]
    if contact or live:
        inner = _runs(contact, s['size_headline'])
        for i, (label, url) in enumerate(live):
            rid = f'rId{100+i}'
            links.append((rid, url if url.startswith('http') else 'https://' + url))
            inner += _runs('  |  ', s['size_headline'])
            inner += (f'<w:hyperlink r:id="{rid}">'
                      + _runs(_display_link(label, url), s['size_headline'], color='0563C1') +
                      '</w:hyperlink>')
        body.append(_p(inner, jc='center', space_after=60))

    for sec in cv.get('sections', []):
        if not sec.get('items'):
            continue
        body.append(_p(_runs(sec['name'], s['size_section'], bold=True, caps=True),
                       space_before=s['space_before_section'], space_after=40,
                       border_bottom=True, keep_next=True))
        typ = sec.get('type', 'bullets')

        for item in sec['items']:
            if typ in ('para', 'band'):
                body.append(_p(_runs(item['text'], s['size_body']),
                               space_after=s['space_after_body'],
                               jc=s['body_alignment'] if typ == 'para' else None))

            elif typ == 'experience':
                body.append(_p(_runs(item.get('title', ''), s['size_body'], bold=True),
                               space_before=90, space_after=0, keep_next=True))
                sub = ' | '.join(x for x in [item.get('org'), item.get('period')] if x)
                if sub:
                    body.append(_p(_runs(sub, s['size_body'], italic=True, color='444444'),
                                   space_after=30, keep_next=True))
                if item.get('framing'):
                    body.append(_p(_runs(item['framing'], s['size_body'], color='333333'),
                                   space_after=40, keep_next=True, jc=s['body_alignment']))
                for b in item.get('bullets', []):
                    body.append(_p(_runs(b['text'], s['size_body']),
                                   numid=1, space_after=s['space_after_body'],
                                   jc=s['body_alignment']))

            elif typ == 'list':
                body.append(_p(_runs(item['text'], s['size_body']),
                               numid=1, space_after=s['space_after_body'],
                               jc=s['body_alignment']))

            else:  # plain lines, e.g. education / certifications
                body.append(_p(_runs(item['text'], s['size_body']),
                               space_after=s['space_after_body']))

    sect = (f'<w:sectPr><w:pgSz w:w="{s["page_w"]}" w:h="{s["page_h"]}"/>'
            f'<w:pgMar w:top="{s["margin"]}" w:right="{s["margin"]}" '
            f'w:bottom="{s["margin"]}" w:left="{s["margin"]}" '
            'w:header="0" w:footer="0" w:gutter="0"/></w:sectPr>')

    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
           '<w:body>' + ''.join(body) + sect + '</w:body></w:document>')
    return doc, links


def to_docx(cv, out_path):
    s = style()
    doc, links = _build_document(cv, s)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as z:
        def stable_write(name, value):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            z.writestr(info, value.encode('utf-8'))

        stable_write('[Content_Types].xml', _content_types())
        stable_write('_rels/.rels', _root_rels())
        stable_write('word/document.xml', doc)
        stable_write('word/_rels/document.xml.rels', _doc_rels(links))
        stable_write('word/styles.xml', _styles(s, cv.get('language', 'en-US')))
        stable_write('word/numbering.xml', _numbering())
        stable_write('word/settings.xml', _settings())
        stable_write('docProps/core.xml', _core(cv))
    return out_path


# ---------------------------------------------------------------- other formats

def to_markdown(cv):
    h = cv.get('header', {})
    o = [f"# {h.get('name','')}", '']
    if h.get('headline'):
        o += [f"*{h['headline']}*", '']
    contact = [x for x in h.get('contact', []) if x]
    contact += [_display_link(k, v) for k, v in (h.get('links') or {}).items() if v]
    o += [' | '.join(contact), '']
    for sec in cv.get('sections', []):
        if not sec.get('items'):
            continue
        o += [f"## {sec['name']}", '']
        for item in sec['items']:
            if sec.get('type') == 'experience':
                o += [f"**{item.get('title','')}**",
                      f"*{' | '.join(x for x in [item.get('org'), item.get('period')] if x)}*", '']
                if item.get('framing'):
                    o += [item['framing'], '']
                o += [f"- {b['text']}" for b in item.get('bullets', [])] + ['']
            elif sec.get('type') in ('para', 'band'):
                o += [item['text'], '']
            else:
                o.append(f"- {item['text']}")
        o.append('')
    return '\n'.join(o)


def to_ats_text(cv):
    """What a naive parser sees. Verify this before shipping anywhere important."""
    h = cv.get('header', {})
    contact = [x for x in h.get('contact', []) if x]
    contact += [_display_link(k, v) for k, v in (h.get('links') or {}).items() if v]
    o = [h.get('name', ''), h.get('headline', ''), ' | '.join(contact), '']
    for sec in cv.get('sections', []):
        if not sec.get('items'):
            continue
        o += ['', sec['name'].upper(), '']
        for item in sec['items']:
            if sec.get('type') == 'experience':
                o += [item.get('title', ''),
                      ' | '.join(x for x in [item.get('org'), item.get('period')] if x)]
                if item.get('framing'):
                    o.append(item['framing'])
                o += [f"- {b['text']}" for b in item.get('bullets', [])]
            else:
                o.append(item['text'])
    return '\n'.join(o)


def to_pdf(docx_path, pdf_path=None):
    """Convert with an available verified office engine."""
    return to_pdfs([(docx_path, pdf_path)])[0]


def to_pdfs(documents):
    """Convert multiple DOCX files in one office-engine session.

    Each result is either the final PDF path or ``(None, reason)``. Batching the
    CV and cover letter avoids paying the office engine's startup cost twice.
    """
    jobs = []
    for docx_path, pdf_path in documents:
        final = pdf_path or os.path.splitext(docx_path)[0] + '.pdf'
        jobs.append((os.path.abspath(docx_path), os.path.abspath(final),
                     os.path.abspath(final + '.building.pdf')))

    word_ok, _ = _word_pdf_capability()
    if word_ok:
        return _to_pdfs_word(jobs)
    office = _libreoffice_path()
    if office:
        return _to_pdfs_libreoffice(jobs, office)
    _, reason = pdf_capability()
    return [(None, reason) for _ in jobs]


def _to_pdfs_word(jobs):
    """Use one Microsoft Word COM session for all requested documents."""
    def psq(value):
        return os.path.abspath(value).replace("'", "''")

    actions = ''.join(
        f"$d=$w.Documents.Open('{psq(source)}',$false,$true);"
        f"$d.ExportAsFixedFormat('{psq(pending)}',17);"
        "$d.Close($false);[void][Runtime.InteropServices.Marshal]::ReleaseComObject($d);$d=$null;"
        for source, _, pending in jobs)
    ps = (
        "$ErrorActionPreference='Stop';"
        "$w=$null;$d=$null;try{"
        "$w=New-Object -ComObject Word.Application;$w.Visible=$false;"
        "$w.DisplayAlerts=0;"
        + actions +
        "}finally{"
        "if($d -ne $null){$d.Close($false);[void][Runtime.InteropServices.Marshal]::ReleaseComObject($d)};"
        "if($w -ne $null){$w.Quit();[void][Runtime.InteropServices.Marshal]::ReleaseComObject($w)};"
        "[GC]::Collect();[GC]::WaitForPendingFinalizers()}"
    )
    try:
        for _, _, pending in jobs:
            if os.path.exists(pending):
                os.remove(pending)
        r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            reason = (r.stderr or 'unknown error').strip()[:300]
            return [(None, 'Microsoft Word: ' + reason) for _ in jobs]
        results = []
        for _, final, pending in jobs:
            if not os.path.exists(pending):
                results.append((None, 'Word did not create the expected PDF'))
                continue
            with open(pending, 'rb') as stream:
                valid = stream.read(5) == b'%PDF-'
            if not valid:
                results.append((None, 'Word returned a file without a PDF signature'))
                continue
            os.replace(pending, final)
            results.append(final)
        return results
    except Exception as e:
        return [(None, 'Microsoft Word: ' + str(e)[:300]) for _ in jobs]
    finally:
        for _, _, pending in jobs:
            if os.path.exists(pending):
                try:
                    os.remove(pending)
                except OSError:
                    pass


def _to_pdfs_libreoffice(jobs, office):
    """Use one isolated headless LibreOffice process for all documents."""
    basenames = [os.path.splitext(os.path.basename(source))[0].casefold()
                 for source, _, _ in jobs]
    if len(basenames) != len(set(basenames)):
        reason = 'LibreOffice batch contains duplicate DOCX base names'
        return [(None, reason) for _ in jobs]
    try:
        with tempfile.TemporaryDirectory(prefix='joblooper-libreoffice-') as temp:
            out_dir = os.path.join(temp, 'out')
            profile = os.path.join(temp, 'profile')
            os.makedirs(out_dir)
            command = [
                office, f'-env:UserInstallation={Path(profile).as_uri()}',
                '--headless', '--convert-to', 'pdf', '--outdir', out_dir,
                *[source for source, _, _ in jobs],
            ]
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                reason = (result.stderr or result.stdout or 'unknown error').strip()[:300]
                return [(None, 'LibreOffice: ' + reason) for _ in jobs]
            converted = []
            for source, final, _ in jobs:
                candidate = os.path.join(
                    out_dir, os.path.splitext(os.path.basename(source))[0] + '.pdf')
                if not os.path.isfile(candidate):
                    converted.append((None, 'LibreOffice did not create the expected PDF'))
                    continue
                with open(candidate, 'rb') as stream:
                    valid = stream.read(5) == b'%PDF-'
                if not valid:
                    converted.append((None, 'LibreOffice returned a file without a PDF signature'))
                    continue
                os.makedirs(os.path.dirname(final), exist_ok=True)
                os.replace(candidate, final)
                converted.append(final)
            return converted
    except Exception as error:
        return [(None, 'LibreOffice: ' + str(error)[:300]) for _ in jobs]


def _word_pdf_capability():
    if os.name != 'nt':
        return False, 'Microsoft Word automation is Windows-only'
    if not shutil.which('powershell'):
        return False, 'Windows PowerShell was not found'
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r'Word.Application\CLSID'):
            pass
    except (ImportError, OSError):
        return False, 'Microsoft Word automation is not registered'
    return True, 'Microsoft Word automation detected'


def _libreoffice_path():
    return shutil.which('libreoffice') or shutil.which('soffice')


def pdf_capability():
    """Return available PDF capability without launching an office engine."""
    word_ok, word_detail = _word_pdf_capability()
    if word_ok:
        return True, word_detail + '; each build verifies PDF output'
    office = _libreoffice_path()
    if office:
        return True, f'LibreOffice detected at {office}; each build verifies PDF output'
    return False, ('DOCX supported; PDF requires Microsoft Word on Windows or '
                   'LibreOffice on Windows, macOS or Linux')


def pdf_pages(pdf_path):
    """Page count of a rendered PDF. Returns None if it cannot be determined.

    Counting /Type /Page objects is crude but exact enough: the alternative is
    trusting a words-per-page estimate that cannot see section headings or
    line wrapping.
    """
    try:
        data = open(pdf_path, 'rb').read()
    except OSError:
        return None
    n = len(re.findall(rb'/Type\s*/Page[^s]', data))
    return n or None
