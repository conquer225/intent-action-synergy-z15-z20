"""Build-local compatibility for the measured ESP32 3.3.11 MTU collision."""
from pathlib import Path
import hashlib
import json
import shutil


def patch_client(source):
    request = '        rc = ble_gattc_exchange_mtu(client->m_conn_id, nullptr, nullptr);'
    if source.count(request) != 1:
        raise ValueError('Unrecognized SDK MTU branch; review before patching.')
    return source.replace(request, request + '''
        // The peer/host can already have an MTU exchange in progress.
        // Keep the real connection and complete this wait; retain other errors.
        if (rc == BLE_HS_EALREADY) {
          BLEUtils::taskRelease(*pTaskData, 0);
          rc = 0;
        }''', 1)


def stage_library(source, destination):
    source, destination = Path(source), Path(destination)
    original = source / 'src' / 'BLEClient.cpp'
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    if digest != 'd35d20b0822e41241cfe290a4caa70807dcfecc9662af99cc1fd4a0be603bde6':
        raise ValueError('Expected reviewed Arduino-ESP32 3.3.11 BLEClient.cpp.')
    patched = patch_client(original.read_text(encoding='utf-8'))
    shutil.copytree(source, destination, dirs_exist_ok=True)
    target = destination / 'src' / 'BLEClient.cpp'
    target.write_text(patched, encoding='utf-8')
    manifest = dict(source_sha256=digest, patched_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                    change='Treat MTU EALREADY as an existing exchange, preserving connection and other errors.')
    (destination.parent / 'ble_compat_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return destination
