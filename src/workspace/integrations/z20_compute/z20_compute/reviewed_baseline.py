"""Keep the historical baseline immutable while checking exact reviewed deltas."""
import hashlib
from pathlib import Path


def verify_reviewed(root,baseline,review):
    changed=[];errors=[]
    for entry in baseline['files']:
        name,old=entry['path'],entry['sha256'];path=Path(root)/entry['path']
        actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if actual==old:continue
        row=review.get(name,{})
        if row.get('before')==old and row.get('after')==actual and row.get('reason'):
            changed.append(name)
        else:errors.append(name)
    return dict(passed=not errors,unchanged=not errors and not changed,files=len(baseline['files']),
                reviewed_changes=changed,unreviewed_changes=errors)
