"""Exercise the actual SDK MTU branch used by the build overlay."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('ble_compat', Path(__file__).resolve().parents[1] / 'ble_compat.py')
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)

# Arduino-ESP32 3.3.11 BLEClient.cpp CONNECT branch, before security handling.
MTU_REQUEST = '''        rc = ble_gattc_exchange_mtu(client->m_conn_id, nullptr, nullptr);
        if (rc != 0) {
          log_e("BLEClient", "MTU exchange error; rc=%d %s", rc, BLEUtils::returnCodeToString(rc));
          break;
        }
'''


class CompatibilityTests(unittest.TestCase):
    def test_mtu_collision_completes_connection_and_other_errors_still_fail(self):
        fragment = compat.patch_client(MTU_REQUEST)
        program = '''
#define BLE_HS_EALREADY 2
#define log_e(...) ((void)0)
struct Task { int flags = -1; };
struct Client { int m_conn_id = 0; };
static int nextResult;
int ble_gattc_exchange_mtu(int, void*, void*) { return nextResult; }
namespace BLEUtils {
  void taskRelease(Task &task, int rc) { task.flags = rc; }
}
int connectEvent(int result, int &released) {
  nextResult = result;
  Client object; Client *client = &object;
  Task task; Task *pTaskData = &task;
  int rc = 0;
  do {
''' + fragment + '''
    released = task.flags;
    return 0; // Original SDK returns while waiting for the MTU event.
  } while (false);
  BLEUtils::taskRelease(*pTaskData, rc); // Original event-handler epilogue.
  released = task.flags;
  return rc;
}
int main() {
  int released;
  if (connectEvent(2, released) != 0 || released != 0) return 1;
  if (connectEvent(6, released) != 6 || released != 6) return 2;
  if (connectEvent(0, released) != 0 || released != -1) return 3;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'test.cpp').write_text(program, encoding='utf-8')
            subprocess.run(['cl', '/nologo', '/EHsc', str(root / 'test.cpp'), '/Fe:' + str(root / 'test.exe'), '/Fo:' + str(root / 'test.obj')], check=True, capture_output=True, cwd=tmp)
            subprocess.run([str(root / 'test.exe')], check=True)


if __name__ == '__main__':
    unittest.main()
