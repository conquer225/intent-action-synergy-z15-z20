"""Finite actual Z15-to-spare-ESP virtual acceptance. Never sends ARM_HID."""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import socket
import time

from network_receiver import NetworkReceiver, ReceiverError, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    receiver = NetworkReceiver(load_config(args.config))
    cases = []
    before = receiver.probe()
    if before["network_mode"] != "off" or before["busy"]:
        raise RuntimeError("Receiver not idle; no acceptance commands sent")
    try:
        try:
            receiver.command("NEXT")
        except ReceiverError as error:
            if "disabled" not in str(error):
                raise
            cases.append("unarmed_command_rejected")
        for direction in ("NEXT", "PREV"):
            armed = receiver.command("ARM_VIRTUAL")
            if armed["network_mode"] != "virtual":
                raise RuntimeError("Virtual ARM did not select virtual mode")
            accepted = receiver.command(direction)
            if accepted["result"] != "virtual_accepted" or accepted["hid_commands"] != before["hid_commands"]:
                raise RuntimeError("Virtual direction unexpectedly enabled HID")
            cases.append("virtual_" + direction.lower())
            receiver.command("STOP")
        ticket = receiver.probe()
        text = "G1|{}|{}|{}|NEXT".format(ticket["boot_id"], ticket["ticket"], ticket["last_sequence"] + 1)
        bad_signature = hmac.new(bytes(32), text.encode(), hashlib.sha256).hexdigest()
        receiver.socket.sendto((text + "|" + bad_signature).encode(), receiver.address)
        try:
            receiver._receive(ticket["ticket"])
        except ReceiverError as error:
            if "timeout" not in str(error):
                raise
            cases.append("wrong_hmac_rejected")
        else:
            raise RuntimeError("Wrong HMAC was acknowledged")
        ticket = receiver.probe()
        text = "G1|{}|{}|{}|ARM_VIRTUAL".format(ticket["boot_id"], ticket["ticket"], ticket["last_sequence"] + 1)
        packet = (text + "|" + hmac.new(receiver.key, text.encode(), hashlib.sha256).hexdigest()).encode()
        time.sleep(.23)
        receiver.socket.sendto(packet, receiver.address)
        stale = receiver._receive(ticket["ticket"])
        if stale["result"] != "stale_ticket" or stale["network_mode"] != "off":
            raise RuntimeError("Expired ticket was not refused")
        cases.append("expired_ticket_rejected")
        receiver.command("ARM_VIRTUAL")
        time.sleep(.7)
        lost = receiver.probe()
        if lost["network_mode"] != "off":
            raise RuntimeError("Heartbeat loss did not revoke virtual permission")
        cases.append("heartbeat_loss_disarmed")
        final = receiver.command("STOP")
        if (final["hid_commands"] != before["hid_commands"]
                or final["virtual_commands"] != before["virtual_commands"] + 2
                or final["network_mode"] != "off" or final["busy"]):
            raise RuntimeError("Unexpected final virtual acceptance state")
        report = dict(cases_passed=cases, passed=True, receiver_product=final["product"],
                      virtual_commands_delta=2, hid_commands_delta=0, final_mode="off",
                      pc_runtime_bridge=False, usb_sampler_opened=False, pl_configured=False,
                      actual_eye_control_tested=False)
        print(json.dumps(report, indent=2))
    finally:
        try:
            receiver.command("STOP")
        finally:
            receiver.close()


if __name__ == "__main__":
    main()
