"""Dashboard projection, privacy boundary and local-server invariants."""
import base64
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from types import SimpleNamespace


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'examples', 'starter')
sys.path.insert(0, ROOT)

import jl
from core import (codex_bridge, dashboard, dashboard_actions, dashboard_runtime,
                  feedback, integrity, job_fetch, store, truth_review, vec)


def fetch(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.headers, response.read()


def post(url, token, payload, origin=None):
    body = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        url, data=body, method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Joblooper-Token': token,
            'Cookie': f'{dashboard.SESSION_COOKIE}={token}',
            'Origin': origin or url.split('/api/', 1)[0],
        })
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.headers, json.loads(
            response.read().decode('utf-8'))


class FakeBridge:
    def __init__(self):
        self.tasks = {}

    def status(self):
        return {'available': True, 'connected': False, 'active_tasks': 0,
                'error': None, 'integration': 'codex_app_server',
                'approval_mode': 'user'}

    def start_turn(self, message, intent='ask', job_id=None):
        task = {'id': 'TASK-FAKE', 'status': 'completed', 'job_id': job_id,
                'intent': intent, 'user': message, 'assistant': 'verified reply',
                'events': [], 'pending': None, 'error': None}
        self.tasks[task['id']] = task
        return task

    def task(self, task_id):
        return self.tasks.get(task_id)

    def respond(self, task_id, decision=None, answers=None):
        return self.tasks[task_id]

    def close(self):
        pass


class DialogText(HTMLParser):
    """Collect only text a person can read inside native dialogs."""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'dialog':
            self.depth += 1

    def handle_endtag(self, tag):
        if tag == 'dialog' and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.depth and data.strip():
            self.parts.append(data.strip())


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='joblooper-dashboard-') as data:
        shutil.copytree(FIXTURE, data, dirs_exist_ok=True)
        store.configure(data)
        vec.reset_caches()

        snapshot = dashboard.build_snapshot()
        encoded = json.dumps(snapshot, ensure_ascii=False)
        checks.append(('snapshot schema and privacy contract are explicit',
                       snapshot.get('_schema') == 'joblooper.dashboard.v1'
                       and snapshot['privacy']['mode'] == 'LOCAL_ONLY'
                       and snapshot['privacy']['bind'] == '127.0.0.1'
                       and snapshot['privacy']['dashboard_analytics'] is False
                       and snapshot['privacy']['codex_processing']
                       == 'only_after_explicit_user_turn'))
        checks.append(('starter job is visible as actionable work',
                       snapshot['kpis']['jobs'] == 1
                       and snapshot['kpis']['in_progress'] == 1
                       and snapshot['jobs'][0]['phase'] == 'captured'))
        checks.append(('attention queue exposes a typed action instead of a dead-end warning',
                       snapshot['attention'][0]['kind'] == 'preflight'
                       and snapshot['attention'][0]['route'] == 'preflight'
                       and snapshot['attention'][0]['cta'] == 'Review decisions'
                       and bool(snapshot['attention'][0]['detail'])))
        app_script = store.read_text(os.path.join(ROOT, 'dashboard', 'app.js'))
        foundation_script = store.read_text(os.path.join(
            ROOT, 'dashboard', 'foundation.js'))
        display_script = app_script + '\n' + foundation_script
        page_source = store.read_text(os.path.join(ROOT, 'dashboard', 'index.html'))
        dashboard_css = store.read_text(os.path.join(ROOT, 'dashboard', 'styles.css'))
        active_job = snapshot['jobs'][0]
        checks.append(('active job projection preserves durable workspace state',
                       bool(active_job['updated_at'])
                       and isinstance(active_job['feedback_items'], list)
                       and len(active_job['touchpoints']) == 9
                       and active_job['touchpoints'][0]['status'] == 'complete'
                       and active_job['touchpoints'][1]['status'] == 'complete'
                       and active_job['touchpoints'][2]['status'] == 'current'
                       and active_job['workflow']['captured'] is True
                       and active_job['workflow']['preflight'] is False
                       and active_job['workflow']['preflight_questions'] is False
                       and active_job['outputs']['cv'] is False
                       and active_job['outputs']['letter'] is False))
        question_path = os.path.join(
            store.job_dir(active_job['id']), 'PRE-GENERATION-QUESTIONS.md')
        store.write_text(question_path, '# PRE-GENERATION REVIEW\n\n## REQ-1\n\nMaterial question.')
        interrupted_snapshot = dashboard.build_snapshot()
        interrupted_job = interrupted_snapshot['jobs'][0]
        checks.append(('interrupted preparation exposes its durable partial output',
                       interrupted_job['workflow']['preflight'] is False
                       and interrupted_job['workflow']['preflight_questions'] is True
                       and interrupted_job['next_action']
                       == 'Review the prepared fit decisions before CV planning'
                       and any(item['id'] == 'work-preflight_questions'
                               and item['group'] == 'Review'
                               and item['href']
                               for item in interrupted_job['artifacts'])))
        os.unlink(question_path)
        checks.append(('working applications appear before portfolio analytics',
                       page_source.index('id="active-workspace"')
                       < page_source.index('id="overview"')
                       and page_source.index('id="active-job-list"')
                       < page_source.index('id="kpi-grid"')))
        small_rem_values = [float(value) for value in re.findall(
            r'font-size:\s*(\.[0-9]+)rem', dashboard_css)]
        checks.append(('dashboard type and mobile controls remain legible without overflow',
                       small_rem_values and min(small_rem_values) >= 0.75
                       and 'Inter,' not in dashboard_css
                       and 'grid-template-columns: repeat(3, minmax(0, 1fr))'
                       in dashboard_css
                       and '#new-job-button { grid-column: 1; grid-row: 2;'
                       in dashboard_css))
        checks.append(('strict CSP needs no inline style exception',
                       'style=' not in app_script
                       and 'style=' not in foundation_script
                       and 'style=' not in page_source
                       and "style-src 'self'" in store.read_text(
                           os.path.join(ROOT, 'core', 'dashboard.py'))))
        checks.append(('dashboard and docs use the governed Joblooper brand promise',
                       'Tailor every application.' in page_source
                       and 'Invent nothing.' in page_source
                       and os.path.isfile(os.path.join(
                           ROOT, 'references', 'brand.md'))
                       and 'assets/app-mark.svg' in store.read_text(
                           os.path.join(ROOT, 'README.md'))))
        checks.append(('active workspace exposes every required applicant touchpoint',
                       'function renderActiveWorkspace()' in app_script
                       and 'job.touchpoints' in app_script
                       and 'status: item.status' in app_script
                       and 'function workflowProgress(job)' in app_script
                       and 'data-active-action="evidence"' in app_script
                       and 'data-active-action="cautions"' in app_script
                       and 'data-active-action="artifacts"' in app_script
                       and 'data-active-action="feedback"' in app_script
                       and 'Open captured JD' in app_script
                       and 'CV and letter not created' in app_script
                       and 'not an ATS score' in app_script))
        # A re-saved advert page says the same thing. Withdrawing an approved CV
        # decision over line endings trains users to ignore real refresh alerts.
        jd_record = store.read_json(
            os.path.join(store.job_dir(active_job['id']), 'jd.json'))
        raw_advert = store.read_text(
            os.path.join(store.job_dir(active_job['id']), 'jd.raw.md'))
        jd_record['raw_sha256'] = store.sha256_text(raw_advert)
        jd_record['raw_normalized_sha256'] = store.sha256_advert(raw_advert)
        cosmetic = {
            'CRLF line endings': raw_advert.replace('\n', '\r\n'),
            'trailing whitespace': '\n'.join(
                line + '   ' for line in raw_advert.split('\n')),
            'collapsed blank lines': raw_advert.replace('\n\n', '\n\n\n'),
            'leading and trailing padding': '\n\n' + raw_advert + '\n\n',
        }
        cosmetic_ok = all(
            dashboard._analysis_state(active_job['id'], jd_record, text)[0]['current']
            for text in cosmetic.values())
        emptied = '\n'.join(line for line in raw_advert.split('\n')
                            if not line.strip().startswith('-'))
        semantic_state, _ = dashboard._analysis_state(
            active_job['id'], jd_record, emptied)
        checks.append(('a cosmetically re-saved advert does not withdraw the CV decision',
                       cosmetic_ok
                       and dashboard._analysis_state(
                           active_job['id'], jd_record, raw_advert)[0]['current']
                       and semantic_state['current'] is False
                       and semantic_state['detected_count']
                       < semantic_state['stored_count']))
        # Improving a gate rule must not make a stored advert read as changed:
        # match_jd re-derives hard_gate and gate_type on every run, so a refresh
        # could not alter a single word of the advert.
        reclassified = {
            **jd_record,
            'requirements': [{**row,
                              'hard_gate': not row.get('hard_gate'),
                              'gate_type': 'behavioural'}
                             for row in jd_record.get('requirements') or []],
        }
        checks.append(('an engine taxonomy change does not demand a JD refresh',
                       dashboard._analysis_state(
                           active_job['id'], reclassified, raw_advert)[0]['current']))
        dropped = {**jd_record,
                   'requirements': (jd_record.get('requirements') or [])[:-1]}
        checks.append(('a genuinely changed advert still demands a refresh',
                       (jd_record.get('requirements') or [])
                       and not dashboard._analysis_state(
                           active_job['id'], dropped, raw_advert)[0]['current']))

        crlf_advert = raw_advert.replace('\n', '\r\n')
        checks.append(('advert normalization keeps byte-exact provenance separate',
                       store.sha256_text(raw_advert) != store.sha256_text(crlf_advert)
                       and store.sha256_advert(raw_advert)
                       == store.sha256_advert(crlf_advert)))
        checks.append(('internal cautions are visible before employer document review',
                       'data-tab="cautions"' in page_source
                       and page_source.index('data-tab="cautions"')
                       < page_source.index('data-tab="review"')
                       and 'function drawerCautions(job)' in app_script
                       and 'Previous CV decision withdrawn' in app_script
                       and "'/api/actions/refresh-analysis'" in app_script))
        checks.append(('priority and continue controls execute their displayed action',
                       '<button class="hero-action" id="primary-action"' in page_source
                       and "$('#primary-action').addEventListener('click'" in app_script
                       and "if (action === 'preflight')" in app_script
                       and "if (action === 'advert-review')" in app_script
                       and app_script.index('!workflow.advert_confirmed')
                       < app_script.index('!workflow.preflight')
                       and 'function openPreflight(job)' in app_script
                       and "'/api/actions/preflight'" in app_script
                       and 'function prepareApplication(job, source = null)' in app_script
                       and "'/api/actions/prepare'" in app_script))
        checks.append(('URL fallback binds the captured job to deterministic preflight',
                       'state.agentJob = captured[0]' in app_script
                       and 'await openPreflight(captured[0])' in app_script
                       and "['workspace', 'Open application workspace']" in app_script))
        # Users applying for jobs in a second language click past anything they
        # cannot parse quickly, which defeats a correct signal as surely as
        # hiding it. The place the product asks a person to think hardest was
        # the place it read most like a research paper.
        import re as _re
        dialog_parser = DialogText()
        dialog_parser.feed(page_source)
        dialog_copy = dialog_parser.parts
        dynamic_labels = _re.findall(r'>([^<>\n]+)<', display_script)
        visible_labels = _re.findall(r'<option value="[A-Z_]+">([^<]+)', page_source)
        internal_words = ('hypothesis', 'disposition', 'counterevidence',
                           'provenance', 'deterministic', 'artefact', 'digest',
                           'retention', 'retained plausible', 'evidence support')
        internal_pattern = _re.compile(
            r'\b(?:' + '|'.join(map(_re.escape, internal_words)) + r')s?\b',
            _re.IGNORECASE)
        checks.append(('every dialog and generated dashboard label avoids internal vocabulary',
                       bool(dialog_copy)
                       and not [text for text in dialog_copy
                                if internal_pattern.search(text)]
                       and not [text for text in dynamic_labels
                                if internal_pattern.search(text)]))
        checks.append(('cause and status choices read as ordinary English',
                       bool(visible_labels)
                       and not any(label.isupper() for label in visible_labels)
                       and not any(word in label.lower()
                                   for label in visible_labels
                                   for word in ('disposition', 'hypothesis'))))
        checks.append(('how sure you are is a choice, never a decimal to invent',
                       'name="confidence"><option' in page_source.replace(' ', '')
                       or ('<select name="confidence"' in page_source
                            and 'type="number"' not in page_source.split(
                                'name="confidence"')[1][:120])))
        historical = {
            'cause': 'DOMAIN_TRANSLATION', 'status': 'RETAINED_PLAUSIBLE',
            'confidence': 0.62,
            'summary': ('For future customer-embedded defence roles, preflight must '
                        'separate technical lifecycle fit from direct customer, regulatory, '
                        'localisation and succession-context fit, then ask for verified '
                        'evidence or flag the residual risk.'),
        }
        display = dashboard._reasoning_display(historical)
        checks.append(('old reasoning values keep their stored meaning but display plainly',
                       historical['status'] == 'RETAINED_PLAUSIBLE'
                       and historical['confidence'] == 0.62
                       and display['cause_label']
                       == 'My experience is in a different field'
                       and display['status_label']
                       == 'Saved concern · cause unconfirmed'
                       and display['confidence_label'] == 'Some supporting evidence'
                       and len(display['summary_display'].split()) <= 24
                       and not internal_pattern.search(display['summary_display'])
                       and 'item.summary_display' in app_script
                       and 'item.status_label' in app_script
                       and 'item.confidence_label' in app_script
                       and '% evidence support' not in app_script.lower()))
        checks.append(('Codex is told to write for the person, not the system',
                       'plain language' in codex_bridge.DEVELOPER_INSTRUCTIONS.lower()
                       and 'second language'
                       in codex_bridge.DEVELOPER_INSTRUCTIONS.lower()))

        checks.append(('preflight answers and artefact access are first-class dashboard controls',
                       'id="preflight-dialog"' in page_source
                       and 'id="agent-artifacts"' in page_source
                       and 'function submitPreflight(event)' in app_script
                       and 'function renderAgentArtifacts()' in app_script
                       and 'CV and cover letter have not been created yet' in app_script))
        checks.append(('failed Codex turns end thinking and expose safe recovery',
                       'CODEX TURN INTERRUPTED' in app_script
                       and 'No completed response was received' in app_script
                       and 'data-agent-recovery="resume"' in app_script
                       and 'function resumeInterruptedTurn()' in app_script
                       and 'repeat no completed mutation' in app_script
                       and 'state.taskPollFailures >= 3' in app_script))
        checks.append(('job-scoped generation requests use the durable prepare action',
                       'function composerIntent(message)' in app_script
                       and 'isPreparationRequest' in app_script
                       and 'prepareApplication(state.agentJob)' in app_script
                       and "state.agentJob ? 'auto' : 'ask'" in app_script
                       and 'composerIntent(message)' in app_script
                       and codex_bridge.resolve_intent(
                           'Using ground truth, tailor the CV for this role.',
                           'auto', active_job['id']) == 'prepare_application'
                       and codex_bridge.resolve_intent(
                           'What is the next gate?', 'auto', active_job['id']) == 'ask'
                       and codex_bridge.resolve_intent(
                           'Why was this rejection observed?',
                           'auto', active_job['id']) == 'outcome_review'))
        checks.append(('objections and applied reports keep their intended route',
                       all(codex_bridge.resolve_intent(message, 'auto', active_job['id'])
                           == 'feedback_discussion' for message in [
                               'Update the CV, you missed my evidence.',
                               'Do not generate my CV, this gap is incorrect.',
                               'I disagree with this rejection explanation.'])
                       and codex_bridge.resolve_intent('I applied to this job',
                           'auto', active_job['id']) == 'submission_help'))
        checks.append(('open browsers detect replacement and preserve job context',
                       'function monitorDashboardInstance()' in app_script
                       and 'health.instance_id !== state.serverInstanceId' in app_script
                       and "sessionStorage.setItem('joblooper-dashboard-context'" in app_script
                       and 'setInterval(monitorDashboardInstance, 4000)' in app_script))
        checks.append(('every declared attention route has a browser interaction state',
                       all(f"item.route === '{route}'" in app_script
                           for route in dashboard.ATTENTION_ROUTES)
                       and all(set(item) >= {
                           'id', 'kind', 'title', 'detail', 'cta', 'route', 'severity'}
                           for item in snapshot['attention'])))
        checks.append(('public API projection contains no filesystem paths',
                       '"_path"' not in encoded and os.path.abspath(data) not in encoded))
        checks.append(('blocked URL journey automatically exposes manual capture',
                       'function openManualIntake(message)' in app_script
                       and "if (!dialog.open) dialog.showModal()" in app_script
                       and 'const started = await startAgentTurn(' in app_script
                       and 'if (!started)' in app_script))
        checks.append(('coverage is labelled as evidence, never an ATS score',
                       'not an ATS or hiring score' in snapshot['jobs'][0]['coverage_note']))
        checks.append(('captured JD is directly addressable through registry',
                       any(row.get('href') and row.get('group') == 'Source'
                           for row in snapshot['jobs'][0]['artifacts'])))

        original_truth_check = integrity.check_truth
        try:
            integrity.check_truth = lambda: (
                ['source SRC-FIXTURE: SHA-256 mismatch'], [], {})
            blocked_truth = dashboard.build_snapshot()
        finally:
            integrity.check_truth = original_truth_check
        truth_attention = next(
            item for item in blocked_truth['attention']
            if item['kind'] == 'truth_integrity')
        checks.append(('truth integrity failure is explicit and directly actionable',
                       blocked_truth['truth']['ready'] is False
                       and blocked_truth['truth']['errors'] == 1
                       and truth_attention['route'] == 'truth_integrity'
                       and truth_attention['cta'] == 'Review options'
                       and 'SHA-256 mismatch' in truth_attention['detail']))
        checks.append(('integrity attention is deterministic before optional Codex use',
                       "item.route === 'truth_integrity'" in app_script
                       and "$('#truth-integrity-dialog').showModal()" in app_script
                       and "'integrity_review'" in app_script
                       and 'Bounded read-only diagnosis' in app_script))

        comment = feedback.record(
            snapshot['jobs'][0]['id'], 'WORKFLOW',
            'Expose a direct resolution control in the task queue.', 'test-user')
        feedback_snapshot = dashboard.build_snapshot()
        checks.append(('open feedback queue item carries the exact resolvable record',
                       feedback_snapshot['attention'][0]['route'] == 'feedback'
                       and feedback_snapshot['jobs'][0]['open_feedback'][0]['id']
                       == comment['id']
                       and bool(feedback_snapshot['jobs'][0]['open_feedback'][0]['note'])))
        feedback.resolve(
            snapshot['jobs'][0]['id'], comment['id'], 'ADOPTED',
            'Added the governed resolution dialog.',
            'Dashboard regression covers the route and record.')
        resolved_snapshot = dashboard.build_snapshot()
        resolved_comment = resolved_snapshot['jobs'][0]['feedback_items'][0]
        checks.append(('resolved comments remain visible with decision evidence',
                       resolved_comment['id'] == comment['id']
                       and resolved_comment['status'] == 'ADOPTED'
                       and bool(resolved_comment['implementation'])
                       and bool(resolved_comment['validation'])
                       and 'function drawerFeedback(job)' in app_script))

        thread_calls = []
        first_bridge = codex_bridge.CodexBridge()
        first_bridge._request = lambda method, params: (
            thread_calls.append(method) or {'thread': {'id': 'thread-fixture'}})
        first_id = first_bridge._thread('fixture-job')
        resumed_bridge = codex_bridge.CodexBridge()
        resumed_bridge._request = lambda method, params: (
            thread_calls.append(method) or {'thread': {'id': params['threadId']}})
        resumed_id = resumed_bridge._thread('fixture-job')
        checks.append(('private per-job Codex context resumes after dashboard restart',
                       first_id == resumed_id == 'thread-fixture'
                       and thread_calls == ['thread/start', 'thread/resume']))

        turn_calls = []
        profile_bridge = codex_bridge.CodexBridge()
        profile_bridge._start = lambda: None
        profile_bridge._thread = lambda key: 'thread-profile'
        profile_bridge._request = lambda method, params: (
            turn_calls.append((method, params))
            or {'turn': {'id': 'turn-profile', 'status': 'inProgress'}})
        profile_task = profile_bridge.start_turn(
            'Explain source SRC-FIXTURE: SHA-256 mismatch',
            'integrity_review')
        turn_params = turn_calls[-1][1]
        checks.append(('small integrity diagnosis has an explicit lean execution profile',
                       profile_task['effort'] == 'low'
                       and profile_task['scope'] == 'bounded read-only diagnosis'
                       and profile_task['read_only'] is True
                       and turn_params['effort'] == 'low'
                       and turn_params['summary'] == 'concise'
                       and turn_params['sandboxPolicy']['type'] == 'readOnly'
                       and 'Do not compare image pixels or containers'
                       in turn_params['input'][0]['text']))
        profile_bridge._notification({
            'method': 'item/completed',
            'params': {'threadId': 'thread-profile',
                       'item': {'type': 'agentMessage', 'text': 'Bounded answer'}},
        })
        profile_bridge._notification({
            'method': 'turn/completed',
            'params': {'threadId': 'thread-profile',
                       'turn': {'id': 'turn-profile', 'status': 'completed'}},
        })
        completed_profile = profile_bridge.task(profile_task['id'])
        performance = profile_bridge.status()['performance']
        checks.append(('Codex latency and work are exposed as operational evidence',
                       completed_profile['status'] == 'completed'
                       and completed_profile['duration_ms'] >= 0
                       and completed_profile['work_items'] == 1
                       and completed_profile['finished_at']
                       and performance['completed_turns'] == 1
                       and performance['last_duration_ms'] is not None))

        failed_calls = []
        failed_bridge = codex_bridge.CodexBridge()
        failed_bridge._start = lambda: None
        failed_bridge._thread = lambda key: 'thread-failed'
        failed_bridge._request = lambda method, params: (
            failed_calls.append((method, params))
            or {'turn': {'id': 'turn-failed', 'status': 'inProgress'}})
        failed_task = failed_bridge.start_turn(
            'Tailor the CV from governed truth.', 'prepare_application',
            snapshot['jobs'][0]['id'])
        failed_bridge._notification({
            'method': 'turn/completed',
            'params': {'threadId': 'thread-failed', 'turn': {
                'id': 'turn-failed', 'status': 'failed',
                'error': {'message': 'stream disconnected before completion'},
            }},
        })
        failed_task = failed_bridge.task(failed_task['id'])
        checks.append(('interrupted application turn preserves recovery inputs',
                       failed_task['status'] == 'failed'
                       and failed_task['intent'] == 'prepare_application'
                       and failed_task['job_id'] == snapshot['jobs'][0]['id']
                       and failed_task['user'] == 'Tailor the CV from governed truth.'
                       and 'stream disconnected' in failed_task['error']))

        store.write_jsonl(store.data_p('index', 'applications.jsonl'), [{
            'app_id': snapshot['jobs'][0]['id'],
            'company': 'Example Aerospace',
            'role': 'Senior Systems Engineer',
            'status': 'applied',
        }])
        applied = dashboard.build_snapshot()
        # Age alone is not evidence of ghosting or a compulsory learning task.
        import datetime as _dt

        def _silence_kinds(days):
            store.write_jsonl(store.data_p('index', 'applications.jsonl'), [{
                'app_id': snapshot['jobs'][0]['id'], 'company': 'Example Aerospace',
                'role': 'Senior Systems Engineer', 'status': 'applied',
                'applied': (_dt.date.today() - _dt.timedelta(days=days)).isoformat(),
            }])
            return [item['kind'] for item in dashboard.build_snapshot()['attention']]

        quiet = _silence_kinds(29)
        overdue = _silence_kinds(90)
        checks.append(('waiting alone never creates a compulsory outcome task',
                       'silent_application' not in quiet
                       and 'silent_application' not in overdue))
        checks.append(('a silent application is never auto-recorded as ghosted',
                       all(row.get('status') == 'applied'
                           for row in store.applications())))

        checks.append(('submitted and awaiting-response work remains visible without a false task',
                       applied['jobs'][0]['phase'] == 'applied'
                       and applied['kpis']['submitted'] == 1
                       and applied['kpis']['in_progress'] == 0
                       and 'applied' not in applied['lifecycle']['active_phases']
                       and not applied['attention']))
        try:
            dashboard_actions.refresh_job_analysis(snapshot['jobs'][0]['id'])
            submitted_refresh_refused = False
        except ValueError as error:
            submitted_refresh_refused = 'submitted application history is immutable' in str(error)
        checks.append(('submitted history refuses JD refresh at the governed CLI boundary',
                       submitted_refresh_refused))
        store.write_jsonl(store.data_p('index', 'applications.jsonl'), [])

        bridge = FakeBridge()
        server = dashboard.create_server(0, quiet=True, bridge=bridge)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_address[1]}'
        try:
            duplicate_refused = False
            try:
                duplicate = dashboard.create_server(server.server_address[1], quiet=True,
                                                    bridge=FakeBridge())
            except OSError:
                duplicate_refused = True
            else:
                duplicate.server_close()
            checks.append(('one loopback port cannot serve competing dashboard instances',
                           duplicate_refused))

            status, headers, page = fetch(base + '/')
            checks.append(('local UI ships without third-party runtime dependencies',
                           status == 200 and b'Evidence-backed applications' in page
                           and b'truth-integrity-dialog' in page
                           and headers.get('Content-Security-Policy') is not None
                           and headers.get('Cache-Control') == 'private, no-cache'
                           and bool(headers.get('ETag'))))
            status, static_headers, _ = fetch(base + '/styles.css')
            static_etag = static_headers.get('ETag')
            static_revalidated = False
            try:
                fetch(base + '/styles.css', {'If-None-Match': static_etag})
            except urllib.error.HTTPError as error:
                static_revalidated = error.code == 304
            checks.append(('unchanged static assets revalidate without a full response',
                           status == 200 and bool(static_etag)
                           and static_headers.get('Cache-Control') == 'private, no-cache'
                           and static_revalidated))

            private_read_refused = False
            try:
                fetch(base + '/api/dashboard')
            except urllib.error.HTTPError as error:
                private_read_refused = error.code == 403
            checks.append(('private dashboard reads require the local session',
                           private_read_refused))
            rebound_refused = False
            try:
                fetch(base + '/api/session', {'Host': 'attacker.example'})
            except urllib.error.HTTPError as error:
                rebound_refused = error.code == 421
            checks.append(('unrecognised Host headers cannot reach the local dashboard',
                           rebound_refused))
            status, headers, body = fetch(base + '/api/session')
            session = json.loads(body.decode('utf-8'))
            session_cookie = (headers.get('Set-Cookie') or '').split(';', 1)[0]
            checks.append(('session advertises guarded interaction capabilities',
                           status == 200 and session['csrf_token']
                           and session['instance_id']
                           and session['dashboard_version']
                           and session['capabilities']['intake'] is True
                           and session['capabilities']['url_intake'] is True
                           and session['capabilities']['jd_analysis_refresh'] is True
                           and session['capabilities']['structured_preflight'] is True
                           and session['capabilities']['deterministic_prepare'] is True
                           and session['capabilities']['deterministic_build_recovery'] is True
                           and session['capabilities']['feedback_resolution'] is True
                           and session['capabilities']['submission_update'] is True
                           and session['capabilities']['record_outcome'] is True
                           and session['capabilities']['agent_chat'] is True
                           and session['capabilities']['external_portal_submission'] is False
                           and session_cookie.startswith(
                               dashboard.SESSION_COOKIE + '=')
                           and 'HttpOnly' in headers.get('Set-Cookie')
                           and 'SameSite=Strict' in headers.get('Set-Cookie')))

            private_headers = {'Cookie': session_cookie}
            status, headers, body = fetch(
                base + '/api/dashboard', private_headers)
            api = json.loads(body.decode('utf-8'))
            checks.append(('dashboard API returns the governed projection',
                           status == 200 and api['kpis']['jobs'] == 1
                           and headers.get('Cache-Control') == 'no-store'))

            status, headers, body = fetch(
                base + '/api/preflight?job=' + urllib.parse.quote(api['jobs'][0]['id']),
                private_headers)
            preflight_view = json.loads(body.decode('utf-8'))
            checks.append(('preflight endpoint returns exact actionable decisions',
                           status == 200 and preflight_view['questions']
                           and preflight_view['complete'] is False
                           and all(row['kind'] == 'KNOWN_GAP'
                                   for row in preflight_view['questions'])))
            refused_answers = {
                row['id']: ({'decision': 'ADD_NEW_EVIDENCE',
                             'note': 'A new certificate should be reviewed for this requirement.'}
                            if index == 0
                            else 'PROCEED_WITH_RECORDED_GAP')
                for index, row in enumerate(preflight_view['questions'])}
            status, headers, paused_preflight = post(
                base + '/api/actions/preflight', session['csrf_token'], {
                    'job_id': api['jobs'][0]['id'], 'answers': refused_answers,
                })
            first_question = preflight_view['questions'][0]
            status_issue, headers, issue_saved = post(
                base + '/api/actions/preflight-issue', session['csrf_token'], {
                    'job_id': api['jobs'][0]['id'],
                    'question_id': first_question['id'],
                    'note': 'A new certificate should be reviewed for this requirement.',
                    'issue_type': 'NEW_EVIDENCE',
                })
            feedback.resolve(
                api['jobs'][0]['id'], issue_saved['result']['item']['id'], 'REJECTED',
                'Fictional evidence request closed after endpoint verification.',
                'The exact current requirement and comment binding were verified.')
            accepted_answers = {
                row['id']: 'PROCEED_WITH_RECORDED_GAP'
                for row in preflight_view['questions']}
            status, headers, preflight_saved = post(
                base + '/api/actions/preflight', session['csrf_token'], {
                    'job_id': api['jobs'][0]['id'], 'answers': accepted_answers,
                })
            checks.append(('dashboard saves current-gap comments but blocks unreviewed new evidence',
                           status == 200 and status_issue == 200
                           and paused_preflight['result']['preflight']['complete'] is False
                           and paused_preflight['result']['preflight']['answers'][
                               first_question['id']]['note'].startswith('A new certificate')
                           and issue_saved['result']['item']['target_id'] == first_question['id']
                           and issue_saved['result']['item']['target_artifact'] == 'preflight'
                           and issue_saved['result']['item']['classification'] == 'FACTUAL_CORRECTION'
                           and preflight_saved['result']['preflight']['complete'] is True
                           and set(preflight_saved['result']['preflight']['answers'])
                           == set(accepted_answers)))

            jd_path = os.path.join(store.job_dir(api['jobs'][0]['id']), 'jd.json')
            incomplete_jd = store.read_json(jd_path)
            incomplete_jd['requirements'] = incomplete_jd['requirements'][:-1]
            store.write_json(jd_path, incomplete_jd)
            incomplete = dashboard.build_snapshot()['jobs'][0]
            status, headers, refreshed_analysis = post(
                base + '/api/actions/refresh-analysis', session['csrf_token'], {
                    'job_id': api['jobs'][0]['id'],
                })
            current = next(job for job in dashboard.build_snapshot()['jobs']
                           if job['id'] == api['jobs'][0]['id'])
            checks.append(('stale JD analysis is surfaced and refresh returns to preflight',
                           incomplete['cautions']['status'] == 'NEEDS_REFRESH'
                           and incomplete['cautions']['stored_requirement_count'] == 5
                           and incomplete['cautions']['detected_requirement_count'] == 6
                           and status == 200
                           and 'requirements  5 -> 6' in refreshed_analysis['result']['output']
                           and current['workflow']['analysis_current'] is True
                           and current['workflow']['preflight'] is False
                           and any(row.get('event') == 'JD_ANALYSIS_REFRESHED'
                                   for row in store.application_events())))

            status, headers, body = fetch(base + '/api/health')
            health = json.loads(body.decode('utf-8'))
            checks.append(('dashboard exposes a bounded local instance identity',
                           status == 200
                           and health['_schema'] == dashboard_runtime.HEALTH_SCHEMA
                           and health['product'] == 'Joblooper'
                           and health['port'] == server.server_address[1]
                           and 'shutdown_token' not in health))

            rejected = False
            try:
                post(base + '/api/agent/turn', 'wrong-token',
                     {'message': 'hello'})
            except urllib.error.HTTPError as error:
                rejected = error.code == 403
            except ConnectionAbortedError:
                # Some Windows endpoint-security stacks abort local rejected
                # requests before urllib receives the 403 response body.
                rejected = True
            checks.append(('state-changing requests require same-origin session token',
                           rejected and not bridge.tasks))

            status, headers, agent = post(
                base + '/api/agent/turn', session['csrf_token'],
                {'message': 'Audit this job', 'intent': 'ask',
                 'job_id': api['jobs'][0]['id']})
            checks.append(('dashboard can hand a scoped turn to the Codex bridge',
                           status == 202 and agent['task']['assistant'] == 'verified reply'))

            outcome_refused = False
            try:
                post(base + '/api/actions/outcome', session['csrf_token'], {
                    'job_id': api['jobs'][0]['id'], 'status': 'rejected',
                    'latency': 'under_24h',
                })
            except urllib.error.HTTPError as error:
                outcome_refused = error.code == 400
            checks.append(('outcome capture refuses an unverified submission record',
                           outcome_refused))

            update_calls = []
            original_update = dashboard_actions.update_submission
            try:
                dashboard_actions.update_submission = lambda *args: (
                    update_calls.append(args) or {'ok': True, 'output': 'updated'})
                status, headers, update = post(
                    base + '/api/actions/update-submission', session['csrf_token'], {
                        'job_id': api['jobs'][0]['id'],
                        'applied_date': '2026-08-20', 'channel': 'portal',
                        'screening_unavailable': True,
                    })
            finally:
                dashboard_actions.update_submission = original_update
            checks.append(('attention record editor reaches one allowlisted backend action',
                           status == 200 and update['result']['output'] == 'updated'
                           and update_calls
                           and update_calls[0][0] == api['jobs'][0]['id']
                           and update_calls[0][1] == '2026-08-20'
                           and update_calls[0][4] is True))

            resolution_calls = []
            original_resolution = dashboard_actions.resolve_feedback
            try:
                dashboard_actions.resolve_feedback = lambda *args: (
                    resolution_calls.append(args) or
                    {'ok': True, 'output': 'resolved'})
                status, headers, resolved = post(
                    base + '/api/actions/resolve-feedback', session['csrf_token'], {
                        'job_id': api['jobs'][0]['id'], 'feedback_id': 'F0001',
                        'status': 'adopted',
                        'implementation': 'Applied the requested change.',
                        'validation': 'Checked against the exact presentation.',
                    })
            finally:
                dashboard_actions.resolve_feedback = original_resolution
            checks.append(('feedback attention route reaches explicit resolution',
                           status == 200
                           and resolved['result']['output'] == 'resolved'
                           and resolution_calls[0][1:] == (
                               'F0001', 'adopted',
                               'Applied the requested change.',
                               'Checked against the exact presentation.')))
            try:
                dashboard_actions.resolve_feedback(
                    api['jobs'][0]['id'], '../F0001', 'adopted',
                    'Applied the requested change.',
                    'Checked against the exact presentation.')
                unsafe_feedback_id_refused = False
            except ValueError:
                unsafe_feedback_id_refused = True
            checks.append(('feedback resolution refuses an invented record identifier',
                           unsafe_feedback_id_refused))

            status, headers, intake = post(
                base + '/api/actions/ingest', session['csrf_token'], {
                    'company': 'Fixture Flight', 'title': 'Integration Manager',
                    'url': 'https://example.com/jobs/99887766',
                    'jd': 'Requirements\n- Lead avionics integration and acceptance.',
                })
            refreshed = dashboard.build_snapshot()
            checks.append(('pasted JD follows the deterministic intake path end to end',
                           status == 200 and intake['result']['job_id'] == 'fixture-flight--99887766'
                           and any(job['id'] == 'fixture-flight--99887766'
                                   for job in refreshed['jobs'])))

            original_fetch = job_fetch.fetch
            try:
                job_fetch.fetch = lambda url: {
                    'url': 'https://careers.url-route.example/jobs/77889911',
                    'company': 'URL Route Aerospace',
                    'title': 'Avionics Assurance Lead',
                    'jd': ('Lead avionics assurance, requirements and verification across '
                           'airborne systems. Own qualification evidence, configuration '
                           'control and certification coordination with engineering teams. ' * 3),
                    'extractor': 'json_ld_jobposting',
                    'characters': 558,
                }
                status, headers, url_intake = post(
                    base + '/api/actions/ingest-url', session['csrf_token'],
                    {'url': 'https://short.example/77889911'})
            finally:
                job_fetch.fetch = original_fetch
            refreshed = dashboard.build_snapshot()
            checks.append(('URL-only browser route captures the exact extracted advert',
                           status == 200
                           and url_intake['result']['job_id']
                           == 'url-route-aerospace--77889911'
                           and url_intake['result']['extraction']['requested_url']
                           == 'https://short.example/77889911'
                           and any(job['id'] == 'url-route-aerospace--77889911'
                                   for job in refreshed['jobs'])))

            source = next(row for row in api['jobs'][0]['artifacts']
                          if row.get('href') and row.get('group') == 'Source')
            status, headers, body = fetch(base + source['href'], private_headers)
            checks.append(('allowlisted artefact endpoint serves a real source file',
                           status == 200 and bool(body)
                           and headers.get('X-Content-Type-Options') == 'nosniff'))

            blocked = False
            try:
                fetch(base + '/artifact?job=..%2F..&id=profile', private_headers)
            except urllib.error.HTTPError as error:
                blocked = error.code == 404
            checks.append(('unregistered path traversal cannot read files', blocked))

            screening_path = dashboard_actions._screening_file({
                'name': 'portal-answers.txt',
                'base64': base64.b64encode(b'fictional answer evidence').decode('ascii'),
            })
            try:
                checks.append(('screening evidence upload is bounded and decoded exactly',
                               store.read_text(screening_path)
                               == 'fictional answer evidence'))
            finally:
                os.unlink(screening_path)
            with tempfile.TemporaryDirectory(prefix='joblooper-upload-cleanup-') as upload_dir:
                previous_tempdir = tempfile.tempdir
                tempfile.tempdir = upload_dir
                try:
                    try:
                        dashboard_actions._screening_files([
                            {
                                'name': 'portal-answers.txt',
                                'base64': base64.b64encode(b'valid first file').decode('ascii'),
                            },
                            {'name': 'blocked.exe', 'base64': 'eA=='},
                        ])
                        invalid_batch_refused = False
                    except ValueError:
                        invalid_batch_refused = True
                    checks.append(('failed evidence batches leave no temporary files',
                                   invalid_batch_refused and os.listdir(upload_dir) == []))
                finally:
                    tempfile.tempdir = previous_tempdir
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        restart_server = dashboard.create_server(0, quiet=True, bridge=FakeBridge())
        restart_port = restart_server.server_address[1]
        dashboard_runtime.register(restart_server)
        restart_thread = threading.Thread(
            target=restart_server.serve_forever, daemon=True)
        restart_thread.start()
        try:
            stopped = dashboard_runtime.stop_registered(restart_port)
            restart_thread.join(timeout=5)
            restart_server.server_close()
            replacement = dashboard.create_server(
                restart_port, quiet=True, bridge=FakeBridge())
            replacement.server_close()
            checks.append(('canonical relaunch stops only its authenticated prior instance',
                           stopped and not restart_thread.is_alive()
                           and not os.path.exists(dashboard_runtime.control_path())))
        finally:
            restart_server.shutdown()
            restart_server.server_close()

        structured_page = '''<!doctype html><html><head>
        <script type="application/ld+json">{
          "@context":"https://schema.org", "@type":"JobPosting",
          "title":"Lead Avionics Integration Engineer",
          "hiringOrganization":{"@type":"Organization","name":"Link Aerospace"},
          "description":"<p>Lead end-to-end avionics integration, verification and acceptance across complex aircraft programmes.</p><p>Own requirements, interface control, qualification evidence, supplier coordination and technical risk closure with customer engineering authorities.</p><p>Provide clear design reviews, configuration governance and flight-test support.</p>"
        }</script></head><body><h1>Unrelated navigation title</h1></body></html>'''
        extracted = job_fetch.extract(
            structured_page, 'https://careers.link-aero.example/jobs/44556677')
        checks.append(('URL extraction prefers exact JobPosting fields over page chrome',
                       extracted['company'] == 'Link Aerospace'
                       and extracted['title'] == 'Lead Avionics Integration Engineer'
                       and extracted['extractor'] == 'json_ld_jobposting'
                       and 'configuration governance' in extracted['jd']))
        blocked = False
        try:
            job_fetch.extract(
                '<html><title>Just a moment</title><body>Verify you are human</body></html>',
                'https://blocked.example/job')
        except job_fetch.FetchError:
            blocked = True
        checks.append(('blocked or verification pages are refused instead of inferred', blocked))
        private_refused = False
        try:
            job_fetch.fetch('http://127.0.0.1/private-job')
        except job_fetch.FetchError:
            private_refused = True
        checks.append(('URL intake refuses private-network targets', private_refused))
        malformed_port_refused = False
        try:
            job_fetch.fetch('https://careers.example:invalid/job')
        except job_fetch.FetchError as error:
            malformed_port_refused = 'invalid web port' in str(error)
        checks.append(('malformed URL ports produce a governed fallback error',
                       malformed_port_refused))

        original_fetch = job_fetch.fetch
        try:
            job_fetch.fetch = lambda url: extracted
            url_result = dashboard_actions.ingest_url(
                'https://careers.link-aero.example/jobs/44556677')
        finally:
            job_fetch.fetch = original_fetch
        checks.append(('URL-only intake reaches deterministic ingestion end to end',
                       url_result['job_id'] == 'link-aerospace--44556677'
                       and url_result['extraction']['requested_url'].endswith('/44556677')
                       and store.read_json(os.path.join(
                           store.job_dir(url_result['job_id']), 'jd.json'))['company']
                       == 'Link Aerospace'
                       and url_result['advert_review']['confirmed'] is False))
        dashboard_actions.confirm_advert(
            url_result['job_id'], 'Link Aerospace', 'Principal Integration Lead',
            'fixture-reviewer')
        checks.append(('new capture requires exact advert confirmation before preflight',
                       dashboard_actions.advert_review_state(
                           url_result['job_id'])['confirmed'] is True
                       and dashboard_actions.preflight_state(
                           url_result['job_id'])['company'] == 'Link Aerospace'))

    with tempfile.TemporaryDirectory(prefix='joblooper-dashboard-empty-') as empty:
        store.configure(empty)
        vec.reset_caches()
        snapshot = dashboard.build_snapshot()
        checks.append(('empty unonboarded workspace renders a safe empty state',
                       snapshot['kpis']['jobs'] == 0
                       and snapshot['jobs'] == []
                       and snapshot['truth']['ready'] is False))
        # JF-01: capture is not a first-run action. An unreadable workspace is
        # TRUTH_BLOCKED, never silently treated as ready, and either way the
        # dashboard must refuse to tailor against facts nobody has reviewed.
        entry = snapshot['entry']
        checks.append(('an unonboarded workspace never reports capture-ready truth',
                       entry['state'] in truth_review.ENTRY_STATES
                       and entry['state'] != 'TRUTH_READY'
                       and entry['can_capture'] is False
                       and bool(entry['reason']) and bool(entry['next_action'])))
        try:
            dashboard_actions.ingest(
                'Fictional advert body for gating.', 'Example Aerospace',
                'Senior Systems Engineer')
            capture_refused = False
        except ValueError as error:
            capture_refused = 'before capturing a job' in str(error)
        checks.append(('unsigned candidate truth refuses job capture',
                       capture_refused))
        checks.append(('the browser routes an ungated capture to truth setup',
                       'function openIntake()' in app_script
                       and 'entry.can_capture === false' in app_script
                       and 'data-active-action="truth"' in app_script))

    # A real first run initializes the workspace before anything else. It must
    # route to career-truth setup, not to a job link.
    with tempfile.TemporaryDirectory(prefix='joblooper-dashboard-init-') as fresh:
        workspace = os.path.join(fresh, 'workspace')
        store.configure(workspace)
        vec.reset_caches()
        with contextlib.redirect_stdout(io.StringIO()):
            jl.cmd_init(SimpleNamespace(demo=False))
        first_run = truth_review.entry_state()
        checks.append(('a fresh workspace opens on career truth, not job capture',
                       first_run['state'] == 'UNINITIALIZED'
                       and first_run['can_capture'] is False
                       and 'career truth' in first_run['next_action'].lower()))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} dashboard invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
