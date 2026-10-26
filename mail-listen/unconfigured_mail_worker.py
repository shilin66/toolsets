import json
import threading
import uuid

import requests
from loguru import logger

from actions import APIForwardAction, email_message_from_record
from config import settings
from cutover_prompt import get_fixed_field_definitions, TIME_CONVERSION_RULES
from fastgpt_contracts import parse_response
from unconfigured_mail_repository import UnconfiguredMailRepository


class MailAIWorker:
    def __init__(self, db, concurrency=2):
        self.db = db
        self.repo = UnconfiguredMailRepository(db)
        self.concurrency = concurrency
        self.stopping = threading.Event()
        self.threads = []

    def start(self):
        if self.threads:
            return
        self.stopping.clear()
        for index in range(self.concurrency):
            thread = threading.Thread(target=self._loop, name=f'MailAI-{index}', daemon=True)
            self.threads.append(thread)
            thread.start()

    def stop(self):
        self.stopping.set()
        for thread in self.threads:
            thread.join(timeout=2)

    def _loop(self):
        while not self.stopping.is_set():
            try:
                if self.run_once():
                    continue
            except Exception as exc:
                logger.error('邮件 AI 队列执行失败：{}', type(exc).__name__)
            self.stopping.wait(1)

    def run_once(self):
        job = self.repo.claim(lease_seconds=max(300, settings.api_timeout * 6 + 60), combined=True)
        if job is None:
            return False
        try:
            record = self.db.get_email_record_by_id(job['email_records_id'])
            if record is None:
                raise ValueError('任务原始邮件不存在')
            content = json.loads(APIForwardAction(self.db)._build_content(
                email_message_from_record(record), {'_email_records_id': record['id']}))
            content.update({key: job[key] for key in ('task_type', 'request_id', 'attempt_id', 'draft_id', 'draft_revision')})
            content.update(schema_version=1, security_timezone='Asia/Shanghai')
            combined = job['task_type'] == 'unconfigured_mail_analyze'
            if combined:
                content.update(job['workflow_context'], task_type='unconfigured_mail_process')
            if job['task_type'] == 'supplier_config_draft' or content.get('should_generate_supplier_draft'):
                content['fixed_field_defaults'] = {
                    **get_fixed_field_definitions(), 'time_conversion_rules': TIME_CONVERSION_RULES}
            response = requests.post(settings.api_url, json={
                'chatId': str(uuid.uuid4()), 'stream': False, 'detail': False,
                'messages': [{'role': 'user', 'content': json.dumps(content, ensure_ascii=False)}],
            }, headers={'Authorization': f'Bearer {settings.api_token}', 'Content-Type': 'application/json'},
                timeout=settings.api_timeout * (3 if combined else 1))
            if not response.ok:
                self.repo.fail(job, f'FastGPT HTTP {response.status_code}',
                               transient=response.status_code == 429 or response.status_code >= 500)
            else:
                envelope = parse_response(response.json())
                if combined:
                    self.repo.complete_combined(envelope)
                else:
                    self.repo.complete(envelope)
        except (requests.Timeout, requests.ConnectionError) as exc:
            self.repo.fail(job, f'FastGPT 网络请求失败：{type(exc).__name__}', transient=True)
        except (ValueError, TypeError, KeyError) as exc:
            self.repo.fail(job, f'FastGPT 结果无效：{exc}')
        except Exception as exc:
            logger.error('邮件 AI 任务异常，job_id={}，error={}', job['id'], type(exc).__name__)
            self.repo.fail(job, f'任务执行异常：{type(exc).__name__}', transient=True)
        return True
