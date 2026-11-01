"""Generate a clearly separate IS4 experimental probe from pinned Apache-2.0 source."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = (root / "third_party/njmill/tobii-ttp-mux.c").read_text()
assert source.count("#define TOBII_PID 0x0313") == 1
source = source.replace("#define TOBII_PID 0x0313", "#define TOBII_PID 0x0124 /* Z15 connected IS4 OEM; experimental */")
source = source.replace('const char *startup = "public";', 'const char *startup = "tobiifree";')
source = source.replace('const char *streams_text = "0501,050e,1771";', 'const char *streams_text = "0501";')
# Vendor ttp_authorize_challenge serializes the second argument as u32_arr,
# including an empty array. The original raw 00 byte is not a TLV array.
source = source.replace('    payload[n++] = 0x00;\n    unsigned char ttp[MAX_PACKET_BYTES];\n    size_t ttp_len = build_frame(ttp, seq, TTP_OP_OPEN_REALM',
'''    payload[n++] = 0x17;
    put_be32(payload+n,4); n+=4;
    put_be32(payload+n,0); n+=4;
    unsigned char ttp[MAX_PACKET_BYTES];
    size_t ttp_len = build_frame(ttp, seq, TTP_OP_OPEN_REALM''')
# Realm query 0 is the device's no-auth path; invalid challenge replies must
# never be used as an acknowledgement. Keep normal authenticated paths intact.
source = source.replace('''    packet_len = build_open_realm(seq, realm_type, packet);
    err = send_request_wait_response(handle, parser, "open_realm", packet, packet_len, seq, &response);
    if (err != 0) return err;
    seq++;''', '''    if (realm_type != 0) {
        packet_len = build_open_realm(seq, realm_type, packet);
        err = send_request_wait_response(handle, parser, "open_realm", packet, packet_len, seq, &response);
        if (err != 0) return err;
        seq++;
    }''')
needle = '                    response->plen);\n            return 0;'
assert source.count(needle) == 1
source = source.replace(needle, '                    response->plen);\n            fprintf(stderr, "response_hex name=%s data=", name);\n            for (uint32_t j=0; j<response->plen && j<512; j++) fprintf(stderr, "%02x", response->payload[j]);\n            fprintf(stderr, "\\n");\n            return 0;')
source = source.replace("j<response->plen && j<512", 'j<response->plen && j<512 && strcmp(name, "calibration_backup") != 0')
source = source.replace("response->magic == TTP_MAGIC_RSP && response->seq == seq", "response->magic == TTP_MAGIC_RSP && response->seq == seq && response->op == be32_at(packet, ENVELOPE_SIZE + 12)")

# A partial image split over many USB transfers is not a USB timeout.
start = source.index("    int popped = parser_pop(parser, frame);", source.index("static int read_next_frame"))
end = source.index("\n}\n", start)
source = source[:start] + '''    uint64_t deadline = monotonic_ns() + (uint64_t)timeout_ms * 1000000ull;
    while (!stop_requested) {
        int popped = parser_pop(parser, frame);
        if (popped < 0) {
            fprintf(stderr, "frame_parse_error buffered=%zu prefix=", parser->len);
            for (size_t i=0; i<parser->len && i<64; i++) fprintf(stderr, "%02x", parser->acc[i]);
            fprintf(stderr, "\\n");
            FILE *dump = fopen("captures/parser_error.bin", "wb");
            if (dump) { fwrite(parser->acc, 1, parser->len, dump); fclose(dump); }
            return LIBUSB_ERROR_OTHER;
        }
        if (popped > 0) return popped;
        uint64_t now = monotonic_ns();
        if (now >= deadline) return 0;
        unsigned char buf[READ_BUFFER_BYTES];
        int transferred = 0;
        unsigned int remaining_ms = (unsigned int)((deadline - now + 999999) / 1000000);
        int err = libusb_bulk_transfer(handle, TOBII_EP_IN, buf, sizeof(buf), &transferred, remaining_ms);
        if (transferred > 0 && parser_feed(parser, buf, (size_t)transferred) != 0)
            return LIBUSB_ERROR_OVERFLOW;
        if (err != 0 && err != LIBUSB_ERROR_TIMEOUT) {
            fprintf(stderr, "usb_bulk_error code=%d transferred=%d buffered=%zu\\n", err, transferred, parser->len);
            return err;
        }
        if (err == LIBUSB_ERROR_TIMEOUT) return parser_pop(parser, frame);
    }
    return 0;''' + source[end:]

source = source.replace("    bool stream_disable = false;", "    bool inspect = false;\n    bool stream_disable = false;")
source = source.replace("    bool inspect = false;", "    bool inspect = false;\n    bool calibration_probe = false;")
source = source.replace("    bool calibration_probe = false;", "    bool calibration_probe = false;\n    bool collect_center = false;")
source = source.replace('        } else if (strcmp(argv[i], "--help") == 0) {', '        } else if (strcmp(argv[i], "--inspect") == 0) {\n            inspect = true;\n        } else if (strcmp(argv[i], "--help") == 0) {')
source = source.replace('        } else if (strcmp(argv[i], "--inspect") == 0) {', '        } else if (strcmp(argv[i], "--probe-calibration") == 0) {\n            calibration_probe = true;\n        } else if (strcmp(argv[i], "--inspect") == 0) {')
source = source.replace('        } else if (strcmp(argv[i], "--probe-calibration") == 0) {', '        } else if (strcmp(argv[i], "--collect-center") == 0) {\n            collect_center = true; calibration_probe = true;\n        } else if (strcmp(argv[i], "--probe-calibration") == 0) {')
source = source.replace('uint64_t deadline = monotonic_ns() + 2000000000ull;', 'uint64_t deadline = monotonic_ns() + (strcmp(name, "calibration_collect_center") == 0 ? 30000000000ull : 2000000000ull);')
needle = "    uint64_t start_ns = monotonic_ns();"
assert source.count(needle) == 1
source = source.replace(needle, '''    if (inspect) {
        /* Read-only queries: never clear, compute or overwrite calibration. */
        const uint32_t ops[] = {0x04b0, 0x0c62, 0x044c, 0x0460, 0x04ba, 0x05d2, 0x058c, 0x0780};
        const char *names[] = {"catalog", "enabled_eye", "calibration_backup", "calibration_points", "gaze_schema", "device_status", "unit_information", "lowblink_mode"};
        for (size_t i = 0; i < sizeof(ops) / sizeof(ops[0]); i++) {
            unsigned char payload[16] = {0};
            unsigned char packet[MAX_PACKET_BYTES];
            struct ttp_frame response;
            size_t plen = 2;
            if (ops[i] == 0x04ba) plen += tlv_u32(payload + 2, STREAM_GAZE);
            uint32_t seq = next_seq++;
            unsigned char ttp[MAX_PACKET_BYTES];
            size_t tlen = build_frame(ttp, seq, ops[i], payload, plen);
            size_t packet_len = wrap_envelope(packet, ttp, tlen);
            int query_err = send_request_wait_response(handle, &parser, names[i], packet, packet_len, seq, &response);
            if (query_err != 0) {
                fprintf(stderr, "inspect_failed name=%s error=%d\\n", names[i], query_err);
                continue;
            }
            char path[1024];
            if (write_raw_payload(out_dir, ops[i], 0, response.payload, response.plen, path, sizeof(path)) != 0) {
                fprintf(stderr, "inspect_save_failed name=%s\\n", names[i]);
            }
        }
    }

    {
        /* Vendor ttp_set_tracker_pause_state / captured initialization: resume. */
        unsigned char payload[16] = {0};
        unsigned char ttp[64], packet[80];
        struct ttp_frame response;
        size_t payload_len = 2 + tlv_u32(payload + 2, 0);
        uint32_t seq = next_seq++;
        size_t tlen = build_frame(ttp, seq, 0x0c1c, payload, payload_len);
        size_t plen = wrap_envelope(packet, ttp, tlen);
        err = send_request_wait_response(handle, &parser, "resume_tracker", packet, plen, seq, &response);
        fprintf(stderr, "resume_tracker_result=%d\\n", err);
        if (err != 0) {
            libusb_control_transfer(handle, 0x41, 0x42, 0, 0, NULL, 0, 500);
            libusb_release_interface(handle, TOBII_VENDOR_IFACE);
            libusb_close(handle);
            libusb_exit(ctx);
            fclose(csv);
            fclose(events);
            return EXIT_FAILURE;
        }
    }

    if (calibration_probe) {
        /* Enter/exit only. Never clear, add points, compute or apply a model. */
        unsigned char prefix[2] = {0};
        unsigned char ttp[64], packet[80];
        struct ttp_frame response;
        uint32_t seq = next_seq++;
        size_t tlen = build_frame(ttp, seq, 0x03f2, prefix, 2);
        size_t plen = wrap_envelope(packet, ttp, tlen);
        err = send_request_wait_response(handle, &parser, "calibration_enter_probe", packet, plen, seq, &response);
        fprintf(stderr, "calibration_enter_probe_result=%d\\n", err);
        if (err == 0 && collect_center) {
            unsigned char point[64] = {0};
            size_t n = 2;
            /* Vendor ttp_calibration_add_point: two Q42 scalars + both eyes. */
            n += tlv_q42(point+n, 0.5);
            n += tlv_q42(point+n, 0.5);
            n += tlv_u32(point+n, 3);
            seq = next_seq++;
            tlen = build_frame(ttp, seq, 0x0406, point, n);
            plen = wrap_envelope(packet, ttp, tlen);
            int collected = send_request_wait_response(handle, &parser, "calibration_collect_center", packet, plen, seq, &response);
            fprintf(stderr, "calibration_collect_center_result=%d\\n", collected);
        }
    }

''' + needle)
source = source.replace("        gaze_packets++;", '''        gaze_packets++;
        if (gaze_packets == 1) {
            char path[1024];
            if (write_raw_payload(out_dir, STREAM_GAZE, 0, frame.payload, frame.plen, path, sizeof(path)) != 0)
                fprintf(stderr, "gaze_payload_save_failed\\n");
        }''')

# The real IS4 schema, not ET5 field assumptions: 0x1b is combined
# validity; 0x16 is left-eye detected, 0x15 is right-eye detected.
source = source.replace("if (!tlv_read_u32(&reader, &sample->binocular_flag)) return true;", "if (!tlv_read_u32(&reader, &sample->gaze_valid)) return true;")
source = source.replace("case 0x15:\n                if (!tlv_read_u32(&reader, &sample->eye_present_l))", "case 0x15:\n                if (!tlv_read_u32(&reader, &sample->eye_present_r))")
source = source.replace("case 0x16:\n                if (!tlv_read_u32(&reader, &sample->eye_present_r))", "case 0x16:\n                if (!tlv_read_u32(&reader, &sample->eye_present_l))")
begin = source.index("static bool decode_gaze_sample(")
end = source.index("\nstatic int run_tobiifree_handshake", begin)
decoder = source[begin:end]
decoder = decoder.replace("return true;", "return false;")
decoder = decoder.replace("    return false;\n}", "    return reader.pos == reader.len;\n}")
decoder = decoder.replace("i < n_cols && reader.pos < reader.len", "i < n_cols")
decoder = decoder.replace("    uint32_t n_cols = 0;", "    uint32_t n_cols = 0;\n    uint64_t seen = 0;")
decoder = decoder.replace("        switch (col) {", "        if (col >= 64 || (seen & (1ull << col))) return false;\n        seen |= 1ull << col;\n        switch (col) {")
source = source[:begin] + decoder + source[end:]
source = source.replace("sample.gaze_y >= 0.0)", "sample.gaze_y >= 0.0 && sample.gaze_x <= 1.0 && sample.gaze_y <= 1.0 && ((sample.eye_present_l == 1 && sample.validity_l == 0) || (sample.eye_present_r == 1 && sample.validity_r == 0)))")
source = source.replace("#include <sys/stat.h>", "#include <sys/stat.h>\n#include <sys/resource.h>")
end = source.rindex("    libusb_control_transfer(handle, 0x41, 0x42")
source = source[:end] + '''    if (calibration_probe) {
        unsigned char prefix[2] = {0};
        unsigned char ttp[64], packet[80];
        struct ttp_frame response;
        uint32_t seq = next_seq++;
        size_t tlen = build_frame(ttp, seq, 0x03fc, prefix, 2);
        size_t plen = wrap_envelope(packet, ttp, tlen);
        sig_atomic_t saved_stop = stop_requested;
        stop_requested = 0;
        int stopped = send_request_wait_response(handle, &parser, "calibration_exit_probe", packet, plen, seq, &response);
        stop_requested = saved_stop;
        fprintf(stderr, "calibration_exit_probe_result=%d\\n", stopped);
        if (stopped != 0) errors++;
    }
    struct rusage usage;
    if (getrusage(RUSAGE_SELF, &usage) == 0) {
        fprintf(stderr, "resources elapsed_s=%.6f user_s=%.6f system_s=%.6f max_rss_kib=%ld\\n",
                (monotonic_ns() - start_ns) / 1e9,
                usage.ru_utime.tv_sec + usage.ru_utime.tv_usec / 1e6,
                usage.ru_stime.tv_sec + usage.ru_stime.tv_usec / 1e6,
                usage.ru_maxrss);
    }
''' + source[end:]
destination = root / "build/is4-probe.c"

# TTP header offset 16 is the protocol error word (vendor parser checks it
# before dispatching a response). Offset 8 is retained for diagnostics too.
source = source.replace('    uint32_t magic;\n', '    uint32_t magic;\n    uint32_t header8;\n    uint32_t status;\n', 1)
source = source.replace('    frame->op = be32_at(ttp, 12);',
                        '    frame->header8 = be32_at(ttp, 8);\n    frame->status = be32_at(ttp, 16);\n    frame->op = be32_at(ttp, 12);')
source = source.replace('            return 0;\n        }\n    }\n\n    fprintf(stderr, "handshake_response',
'''            fprintf(stderr, "response_header name=%s header8=%08x status=%08x\\n", name, response->header8, response->status);
            if (response->status != 0) return LIBUSB_ERROR_OTHER;
            return 0;
        }
    }

    fprintf(stderr, "handshake_response''', 1)
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text("/* Generated IS4 probe. Original and license in third_party/njmill. */\n" + source)
print(destination)
