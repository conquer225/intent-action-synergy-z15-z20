"""Reuse the bounded MI HTTP protocol; expose only the private study page."""
from pathlib import Path
from mi_cued_server import make_handler as base_handler


def make_handler(session, multitask=None):
    class Handler(base_handler(session, multitask=multitask)):
        def do_GET(self):
            if self.path in ('/', '/mi-cued'):
                self.reply(200, Path(__file__).with_name('mi_personal_study.html').read_bytes(),
                           'text/html; charset=utf-8')
            else:
                super().do_GET()
    return Handler
