import unittest
import subprocess
import sys
from unittest.mock import Mock, patch

from rpa.isolation import session_lock
from rpa.report_jobs import claim_report, get_job, finish_job, run_report_queue
from rpa.report_worker import execute
from rpa.session_models import LoginMode, PortalEnvironment, PortalSessionError
from tests.rpa import test_report_jobs as fixtures


class ReportQueueLifecycleTest(unittest.TestCase):
    setUp = fixtures.ReportIsolationTest.setUp
    claim = fixtures.ReportIsolationTest.claim
    new_backbone_task = fixtures.ReportIsolationTest.new_backbone_task

    def enqueue(self, user=0):
        principal, service = self.people[user]
        return claim_report(self.db, principal, service, self.new_backbone_task(),
                            PortalEnvironment.TEST, self.root)[0]

    def test_login_failure_pauses_only_owner_and_relogin_resumes_same_identity(self):
        from rpa.report_queue import pause_for_login, change_report_pause
        first, _ = self.claim()
        second, paused, other = self.enqueue(), self.enqueue(), self.enqueue(1)
        principal, service = self.people[0]
        change_report_pause(self.db, self.root, principal, paused, True)
        pause_for_login(self.db, first, 'RPA_SESSION_REQUIRED', '登录失效')
        self.assertEqual([get_job(self.db, rid)['status'] for rid in (first, second, paused, other)],
                         ['waiting_login', 'waiting_login', 'paused', 'pending'])
        action = Mock()
        with patch('rpa.report_jobs.run_report_process', action):
            run_report_queue(self.db, self.root, first)
        action.assert_not_called()
        self.assertFalse(service.status(PortalEnvironment.TEST).authenticated)
        previous_version = get_job(self.db, first)['session_version']
        attempt = service.begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
        with self.assertRaises(PortalSessionError):
            service.login_with_password(attempt.attempt_id, 'wrong-account', 'secret', '42')
        service.login_with_password(attempt.attempt_id, 'portal-alice', 'secret', '42')
        self.assertEqual([get_job(self.db, rid)['status'] for rid in (first, second, paused)],
                         ['pending', 'pending', 'paused'])
        self.assertNotEqual(get_job(self.db, first)['session_version'], previous_version)
        self.assertEqual(get_job(self.db, paused)['session_version'], get_job(self.db, first)['session_version'])

    def test_paused_task_is_skipped_and_resume_retains_original_order(self):
        from rpa.report_queue import change_report_pause
        first, second = self.enqueue(), self.enqueue()
        principal = self.people[0][0]
        change_report_pause(self.db, self.root, principal, first, True)
        executed = []
        def complete(task_id, rid, *args, **kwargs):
            executed.append(rid)
            self.db.update_cutover_report(rid, status='success')
        with patch('rpa.report_jobs.run_report_process', side_effect=lambda db, root, rid: execute(db, root, rid, complete)):
            run_report_queue(self.db, self.root, first)
            self.assertEqual(executed, [second])
            change_report_pause(self.db, self.root, principal, first, False)
            run_report_queue(self.db, self.root, first)
        self.assertEqual(executed, [second, first])

    def test_recovery_marks_abandoned_running_unknown_and_schedules_pending_only(self):
        from rpa.report_queue import recover_report_jobs, change_report_pause
        running, pending, paused = self.enqueue(), self.enqueue(), self.enqueue()
        finish_job(self.db, running, 'running')
        self.db.update_cutover_report(running, status='running', result={'note': '提交中'})
        change_report_pause(self.db, self.root, self.people[0][0], paused, True)
        scheduled = []
        self.assertEqual(recover_report_jobs(self.db, self.root, scheduled.append), [])
        self.assertEqual(scheduled, [pending])
        self.assertEqual(get_job(self.db, running)['status'], 'interrupted')
        self.assertEqual(self.db.get_cutover_report(running)['result']['current_step_label'], '结果待核对')
        self.assertEqual(get_job(self.db, paused)['status'], 'paused')

    def test_recovery_does_not_interrupt_live_worker_and_preserves_saved_success(self):
        from rpa.report_queue import recover_report_jobs
        running, pending = self.enqueue(), self.enqueue()
        finish_job(self.db, running, 'running')
        scheduled = []
        with session_lock(self.people[0][1].lock_path):
            blocked = recover_report_jobs(self.db, self.root, scheduled.append)
        self.assertEqual(blocked, [self.people[0][0].key])
        self.assertEqual(scheduled, [])
        self.db.update_cutover_report(running, status='success')
        recover_report_jobs(self.db, self.root, scheduled.append, principals=blocked)
        self.assertEqual(get_job(self.db, running)['status'], 'success')
        self.assertEqual(scheduled, [pending])

    def test_restart_after_worker_process_dies_never_replays_running_report(self):
        from rpa.report_queue import recover_report_jobs
        rid, pending = self.enqueue(), self.enqueue()
        finish_job(self.db, rid, 'running')
        self.db.update_cutover_report(rid, status='running')
        worker = subprocess.Popen([sys.executable, '-c',
            'import fcntl,sys,time; f=open(sys.argv[1], "a"); fcntl.flock(f, fcntl.LOCK_EX); '
            'print("ready", flush=True); time.sleep(30)', str(self.people[0][1].lock_path)],
            stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(worker.stdout.readline().strip(), 'ready')
            scheduled = []
            deferred = recover_report_jobs(self.db, self.root, scheduled.append)
            self.assertEqual(scheduled, [])
        finally:
            worker.terminate()
            worker.wait(timeout=5)
            worker.stdout.close()
        recover_report_jobs(self.db, self.root, scheduled.append, principals=deferred)
        self.assertEqual(get_job(self.db, rid)['status'], 'interrupted')
        self.assertEqual(scheduled, [pending])

    def test_manual_pause_survives_login_pause_and_restart(self):
        from rpa.report_queue import change_report_pause, pause_for_login, recover_report_jobs
        first, second = self.enqueue(), self.enqueue()
        pause_for_login(self.db, first, 'RPA_SESSION_REQUIRED', 'expired')
        change_report_pause(self.db, self.root, self.people[0][0], second, True)
        scheduled = []
        recover_report_jobs(self.db, self.root, scheduled.append)
        self.assertEqual(scheduled, [])
        service = self.people[0][1]
        attempt = service.begin(LoginMode.PASSWORD, PortalEnvironment.TEST)
        service.login_with_password(attempt.attempt_id, 'portal-alice', 'secret', '42')
        recover_report_jobs(self.db, self.root, scheduled.append)
        self.assertEqual(scheduled, [first])
        self.assertEqual(get_job(self.db, second)['status'], 'paused')

    def test_running_task_and_other_users_task_cannot_be_paused(self):
        from rpa.report_queue import change_report_pause
        rid = self.enqueue()
        with self.assertRaises(PortalSessionError) as caught:
            change_report_pause(self.db, self.root, self.people[1][0], rid, True)
        self.assertEqual(caught.exception.code, 'ACCESS_DENIED')
        finish_job(self.db, rid, 'running')
        with self.assertRaises(PortalSessionError) as caught:
            change_report_pause(self.db, self.root, self.people[0][0], rid, True)
        self.assertEqual(caught.exception.code, 'TASK_BUSY')

    def test_clean_worker_exit_cannot_mark_a_resumed_pending_job_interrupted(self):
        from rpa.report_jobs import run_report_process
        rid = self.enqueue()
        with patch('rpa.report_jobs.subprocess.Popen') as process:
            process.return_value.wait.return_value = 0
            run_report_process(self.db, self.root, rid)
        self.assertEqual(get_job(self.db, rid)['status'], 'pending')

    def test_recovery_rechecks_users_with_live_queue_owners(self):
        from rpa.report_queue import recover_report_jobs
        rid = self.enqueue()
        finish_job(self.db, rid, 'running')
        self.db.update_cutover_report(rid, status='running')
        scheduled = []
        with session_lock(self.people[0][1].root / 'report-queue.lock'):
            deferred = recover_report_jobs(self.db, self.root, scheduled.append)
        self.assertEqual(deferred, [self.people[0][0].key])
        self.assertEqual(get_job(self.db, rid)['status'], 'running')
        recover_report_jobs(self.db, self.root, scheduled.append, principals=deferred)
        self.assertEqual(get_job(self.db, rid)['status'], 'interrupted')
