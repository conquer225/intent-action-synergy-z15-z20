"""Read-only post-deploy check; stores metadata without EEG samples or secrets."""
import json

from audit_z15_integration import OUT, UNITS, summarize_http
from run_soak_stage import PROD, connect, command


def main():
    deployment = json.loads((OUT / "web_guard_deployment.json").read_text(encoding="utf-8"))
    baseline = json.loads((OUT / "board_snapshot.json").read_text(encoding="utf-8"))
    client = connect()
    try:
        services = {}
        for unit in UNITS:
            raw = command(client, "systemctl show " + unit
                          + " -p ActiveState -p UnitFileState -p MainPID -p NRestarts")
            services[unit] = dict(row.split("=", 1) for row in raw.splitlines() if "=" in row)
        names = ("guardianloop_web.py", "cyton_guardianloop.py", "ssvep_shadow.py",
                 "gameemo_covariance_svm.npz", "cyton_fatigue_overlap4.json",
                 "seed_shadow_weights.npz", "guardianloop_pynq.bit",
                 "guardianloop_pynq.hwh")
        hashes = {}
        for name in names:
            hashes[name] = command(client, "sha256sum " + PROD + "/" + name).split()[0]
        backup_hash = command(client, "sha256sum " + deployment["backup"]).split()[0]
        board_health = command(client,
                               "curl -s -o /dev/null -w '%{http_code}' "
                               "http://192.168.50.1:9102/healthz").strip()
    finally:
        client.close()

    http = summarize_http()
    checks = {
        "all_services_active_and_enabled": all(
            s["ActiveState"] == "active" and s["UnitFileState"] == "enabled"
            for s in services.values()),
        "acquisition_ap_dhcp_pids_unchanged": all(
            services[unit]["MainPID"] == baseline["services"][unit]["MainPID"]
            for unit in ("guardianloop-cyton.service", "guardianloop-ap.service",
                         "guardianloop-dhcp.service")),
        "web_restart_isolated": (services["guardianloop-web.service"]["MainPID"]
                                 != baseline["services"]["guardianloop-web.service"]["MainPID"]),
        "web_candidate_hash": hashes["guardianloop_web.py"] == deployment["deployed_sha256"],
        "web_backup_hash": backup_hash == deployment["baseline_sha256"],
        "other_code_models_pl_unchanged": all(
            hashes[name] == baseline["files_sha256"][name]
            for name in names if name != "guardianloop_web.py"),
        "ap_board_local_http_200": board_health == "200",
        "ethernet_http_200": http["health_http"] == 200,
        "current_invalid_primary": http["status"]["fatigue"]["valid"] is False,
        "current_invalid_emotion": http["telemetry"]["emotion"]["valid"] is False,
        "current_invalid_seed": http["seed_live"]["valid"] is False,
        "current_invalid_ssvep": (http["ssvep_live"]["valid"] is False
                                  and http["ssvep_live"]["frequency_hz"] is None
                                  and http["ssvep_live"]["control_enabled"] is False),
    }
    result = {"scope": "read-only post-deploy, metadata only", "checks": checks,
              "services": services, "hashes": hashes, "ap_board_local_health_http": board_health,
              "http": http}
    (OUT / "post_deploy_verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("Post-deployment verification failed")


if __name__ == "__main__":
    main()
