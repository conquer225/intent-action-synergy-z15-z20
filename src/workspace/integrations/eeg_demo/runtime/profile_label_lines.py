"""Private line timing of the unchanged active label renderer; ordinary RAM only."""
import hashlib
import inspect
import json
import sys
import time

from profile_video_ram import DISPLAY, SESSION, Timings, verify_pins


def profile():
    pins = verify_pins()
    sys.path.insert(0, str(DISPLAY))
    import system_hdmi as active
    state = json.loads((DISPLAY / (SESSION + '.json')).read_text())
    display = active.UnifiedDisplay(state['eye_root'], live=True, dimensions=(288, 512),
                                   shell_cache=DISPLAY / 'menu-shells-portrait-live.npz')
    display.controller._enter('video', time.monotonic())
    code = active.UnifiedDisplay.refresh_labels.__code__
    source, first = inspect.getsourcelines(active.UnifiedDisplay.refresh_labels)
    text = {first+index: line.strip() for index, line in enumerate(source)}
    trace = Timings()
    previous = {}

    def line_trace(frame, event, arg):
        if frame.f_code is not code:
            return None
        wall, cpu = time.monotonic(), time.thread_time()
        old = previous.pop(id(frame), None)
        if old:
            line, before_wall, before_cpu = old
            trace.rows.setdefault('line_'+str(line), []).append(
                ((wall-before_wall)*1000, (cpu-before_cpu)*1000))
        if event == 'line':
            previous[id(frame)] = (frame.f_lineno, wall, cpu)
        return line_trace

    original = sys.gettrace()
    try:
        sys.settrace(line_trace)
        for index in range(8):
            row = dict(emotion=dict(valid=True, label='funny' if index % 2 else 'boring'))
            with trace.measure('whole_refresh_instrumented'):
                display.refresh_labels(row, {}, 'pinned clip')
    finally:
        sys.settrace(original)
    rows = trace.summary()
    ranked = sorted((dict(line=int(name[5:]), source=text[int(name[5:])], **stats)
                     for name, stats in rows.items() if name.startswith('line_')),
                    key=lambda row: row['thread_cpu_total_ms'], reverse=True)
    if verify_pins() != pins:
        raise ValueError('Protected display payload changed')
    return dict(scope='active_function_line_trace_in_private_RAM_process',
        whole=rows['whole_refresh_instrumented'], lines=ranked, fixtures=8,
        active_source_sha256=pins['system_hdmi.py'],
        final_overlay_sha256=hashlib.sha256(display.overlays['video'].tobytes()).hexdigest(),
        pl_loaded=False, cache_flush_measured=False, display_submit_measured=False,
        note='Timings include tracing overhead. No tracing attached to the persistent owner; '
             'no screen FPS or optical measurement.')


if __name__ == '__main__':
    print(json.dumps(profile(), indent=2), flush=True)
