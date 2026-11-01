"""Decode the public S3 TELEM_V3 wire record; enable is not a sequence number."""
def hand_telemetry(line):
    fields = line.split(',')
    if len(fields) != 24 or fields[0] != 'TELEM_V3':
        return None
    return {
        'sequence': int(fields[1]),
        'feedback_sequence': int(fields[2]),
        'output_acknowledged': fields[-3] == '1',
        'pressure_fresh': fields[-2] == '1',
        'actuator_ready': fields[-1] == '1',
    }
