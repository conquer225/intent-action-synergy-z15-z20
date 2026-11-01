"""Verification-only Newton residual refinement; immutable fitted models/scores."""
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import mi_logcov_comparison as frozen_driver
import numpy as np
from scipy.optimize import minimize
from threadpoolctl import threadpool_limits

HERE = Path(__file__).resolve().parent
PLAN = HERE / 'MI_LOGCOV_VERIFICATION_REPAIR.md'
TRACE = []


def stabilized_classifier(z, labels, c):
    terms = frozen_driver.logistic_terms
    with threadpool_limits(limits=1):
        result = minimize(lambda b: terms(b, z, labels, c)[0], np.zeros(z.shape[1]+1),
            jac=lambda b: terms(b, z, labels, c)[1],
            hess=lambda b: terms(b, z, labels, c)[2], method='trust-exact',
            options={'gtol': 1e-7, 'maxiter': 200})
        beta = result.x.copy()
        objective, gradient, hessian = terms(beta, z, labels, c)
        initial_gradient = float(np.max(np.abs(gradient)))
        steps = []
        for _ in range(8):
            magnitude = float(np.max(np.abs(gradient)))
            if magnitude <= 1e-7:
                break
            candidate = beta - np.linalg.solve(hessian, gradient)
            after, gnext, hnext = terms(candidate, z, labels, c)
            next_magnitude = float(np.max(np.abs(gnext)))
            rounding_bound = 64*np.finfo(np.float64).eps*max(1., abs(objective))
            if (not np.isfinite(candidate).all() or not np.isfinite(after)
                    or after > objective+rounding_bound or next_magnitude >= magnitude):
                raise ValueError('Newton verification refinement failed finite/descent/rounding check')
            steps.append({'gradient_before': magnitude, 'gradient_after': next_magnitude,
                          'objective_delta': after-objective, 'objective_rounding_bound': rounding_bound})
            beta, objective, gradient, hessian = candidate, after, gnext, hnext
        final_gradient = float(np.max(np.abs(gradient)))
    if not np.isfinite(beta).all() or final_gradient > 1e-6:
        raise ValueError(f'Original independent-gradient bound failed: {final_gradient}')
    TRACE.append({'dimensions': z.shape[1], 'training_rows': len(labels), 'C': c,
                  'trust_exact_success': bool(result.success), 'trust_exact_message': str(result.message),
                  'initial_gradient': initial_gradient, 'final_gradient': final_gradient, 'steps': steps})
    return beta, final_gradient


def main():
    output = frozen_driver.OUTPUT
    target = output / 'verification.json'
    if target.exists() or (output / 'verification_repair_lock.json').exists():
        raise RuntimeError('Completed or partial supplemental verification preserved')
    frozen_driver.load(output)
    frozen_driver.frozen(output)
    result_hash = frozen_driver.digest(output / 'results.json')
    if result_hash != 'b3d85afd9cbb9fe8f1a81b15d975bb6f2cd448f1b47b5ba771ba9003d43bc209':
        raise ValueError('Original negative result changed')
    sources = {str(path): frozen_driver.digest(path) for path in (Path(__file__), PLAN)}
    frozen_driver.save(output / 'verification_repair_lock.json', {
        'declared_at_local': datetime.now().isoformat(), 'source_sha256': sources,
        'results_sha256': result_hash, 'model_scores_tolerances_changed': False,
        'original_failed_gradient': 3.861518784731288e-06, 'original_failure_preserved': True})
    for path in (Path(__file__), PLAN):
        (output / 'code_snapshot' / path.name).write_bytes(path.read_bytes())
    with patch.object(frozen_driver, 'independent_classifier', stabilized_classifier):
        frozen_driver.verify(output)
    assert len(TRACE) == 240
    for path, expected in sources.items():
        assert frozen_driver.digest(path) == expected
    assert frozen_driver.digest(output / 'results.json') == result_hash
    trace_path = output / 'verification_solver_trace.json'
    frozen_driver.save(trace_path, {'solutions': TRACE, 'count': len(TRACE),
        'solutions_refined': sum(bool(r['steps']) for r in TRACE),
        'max_initial_gradient': max(r['initial_gradient'] for r in TRACE),
        'max_final_gradient': max(r['final_gradient'] for r in TRACE),
        'at_local': datetime.now().isoformat()})
    verified = frozen_driver.read(target)
    verified.update(verification_only_repair=True, model_scores_tolerances_changed=False,
        solver_trace_sha256=frozen_driver.digest(trace_path),
        repair_lock_sha256=frozen_driver.digest(output / 'verification_repair_lock.json'),
        original_failure_preserved=True)
    frozen_driver.save(target, verified)
    print('VERIFIED_WITH_ORIGINAL_TOLERANCES', len(TRACE), flush=True)


if __name__ == '__main__':
    main()
