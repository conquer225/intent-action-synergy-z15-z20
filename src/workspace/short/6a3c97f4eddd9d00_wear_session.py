"""Explicit boot-local wearing identity; only acquisition may reset a baseline."""
import json
import os
from pathlib import Path
import secrets
import stat
import time

from cyton_trial_recorder import atomic_json, recording_command_lock


class WearSession:
    def __init__(self, directory='/run/guardianloop', clock=time.monotonic):
        self.directory=Path(directory)
        self.state_path=self.directory/'wear-session.json'
        self.command_path=self.directory/'wear-command.json'
        self.clock=clock
        self.boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip() if os.name=='posix' else 'software-test-host'
        self.next_poll=0.

    def _read(self, path):
        try:info=path.lstat()
        except FileNotFoundError:return {}
        if (not stat.S_ISREG(info.st_mode) or info.st_size>4096
                or (os.name=='posix' and (info.st_uid!=os.geteuid() or info.st_mode&0o077))):
            raise ValueError('佩戴会话文件权限或大小异常')
        row=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(row,dict):raise ValueError('佩戴会话格式异常')
        return row

    def _write(self, path, row):
        self.directory.mkdir(parents=True,exist_ok=True)
        atomic_json(path,row)
        os.chmod(path,0o600)

    def snapshot(self):
        row=self._read(self.state_path)
        if row.get('boot')!=self.boot:return dict(state='unavailable',reason='等待本次开机的采集服务')
        return row

    def initialize(self):
        row=self.snapshot()
        if row.get('id'):return row['id']
        row=dict(boot=self.boot,id=secrets.token_hex(16),state='active',
                 last_command=None,reason='本次开机首次佩戴；仍需有效校准',updated_monotonic=self.clock())
        self._write(self.state_path,row)
        return row['id']

    def request_new(self, expected):
        with recording_command_lock(self.command_path):
            state=self.snapshot()
            if not isinstance(expected,str) or expected!=state.get('id'):
                raise ValueError('佩戴会话已改变，请刷新后确认，未重置')
            pending=self._read(self.command_path)
            if pending and pending.get('id')!=state.get('last_command'):
                raise ValueError('上一条佩戴命令尚未确认')
            row=dict(id=secrets.token_hex(16),action='new_wear',expected_id=expected,
                     boot=self.boot,requested_monotonic=self.clock())
            self._write(self.command_path,row)
            return dict(command_id=row['id'],state='queued',not_yet_confirmed=True)

    def poll(self, reset, *, recording=False):
        if self.clock()<self.next_poll:return
        self.next_poll=self.clock()+.25
        if not self.directory.is_dir():return
        with recording_command_lock(self.command_path):
            state=self.snapshot();command=self._read(self.command_path)
            if not command or command.get('id')==state.get('last_command'):return
            stamp=command.get('requested_monotonic')
            accepted=(command.get('boot')==self.boot and command.get('action')=='new_wear'
                      and command.get('expected_id')==state.get('id')
                      and type(stamp) in (int,float) and 0<=self.clock()-stamp<=30 and not recording)
            if accepted:
                identifier=secrets.token_hex(16)
                reset(identifier)
                state.update(id=identifier,reason='已按本人确认开始新佩戴；旧基线已清除',command_state='applied')
            else:
                state.update(reason='佩戴命令过期、会话变化或正在录制；未清除基线',command_state='rejected')
            state.update(last_command=command.get('id'),updated_monotonic=self.clock())
            self._write(self.state_path,state)
