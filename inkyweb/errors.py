"""Errors meant to be shown in the UI.

Each carries a stable code that the browser translates (see static/i18n.js),
the params used in the message, and an English fallback message.
"""


class UserError(Exception):
    def __init__(self, code, message, status=400, **params):
        super().__init__(message.format(**params))
        self.code = code
        self.status = status
        self.params = params

    def to_dict(self):
        return {"code": self.code, "params": self.params, "message": str(self)}
