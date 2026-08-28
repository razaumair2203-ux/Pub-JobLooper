"""Dashboard projection, privacy boundary and local-server invariants."""
import base64
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'examples', 'starter')
sys.path.insert(0, ROOT)

from core import (codex_bridge, dashboard, dashboard_actions, dashboard_runtime,
                  feedback, integrity, job_fetch, store, vec)


def fetch(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.headers, response.read()


def post(url, token, payload, origin=None):
    body = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        url, data=body, method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Joblooper-Token': token,
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
        page_source = store.read_text(os.path.join(ROOT, 'dashboard', 'index.html'))
        active_job = snapshot['jobs'][0]
        checks.append(('active job projection preserves durable workspace state',
                       bool(active_job['updated_at'])
                       and isinstance(active_job['feedback_items'], list)
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
        checks.append(('active workspace exposes every required applicant touchpoint',
                       'function renderActiveWorkspace()' in app_script
                       and "['Captured', workflow.captured]" in app_script
                       and 'data-active-action="evidence"' in app_script
                       and 'data-active-action="artifacts"' in app_script
                       and 'data-active-action="feedback"' in app_script
                       and 'Open captured JD' in app_script
                       and 'CV and letter not created' in app_script
                       and 'not an ATS score' in app_script))
        checks.append(('priority and continue controls execute their displayed action',
                       '<button class="hero-action" id="primary-action"' in page_source
                       and "$('#primary-action').addEventListener('click'" in app_script
                       and "if (action === 'preflight')" in app_script
                       and 'function openPreflight(job)' in app_script
                       and "'/api/actions/preflight'" in app_script))
        checks.append(('URL fallback binds the captured job to deterministic preflight',
                       'state.agentJob = captured[0]' in app_script
                       and 'await openPreflight(captured[0])' in app_script
                       and "['workspace', 'Open application workspace']" in app_script))
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
        checks.append(('job-scoped CV requests receive the application-work profile',
                       'function composerIntent(message)' in app_script
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
        checks.append(('submitted and awaiting-response work remains visible without a false task',
                       applied['jobs'][0]['phase'] == 'applied'
                       and applied['kpis']['submitted'] == 1
                       and applied['kpis']['in_progress'] == 1
                       and not applied['attention']))

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
                           status == 200 and b'Application workspace' in page
                           and b'truth-integrity-dialog' in page
                           and headers.get('Content-Security-Policy') is not None))

            status, headers, body = fetch(base + '/api/dashboard')
            api = json.loads(body.decode('utf-8'))
            checks.append(('dashboard API returns the governed projection',
                           status == 200 and api['kpis']['jobs'] == 1
                           and headers.get('Cache-Control') == 'no-store'))

            status, headers, body = fetch(base + '/api/session')
            session = json.loads(body.decode('utf-8'))
            checks.append(('session advertises guarded interaction capabilities',
                           status == 200 and session['csrf_token']
                           and session['instance_id']
                           and session['dashboard_version']
                           and session['capabilities']['intake'] is True
                           and session['capabilities']['url_intake'] is True
                           and session['capabilities']['structured_preflight'] is True
                           and session['capabilities']['feedback_resolution'] is True
                           and session['capabilities']['submission_update'] is True
                           and session['capabilities']['record_outcome'] is True
                           and session['capabilities']['agent_chat'] is True
                           and session['capabilities']['external_portal_submission'] is False))

            status, headers, body = fetch(
                base + '/api/preflight?job=' + urllib.parse.quote(api['jobs'][0]['id']))
            preflight_view = json.loads(body.decode('utf-8'))
            checks.append(('preflight endpoint returns exact actionable decisions',
                           status == 200 and preflight_view['questions']
                           and preflight_view['complete'] is False
                           and all(row['kind'] == 'KNOWN_GAP'
                                   for row in preflight_view['questions'])))
            refused_answers = {
                row['id']: ('ADD_NEW_EVIDENCE' if index == 0
                            else 'PROCEED_WITH_RECORDED_GAP')
                for index, row in enumerate(preflight_view['questions'])}
            try:
                post(base + '/api/actions/preflight', session['csrf_token'], {
                    'job_id': api['jobs'][0]['id'], 'answers': refused_answers,
                })
                evidence_stop_refused = False
            except urllib.error.HTTPError as error:
                evidence_stop_refused = error.code == 400
            accepted_answers = {
                row['id']: 'PROCEED_WITH_RECORDED_GAP'
                for row in preflight_view['questions']}
            status, headers, preflight_saved = post(
                base + '/api/actions/preflight', session['csrf_token'], {
                    'job_id': api['jobs'][0]['id'], 'answers': accepted_answers,
                })
            checks.append(('dashboard records decisions but blocks unreviewed new evidence',
                           evidence_stop_refused and status == 200
                           and preflight_saved['result']['preflight']['complete'] is True
                           and set(preflight_saved['result']['preflight']['answers'])
                           == set(accepted_answers)))

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
            status, headers, body = fetch(base + source['href'])
            checks.append(('allowlisted artefact endpoint serves a real source file',
                           status == 200 and bool(body)
                           and headers.get('X-Content-Type-Options') == 'nosniff'))

            blocked = False
            try:
                fetch(base + '/artifact?job=..%2F..&id=profile')
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
                       == 'Link Aerospace'))

    with tempfile.TemporaryDirectory(prefix='joblooper-dashboard-empty-') as empty:
        store.configure(empty)
        vec.reset_caches()
        snapshot = dashboard.build_snapshot()
        checks.append(('empty unonboarded workspace renders a safe empty state',
                       snapshot['kpis']['jobs'] == 0
                       and snapshot['jobs'] == []
                       and snapshot['truth']['ready'] is False))

    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n  {passed}/{len(checks)} dashboard invariants hold")
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
